import asyncio
import os
from pathlib import Path

from dotenv import dotenv_values
from ntgcalls import MediaSource
from pytgcalls import PyTgCalls
from pytgcalls.types import ChatUpdate, Device, Direction, RecordStream, StreamFrames
from pytgcalls.types.raw import AudioParameters, AudioStream, Stream
from telethon import TelegramClient, events
from threading import Thread
from webbrowser import open as open_browser

from gemini_voice import SUPPORTED_LANGUAGES, talk
from hold_audio import play_hold
from service_desk import (
    PORT, active_business, attendance_result, business_for, deposit_for, book_opening, claim_attendance_call, clear_live_call,
    confirm_offer, dashboard_server, delivery_result, pending_messages, request_move, save_request, set_live_call,
    waitlist_candidates,
)

GREETING_WAIT = 8

MOVE_ACCEPTED = "Ko‘chirish so‘rovingiz qabul qilindi. Xodim yangi vaqt taklif qiladi, eski bron hozircha saqlanadi."
MOVE_NOT_FOUND = "Bu kod bo‘yicha faol bron topilmadi. Tasdiq xabaridagi KOCHIR kodini tekshirib qayta yozing."
OFFER_NOT_FOUND = "Bu kod bo‘yicha amaldagi taklif topilmadi. Taklif muddati o‘tgan yoki omonat hali qayd qilinmagan bo‘lishi mumkin."


