import asyncio
from array import array
from collections import deque
from datetime import datetime
from pathlib import Path

from google import genai
from google.genai import types
from pytgcalls.types import Device

from service_desk import TARIFFS, UZ, save_request


def to_gemini(pcm):
    samples = array("h", pcm)
    return array("h", (
        (samples[i] + samples[i + 1] + samples[i + 2]) // 3
        for i in range(0, len(samples) - 2, 3)
    )).tobytes()


def to_telegram(pcm):
    return array("h", (sample for value in array("h", pcm) for sample in (value, value))).tobytes()


async def talk(calls, caller_id, incoming, config, username=None, request_id=None):
    async with genai.Client(
        api_key=config["GEMINI_API_KEY"],
        http_options=types.HttpOptions(api_version="v1beta"),
    ).aio as client:
        async with client.live.connect(
            model=config.get("GEMINI_LIVE_MODEL") or "gemini-3.1-flash-live-preview",
            config=types.LiveConnectConfig(
                response_modalities=["AUDIO"],
                realtime_input_config=types.RealtimeInputConfig(
                    automatic_activity_detection=types.AutomaticActivityDetection(disabled=True),
                    activity_handling="START_OF_ACTIVITY_INTERRUPTS",
                ),
                input_audio_transcription=types.AudioTranscriptionConfig(),
                tools=[types.Tool(function_declarations=[
                    types.FunctionDeclaration(
                        name="quote",
                        description="Get estimated demo labor prices in Uzbek sums.",
                        parameters_json_schema={
                            "type": "object", "properties": {
                                "service": {"type": "string", "enum": list(TARIFFS)},
                            }, "required": ["service"],
                        },
                    ),
                    *[types.FunctionDeclaration(
                        name=action,
                        description=(
                            "Save or update the request as soon as the issue is known and after the caller agrees to a date or time."
                            if action == "save_details" else
                            "Save the final details, then say goodbye. Use when the caller is done."
                        ),
                        parameters_json_schema={
                            "type": "object", "properties": {
                                "car": {"type": "string"},
                                "issue": {"type": "string"},
                                "service": {"type": "string", "enum": list(TARIFFS)},
                                "wants_visit": {"type": "boolean", "description": "Caller explicitly requested a diagnostic visit"},
                                "send_telegram": {"type": "boolean", "description": "Caller explicitly agreed to receive a Telegram message"},
                                "visit_date": {"type": "string", "description": "Requested date in YYYY-MM-DD"},
                                "visit_time": {"type": "string", "description": "HH:MM in Tashkent, only if the caller requested a time"},
                                "phone": {"type": "string", "description": "Phone number only if provided"},
                            }, "required": ["car", "issue", "service", "wants_visit", "send_telegram"],
                        },
                    ) for action in ("save_details", "finish_call")],
                ])],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Charon"),
                    ),
                ),
                system_instruction=(
                    f"Today in Tashkent: {datetime.now(UZ).date().isoformat()}.\n"
                    + Path(__file__).with_name("operator-prompt.md").read_text(encoding="utf-8-sig")
                ),
            ),
        ) as session:
            print("Gemini Live connected. Requesting greeting...", flush=True)
            await session.send_realtime_input(
                text="Say only: Assalomu alaykum, avtoservis AI yordamchisiman. Nima muammo bo'ldi?"
            )

            outgoing = bytearray()
            audio_ready = asyncio.Event()
            turn_complete = False
            finished = asyncio.Event()
            saved = None
            followup = False
            ending = False
            goodbye_audio = False
            transcript = []

            caller_speaking = False

            async def upload():
                nonlocal caller_speaking
                lead = deque(maxlen=8)
                speech_samples = silence_samples = 0
                while True:
                    pcm = to_gemini(await incoming.get())
                    samples = array("h", pcm)
                    voiced = bool(samples) and sum(sample * sample for sample in samples) > 350**2 * len(samples)
                    if not caller_speaking:
                        lead.append(pcm)
                        speech_samples = speech_samples + len(samples) if voiced else 0
                        if speech_samples < 800:
                            continue
                        caller_speaking = True
                        outgoing.clear()
                        print("Caller speaking; assistant playback stopped.", flush=True)
                        await session.send_realtime_input(activity_start=types.ActivityStart())
                        pcm = b"".join(lead)
                        lead.clear()

                    await session.send_realtime_input(audio=types.Blob(data=pcm, mime_type="audio/pcm;rate=16000"))
                    silence_samples = 0 if voiced else silence_samples + len(samples)
                    if silence_samples >= 7200:
                        caller_speaking = False
                        speech_samples = silence_samples = 0
                        await session.send_realtime_input(activity_end=types.ActivityEnd())

            async def receive():
                nonlocal turn_complete, saved, followup, ending, goodbye_audio
                announced = False
                while True:
                    async for response in session.receive():
                        if response.tool_call:
                            replies = []
                            for call in response.tool_call.function_calls:
                                args = call.args or {}
                                service = args.get("service")
                                if call.name == "quote":
                                    label, low, high = TARIFFS.get(service, TARIFFS["diagnostic"])
                                    result = {"service": label, "min_uzs": low, "max_uzs": high}
                                elif call.name in ("save_details", "finish_call"):
                                    ending = call.name == "finish_call"
                                    if str(args.get("issue", "")).strip():
                                        saved = save_request(
                                            caller_id, username, str(args.get("car") or "Noma'lum")[:100],
                                            str(args["issue"])[:1000], service if service in TARIFFS else "diagnostic",
                                            args.get("wants_visit") is True, str(args.get("phone") or "")[:40],
                                            request_id=request_id, visit_time=str(args.get("visit_time") or ""),
                                            visit_date=str(args.get("visit_date") or ""),
                                        )
                                        followup = args.get("send_telegram") is True
                                    result = {"saved": saved is not None}
                                    if ending:
                                        result["instruction"] = "Say goodbye now."
                                else:
                                    result = {"error": "Unknown action"}
                                replies.append(types.FunctionResponse(id=call.id, name=call.name, response=result))
                            turn_complete = False
                            await session.send_tool_response(function_responses=replies)
                        content = response.server_content
                        if not content:
                            continue
                        if content.input_transcription and content.input_transcription.text:
                            transcript.append(content.input_transcription.text)
                        if content.interrupted:
                            outgoing.clear()
                            audio_ready.set()
                        if content.model_turn and not caller_speaking:
                            for part in content.model_turn.parts:
                                if part.inline_data and part.inline_data.data:
                                    if not announced:
                                        print("First Gemini audio received.", flush=True)
                                        announced = True
                                    turn_complete = False
                                    if ending:
                                        goodbye_audio = True
                                    outgoing.extend(to_telegram(part.inline_data.data))
                                    audio_ready.set()

                        if content.turn_complete:
                            turn_complete = True
                            audio_ready.set()

            async def playback():
                frame_bytes = 960
                prebuffer = frame_bytes * 12
                loop = asyncio.get_running_loop()
                while True:
                    await audio_ready.wait()
                    audio_ready.clear()
                    if len(outgoing) < prebuffer and not turn_complete:
                        continue
                    deadline = loop.time()
                    while len(outgoing) >= frame_bytes or (turn_complete and outgoing):
                        frame = bytes(outgoing[:frame_bytes])
                        del outgoing[:frame_bytes]
                        await calls.send_frame(caller_id, Device.MICROPHONE, frame.ljust(frame_bytes, b"\x00"))
                        deadline = max(deadline + 0.01, loop.time())
                        await asyncio.sleep(max(0, deadline - loop.time()))
                    if ending and goodbye_audio and turn_complete and not outgoing:
                        finished.set()

            try:
                async with asyncio.timeout(300), asyncio.TaskGroup() as tasks:
                    running = [tasks.create_task(fn()) for fn in (upload, receive, playback)]
                    await finished.wait()
                    for task in running:
                        task.cancel()
            finally:
                if request_id and saved is None and transcript:
                    save_request(caller_id, username, "", " ".join(transcript)[:1000],
                                 None, False, request_id=request_id)
            return saved if followup else None
