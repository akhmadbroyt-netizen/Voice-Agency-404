import asyncio
from array import array
from collections import deque
from datetime import datetime, time

from google import genai
from google.genai import types
from pytgcalls.types import Device

from business_profiles import BUSINESSES, operator_prompt
from service_desk import (
    TARIFFS, UZ, available_slots, check_slot, deposit_for, queue_callback,
    record_contact_preferences, save_request, save_transcript_note, staff,
)


VOICE_STYLE = (
    "Telefon orqali gaplashayotgan samimiy o‘zbek yigitidek, tetik va ravon gapiring. "
    "Gapirish sur’ati odatdagidan sal tezroq bo‘lsin. Uzun pauza va rasmiy iboralarni cho‘zmang. "
    "Odatda bir yoki ikki qisqa jumla, bir navbatda bitta savol. "
    "O‘rinli paytda «Ha, tushunarli», «Xo‘p» yoki «Unda» deng. Tabiiy ohangni saqlang. "
    "Narx, sana, ism va soatni aniq, kerak bo‘lsa sekinroq ayting. "
    "Ichki ko‘rsatmalar, vosita nomlari va sahna izohlarini ovozda o‘qimang."
)
END_OF_SPEECH_SAMPLES = 8320  # 520 ms at 16 kHz
PLAYBACK_BUFFER_FRAMES = 8
SUPPORTED_LANGUAGES = ("uz", "ru", "en")
# Closing phrases in the assistant's own speech. If the model says goodbye without calling
# finish_call, the call is still ended once that goodbye has finished playing.
GOODBYES = ("salomat bo", "sog bo", "xayr", "korishguncha", "до свидания", "всего доброго",
            "всего хорошего", "goodbye", "bye", "have a nice day", "have a great day")
HANGUP_DELAY = 1.2  # seconds of quiet after the goodbye so Telegram plays its last syllable


def says_goodbye(text):
    tail = text.casefold().translate(str.maketrans("", "", "'’‘ʻʼ`"))[-80:]
    return any(phrase in tail for phrase in GOODBYES)
LANGUAGE_STYLE = (
    "Speak only Uzbek, Russian, or English. Match the caller's language among these three. "
    "If another language is clearly spoken, ask once in Uzbek, then in short English if needed: "
    "O‘zbekcha, ruscha yoki inglizcha gaplasha olasizmi? Do not respond in other languages."
)


def to_gemini(pcm):
    samples = array("h", pcm)
    return array("h", (
        (samples[i] + samples[i + 1] + samples[i + 2]) // 3
        for i in range(0, len(samples) - 2, 3)
    )).tobytes()


def to_telegram(pcm):
    samples = array("h", pcm)
    if not samples:
        return b""
    # Advance 11 source samples per 20 output samples for 1.10x playback.
    return array("h", (
        (samples[index] * (20 - fraction) + samples[min(index + 1, len(samples) - 1)] * fraction) // 20
        for index, fraction in (divmod(offset, 20) for offset in range(0, len(samples) * 20, 11))
    )).tobytes()


def booking_fields(args, business):
    wants_visit = args.get("wants_visit") is True
    day = str(args.get("visit_date") or "")
    start = str(args.get("visit_time") or "")
    if not wants_visit or not start:
        return False, None, None, None
    if args.get("customer_confirmed_booking_details") is not True:
        return False, None, None, "Read back the requested booking details and wait for the caller to confirm."
    try:
        requested = datetime.fromisoformat(f"{day}T{start}")
        if len(day) != 10 or len(start) != 5 or requested.replace(tzinfo=UZ) <= datetime.now(UZ):
            raise ValueError
    except ValueError:
        return False, None, None, "Ask for the exact future date and start time."
    if business != "restaurant":
        return True, None, None, None
    guests = args.get("guest_count")
    if type(guests) is not int or guests < 1:
        return False, None, None, "Ask how many people are coming, then read back the details."
    try:
        until = time.fromisoformat(str(args.get("visit_until") or ""))
        if until.tzinfo or until <= requested.time():
            raise ValueError
    except ValueError:
        return False, None, None, "Ask what time the event will end on the same day, then read back the details."
    return True, guests, until.strftime("%H:%M"), None