async def main():
    root = Path(__file__).resolve().parent
    music_file = root / ".data" / "hold-music.pcm"
    announcement_file = root / ".data" / "hold-announcement.pcm"
    music = music_file.read_bytes() if music_file.is_file() else b""
    announcement = announcement_file.read_bytes() if announcement_file.is_file() else b""
    config = dotenv_values(root / ".env", encoding="utf-8-sig", interpolate=False)
    if not config.get("GEMINI_API_KEY"):
        raise SystemExit("Set GEMINI_API_KEY in .env.")
    session = root / ".telegram" / "voice-agency.session"
    if not session.is_file():
        raise SystemExit("Run start-demo.bat to create a session.")
    client = TelegramClient(str(session), int(config["TELEGRAM_API_ID"]), config["TELEGRAM_API_HASH"])
    calls = PyTgCalls(client)
    await client.connect()
    try:
        account = await client.get_me()
        if not account:
            raise SystemExit("Telegram session expired. Run start-demo.bat again.")
        caller_id = None
        waiting_id = None
        waiting_task = None
        voice_task = None
        connected = False
        received_audio = False
        incoming = asyncio.Queue(maxsize=100)

        async def run_voice(peer_id, playback_gate, greeting_ready):
            nonlocal voice_task
            try:
                username = None
                try:
                    peer = await asyncio.wait_for(client.get_entity(peer_id), 0.25)
                    username = getattr(peer, "username", None)
                except (ValueError, TypeError, TimeoutError):
                    print("Telegram username unavailable; keeping the caller ID.", flush=True)
                business = active_business()
                request_id, *_ = save_request(peer_id, username, "", "", None, False, business=business)
                set_live_call(peer_id, request_id)
                print(f"Call recorded: {request_id}", flush=True)
                await talk(calls, peer_id, incoming, config, username, request_id, business=business,
                                      playback_gate=playback_gate, greeting_ready=greeting_ready)
                voice_task = None
                clear_live_call(peer_id)
                await calls.leave_call(peer_id)
            except Exception as error:
                clear_live_call(peer_id)
                if isinstance(error, ExceptionGroup):
                    error = error.exceptions[0]
                print(f"Gemini audio failed ({type(error).__name__}: {str(error)[:300]}).", flush=True)
                code = getattr(error, "code", None)
                if isinstance(code, int):
                    print(f"Gemini error code: {code}", flush=True)
                await playback_gate.wait()
                if connected and caller_id == peer_id:
                    await calls.leave_call(peer_id)

        async def start_inbound(peer_id, already_joined=False):
            nonlocal caller_id, connected, received_audio, voice_task
            caller_id = peer_id
            connected = True
            received_audio = False
            while not incoming.empty():
                incoming.get_nowait()
            playback_gate = asyncio.Event()
            greeting_ready = asyncio.Event()
            task = asyncio.create_task(run_voice(peer_id, playback_gate, greeting_ready))
            voice_task = task
            try:
                if not already_joined:
                    # Let the phone ring until Gemini is connected and the greeting is fully prepared.
                    ready = asyncio.create_task(greeting_ready.wait())
                    await asyncio.wait({ready, task}, timeout=GREETING_WAIT, return_when=asyncio.FIRST_COMPLETED)
                    ready.cancel()
                    if not connected or caller_id != peer_id:
                        return
                    if task.done():
                        print("Gemini is not ready; the call is declined instead of answering in silence.", flush=True)
                        connected = False
                        voice_task = None
                        playback_gate.set()
                        await calls.leave_call(peer_id)
                        return
                    if not greeting_ready.is_set():
                        print("Greeting still preparing; answering Telegram.", flush=True)
                    await calls.play(peer_id, Stream(microphone=AudioStream(MediaSource.EXTERNAL, "")))
                if connected and caller_id == peer_id:
                    await calls.record(peer_id, RecordStream(audio=True, audio_parameters=AudioParameters(48000, 1)))
                    playback_gate.set()
            except Exception:
                task.cancel()
                if caller_id == peer_id:
                    connected = False
                    if voice_task is task:
                        voice_task = None
                raise

        async def hold_caller(peer_id):
            nonlocal waiting_id, waiting_task
            try:
                await calls.play(peer_id, Stream(microphone=AudioStream(MediaSource.EXTERNAL, "")))
                print("Second caller is on hold.", flush=True)
                await play_hold(calls, peer_id, announcement, music,
                                lambda: waiting_id == peer_id and connected)
                if waiting_id == peer_id and not connected:
                    waiting_id = None
                    waiting_task = None
                    await start_inbound(peer_id, already_joined=True)
            except Exception as error:
                print(f"Waiting call failed ({type(error).__name__}).", flush=True)
                try:
                    await calls.leave_call(peer_id)
                except Exception as cleanup_error:
                    print(f"Waiting call cleanup failed ({type(cleanup_error).__name__}).", flush=True)
            finally:
                if waiting_id == peer_id:
                    waiting_id = None
                    waiting_task = None

        @calls.on_update()
        async def on_update(app, update):
            nonlocal connected, waiting_id, waiting_task, received_audio, voice_task
            peer_id = update.chat_id
            if isinstance(update, ChatUpdate):
                if update.status & ChatUpdate.Status.INCOMING_CALL:
                    if not connected and waiting_id is None:
                        await start_inbound(peer_id)
                    elif music and waiting_id is None and peer_id != caller_id:
                        waiting_id = peer_id
                        waiting_task = asyncio.create_task(hold_caller(peer_id))
                elif update.status & ChatUpdate.Status.LEFT_CALL:
                    if peer_id == waiting_id:
                        waiting_id = None
                        if waiting_task:
                            waiting_task.cancel()
                            waiting_task = None
                    elif connected and peer_id == caller_id:
                        connected = False
                        clear_live_call(peer_id)
                        if voice_task and not voice_task.done() and voice_task is not asyncio.current_task():
                            voice_task.cancel()
                            voice_task = None
                        print("Call ended.", flush=True)
                return
            if peer_id != caller_id:
                return
            if (
                connected
                and isinstance(update, StreamFrames)
                and update.direction == Direction.INCOMING
                and update.device in (Device.MICROPHONE, Device.SPEAKER)
            ):
                if update.frames and not received_audio:
                    received_audio = True
                    print("Telegram caller audio received.", flush=True)
                for frame in update.frames:
                    if incoming.full():
                        incoming.get_nowait()
                    incoming.put_nowait(frame.frame)

        @client.on(events.NewMessage(incoming=True))
        async def handle_reply(event):
            if not event.is_private or not event.sender_id:
                return
            words = event.raw_text.casefold().translate(str.maketrans("", "", "'’‘ʻʼ")).strip(" .!").split()
            if not words or len(words) > 2:
                return
            token = words[1] if len(words) == 2 else None
            reply = None
            # A bare "ha" in an ordinary chat must stay silent; only coded or quoted replies get an answer.
            addressed = token is not None or event.reply_to_msg_id is not None
            if words[0] in ("kochir", "kechikaman"):
                if request_move(event.sender_id, event.reply_to_msg_id, token):
                    reply = MOVE_ACCEPTED
                elif addressed:
                    reply = MOVE_NOT_FOUND
            elif words[0] in ("boladi", "ha"):
                if not confirm_offer(event.sender_id, event.reply_to_msg_id, token) and token is not None:
                    reply = OFFER_NOT_FOUND
            if reply:
                try:
                    await event.reply(reply)
                except Exception as error:
                    print(f"Telegram reply failed ({type(error).__name__}).", flush=True)

        async def outbound_call(job, greeting, answer):
            nonlocal caller_id, connected, received_audio, voice_task
            caller_id = job["caller_id"]
            connected = True
            received_audio = False
            while not incoming.empty():
                incoming.get_nowait()
            language = job.get("language")
            if language not in SUPPORTED_LANGUAGES:
                language = "uz"
            prompt = (
                f"You are the {business_for(job['service']).name} AI assistant. Start in language code {language}. "
                "If the customer speaks another language, reply in that language. "
                "Ask only the question in the greeting. After the caller clearly answers, "
                "call outbound_result with yes or no. If still ambiguous after one follow-up, "
                "report unclear. Translate the returned instruction into the customer language, then say goodbye. "
                "Never say a time was booked unless the tool confirms it."
            )
            try:
                await asyncio.wait_for(
                    calls.play(caller_id, Stream(microphone=AudioStream(MediaSource.EXTERNAL, ""))), 35,
                )
                if not connected:
                    return
                await calls.record(caller_id, RecordStream(audio=True, audio_parameters=AudioParameters(48000, 1)))
                set_live_call(caller_id, job.get("id"), "outbound")
                voice_task = asyncio.create_task(talk(calls, caller_id, incoming, config, outbound={
                    "prompt": prompt, "greeting": f"Say this in language code {language}: {greeting}", "answer": answer,
                }))
                await asyncio.gather(voice_task, return_exceptions=True)
            except Exception as error:
                print(f"Scheduled Telegram call failed ({type(error).__name__}).", flush=True)
            finally:
                voice_task = None
                clear_live_call(caller_id)
                try:
                    if connected:
                        await calls.leave_call(caller_id)
                except Exception as error:
                    print(f"Could not close scheduled call ({type(error).__name__}).", flush=True)
                finally:
                    connected = False

        async def scheduled_calls():
            while True:
                await asyncio.sleep(3)
                if connected or waiting_id is not None:
                    continue
                job = claim_attendance_call()
                if not job:
                    continue
                outcome = "no_answer"

                def attendance(answer):
                    nonlocal outcome
                    outcome = {"yes": "coming", "no": "cannot_come"}.get(answer, "unclear")
                    attendance_result(job, outcome)
                    return {"instruction": "Rahmat, javobingizni qayd qildim. Salomat bo'ling."}

                profile = business_for(job["service"])
                await outbound_call(job, f"Assalomu alaykum, {profile.name} AI yordamchisiman. "
                                    f"{job['service']} uchun tashrifingiz bor. Kelyapsizmi?", attendance)
                if outcome == "no_answer":
                    attendance_result(job, outcome)
                if outcome != "cannot_come" or deposit_for(job["service"]):
                    continue
                for candidate in waitlist_candidates(job):
                    if connected:
                        break
                    booked = None

                    def accept_opening(answer):
                        nonlocal booked
                        if answer == "yes":
                            booked = book_opening(candidate, job)
                        return {"instruction": (
                            f"{booked.replace('T', ' ')} ga yozildingiz. Telegramdan tasdiq keladi."
                            if booked else "Rahmat, vaqt band qilinmadi. Salomat bo'ling."
                        )}

                    await outbound_call(candidate, f"Assalomu alaykum, {profile.name} AI yordamchisiman. "
                                        f"{job['service']} uchun vaqt bo‘shadi. Yaqin vaqtda kela olasizmi?",
                                        accept_opening)
                    if booked:
                        break

        async def send_notices():
            while True:
                for notice in pending_messages():
                    try:
                        try:
                            peer = await client.get_input_entity(notice["caller_id"])
                        except ValueError:
                            if not notice["username"]:
                                raise
                            peer = await client.get_entity("@" + notice["username"])
                            if peer.id != notice["caller_id"]:
                                raise ValueError("Telegram username changed")
                        message = await client.send_message(peer, notice["notice"])
                    except Exception as error:
                        print(f"Telegram notification failed ({type(error).__name__}).", flush=True)
                        delivery_result(notice["request_id"], kind=notice["kind"])
                    else:
                        delivery_result(notice["request_id"], message.id, notice["kind"])
                await asyncio.sleep(1)

        await calls.start()
        with dashboard_server() as server:
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            url = f"http://127.0.0.1:{PORT}"
            print(f"Dashboard: {url}", flush=True)
            print("Auto-answer active. Press Ctrl+C to stop.", flush=True)
            # The launcher sets this on automatic restarts so each reconnect does not open another tab.
            if not os.environ.get("VOICE404_NO_BROWSER"):
                open_browser(url)
            notices = asyncio.create_task(send_notices())
            scheduled = asyncio.create_task(scheduled_calls())
            try:
                await client.disconnected
            finally:
                notices.cancel()
                scheduled.cancel()
                await asyncio.gather(notices, scheduled, return_exceptions=True)
                server.shutdown()
    finally:
        await client.disconnect()


class Tee:
    """Mirror console output to .data/robot.log so a failed call can be diagnosed afterwards."""

    def __init__(self, stream, path):
        self.stream, self.file = stream, open(path, "a", encoding="utf-8", buffering=1)

    def write(self, text):
        self.stream.write(text)
        self.file.write(text)
        return len(text)

    def flush(self):
        self.stream.flush()
        self.file.flush()


if __name__ == "__main__":
    import sys
    from datetime import datetime
    log = Path(__file__).resolve().parent / ".data" / "robot.log"
    log.parent.mkdir(exist_ok=True)
    sys.stdout = Tee(sys.stdout, log)
    sys.stderr = Tee(sys.stderr, log)
    print(f"--- start {datetime.now():%Y-%m-%d %H:%M:%S}", flush=True)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