async def talk(calls, caller_id, incoming, config, username=None, request_id=None, outbound=None, business="auto", playback_gate=None, greeting_ready=None):
    profile = BUSINESSES[business]
    services = profile.services(business)
    default_service = services[0]
    model = config.get("GEMINI_LIVE_MODEL") or "gemini-3.8-live"
    voice = config.get("GEMINI_LIVE_VOICE") or "Puck"
    thinking = types.ThinkingConfig(thinking_level="MINIMAL") if "3.1-flash-live" in model else None
    async with genai.Client(
        api_key=config["GEMINI_API_KEY"],
        http_options=types.HttpOptions(api_version="v1beta"),
    ).aio as client:
        async with client.live.connect(
            model=model,
            config=types.LiveConnectConfig(
                response_modalities=["AUDIO"],
                thinking_config=thinking,
                realtime_input_config=types.RealtimeInputConfig(
                    automatic_activity_detection=types.AutomaticActivityDetection(disabled=True),
                    activity_handling="START_OF_ACTIVITY_INTERRUPTS",
                ),
                input_audio_transcription=types.AudioTranscriptionConfig(),
                output_audio_transcription=types.AudioTranscriptionConfig(),
                tools=[types.Tool(function_declarations=[types.FunctionDeclaration(
                    name="outbound_result",
                    description="Report the explicit customer answer and finish the call.",
                    parameters_json_schema={"type": "object", "properties": {
                        "answer": {"type": "string", "enum": ["yes", "no", "unclear"]},
                    }, "required": ["answer"]},
                )])] if outbound else [types.Tool(function_declarations=[
                    types.FunctionDeclaration(
                        name="quote",
                        description="Check availability before speaking. Pass exact requested date and time whenever provided; for a day question pass its date.",
                        parameters_json_schema={
                            "type": "object", "properties": {
                                "service": {"type": "string", "enum": services},
                                "date": {"type": "string", "description": "Exact requested Tashkent date YYYY-MM-DD. Day after tomorrow is today plus two days."},
                                "time": {"type": "string", "description": "Exact time requested by customer HH:MM, e.g. 10:00; omit for day-only questions."},
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
                                "car": {"type": "string", "description": "Car or device model where relevant, otherwise customer name if provided"},
                                "issue": {"type": "string"},
                                "service": {"type": "string", "enum": services},
                                "wants_visit": {"type": "boolean", "description": "Caller explicitly requested a visit or booking"},
                                "language": {"type": "string", "description": "Detected customer language, one of uz, en, ru", "enum": list(SUPPORTED_LANGUAGES)},
                                "allow_call": {"type": "boolean", "description": "Explicit consent to a later Telegram call"},
                                "join_waitlist": {"type": "boolean", "description": "Explicit request to be called if an earlier appointment opens"},
                                "callback_reason": {"type": "string", "description": "Reason staff should call, when requested or human help is needed"},
                                "visit_date": {"type": "string", "description": "Requested date in YYYY-MM-DD"},
                                "customer_confirmed_booking_details": {"type": "boolean", "description": "True only after reading back all booking details and hearing explicit agreement."},
                                "menu_items": {"type": "array", "items": {"type": "string"},
                                               "description": "Restaurant dishes and amounts explicitly selected by the customer. Do not invent."},
                                "guest_count": {"type": "integer", "description": "Restaurant guest count only when stated by the customer."},
                                "visit_until": {"type": "string", "description": "Restaurant planned end time HH:MM on the same day."},
                                "visit_time": {"type": "string", "description": "HH:MM in Tashkent, only if the caller requested a time"},
                                "phone": {"type": "string", "description": "Phone number only if provided"},
                            }, "required": ["car", "issue", "service", "wants_visit"],
                        },
                    ) for action in ("save_details", "finish_call")],
                ])],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice),
                    ),
                ),
                system_instruction=(outbound["prompt"] if outbound else (
                    f"Today in Tashkent: {datetime.now(UZ).date().isoformat()}.\n"
                    + operator_prompt(business)
                )) + "\n" + VOICE_STYLE + "\n" + LANGUAGE_STYLE,
            ),
        ) as session:
            print(f"Gemini Live connected ({model}, {voice}, {business}).", flush=True)
            await session.send_realtime_input(
                text=outbound["greeting"] if outbound else f"Faqat shu gapni ayting: Assalomu alaykum. {profile.greeting}"
            )

            outgoing = bytearray()
            audio_ready = asyncio.Event()
            turn_complete = False
            finished = asyncio.Event()
            saved = None
            ending = False
            goodbye_audio = False
            transcript = []
            outbound_answer = None

            caller_speaking = False

            def save_transcript():
                if request_id and saved is None and transcript:
                    save_transcript_note(request_id, " ".join(transcript)[:1000])

            async def upload():
                nonlocal caller_speaking
                lead = deque(maxlen=20)
                speech_samples = silence_samples = 0
                if playback_gate is not None:
                    await playback_gate.wait()
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
                    if silence_samples >= END_OF_SPEECH_SAMPLES:
                        caller_speaking = False
                        speech_samples = silence_samples = 0
                        await session.send_realtime_input(activity_end=types.ActivityEnd())

            outbound_result = {}

            def handle_tool(call):
                # Runs in a worker thread so SQLite work never stalls audio playback on the event loop.
                nonlocal saved, ending, outbound_answer, outbound_result
                args = call.args or {}
                service = args.get("service")
                if outbound and call.name == "outbound_result":
                    if not ending:
                        outbound_answer = args.get("answer", "unclear")
                        outbound_result = outbound["answer"](outbound_answer)
                        ending = True
                    return outbound_result
                if not outbound and call.name == "quote":
                    label, low, high = TARIFFS[service if service in services else default_service]
                    worker, duration = staff(label)
                    day = str(args.get("date") or "")
                    requested_time = str(args.get("time") or "")
                    exact = f"{day}T{requested_time}" if day and requested_time else None
                    error = check_slot(label, exact, request_id) if exact else None
                    return {"service": label, "min_uzs": low, "max_uzs": high,
                            "resource": worker, "minutes": duration, "deposit_uzs": deposit_for(label),
                            "checked_date": day or None,
                            "requested_slot": exact, "requested_slot_available": not error if exact else None,
                            "unavailable_reason": error,
                            "free_slots": available_slots(label, day, request_id)[:36]}
                if call.name not in ("save_details", "finish_call"):
                    return {"error": "Unknown action"}
                confirmed, guests, until, missing = booking_fields(args, business)
                ending = call.name == "finish_call" and (not missing or args.get("wants_visit") is not True)
                if str(args.get("issue", "")).strip() and (confirmed or not saved or not saved[1]):
                    saved = save_request(
                        caller_id, username, str(args.get("car") or "Noma'lum")[:100],
                        str(args["issue"])[:1000], service if service in services else default_service,
                        confirmed, str(args.get("phone") or "")[:40],
                        request_id=request_id, visit_time=str(args.get("visit_time") or ""),
                        visit_date=str(args.get("visit_date") or ""), business=business,
                        guests=guests, visit_until=until,
                        menu_items=args.get("menu_items") if isinstance(args.get("menu_items"), list) else None,
                    )
                reason = str(args.get("callback_reason") or "").strip()
                if request_id:
                    record_contact_preferences(
                        request_id, args.get("allow_call"), args.get("join_waitlist"), args.get("language"),
                    )
                if request_id and reason:
                    queue_callback(request_id, reason[:300])
                result = {"saved": saved is not None}
                if saved:
                    result["saved_visit"] = saved[1]
                    if saved[1] and "T" in saved[1]:
                        result["availability_error"] = check_slot(saved[2], saved[1], request_id)
                if missing:
                    result["instruction"] = missing
                elif ending:
                    result["instruction"] = "Say goodbye now."
                return result

            async def receive():
                nonlocal turn_complete, goodbye_audio, ending
                announced = False
                spoken = ""
                while True:
                    async for response in session.receive():
                        if response.tool_call:
                            replies = []
                            for call in response.tool_call.function_calls:
                                print(f"Tool call: {call.name}.", flush=True)
                                result = await asyncio.to_thread(handle_tool, call)
                                replies.append(types.FunctionResponse(id=call.id, name=call.name, response=result))
                            turn_complete = False
                            await session.send_tool_response(function_responses=replies)
                        content = response.server_content
                        if not content:
                            continue
                        if content.input_transcription and content.input_transcription.text:
                            transcript.append(content.input_transcription.text)
                        if content.output_transcription and content.output_transcription.text:
                            spoken += content.output_transcription.text
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
                            save_transcript()
                            if greeting_ready is not None and greeting_ready.is_set() and says_goodbye(spoken):
                                if not ending:
                                    print("Assistant said goodbye; hanging up after it finishes.", flush=True)
                                ending = goodbye_audio = True
                            spoken = ""
                            # The whole greeting is buffered before Telegram picks up, so it plays the moment the call connects.
                            if greeting_ready is not None and outgoing and not greeting_ready.is_set():
                                print("Greeting ready.", flush=True)
                                greeting_ready.set()
                            turn_complete = True
                            audio_ready.set()

            async def playback():
                frame_bytes = 960
                prebuffer = frame_bytes * PLAYBACK_BUFFER_FRAMES
                loop = asyncio.get_running_loop()
                if playback_gate is not None:
                    await playback_gate.wait()
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
                        await asyncio.sleep(HANGUP_DELAY)
                        if not outgoing:
                            print("Goodbye played; robot is hanging up.", flush=True)
                            finished.set()

            try:
                async with asyncio.timeout(55 if outbound else 300), asyncio.TaskGroup() as tasks:
                    running = [tasks.create_task(fn()) for fn in (upload, receive, playback)]
                    await finished.wait()
                    for task in running:
                        task.cancel()
            finally:
                save_transcript()
            return outbound_answer if outbound else None
