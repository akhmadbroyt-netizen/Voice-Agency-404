import asyncio
from pathlib import Path

from dotenv import dotenv_values
from ntgcalls import MediaSource
from pytgcalls import PyTgCalls
from pytgcalls.types import ChatUpdate, Device, Direction, RecordStream, StreamFrames
from pytgcalls.types.raw import AudioParameters, AudioStream, Stream
from telethon import TelegramClient, events
from threading import Thread
from webbrowser import open as open_browser

from gemini_voice import talk
from service_desk import (
    PORT, attendance_result, book_opening, claim_attendance_call, confirm_offer,
    dashboard_server, delivery_result, pending_messages, request_move, save_request,
    waitlist_candidates,
)


async def main():
    root = Path(__file__).resolve().parent
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
        voice_task = None
        connected = False
        received_audio = False
        incoming = asyncio.Queue(maxsize=100)

        async def run_voice(peer_id):
            nonlocal voice_task
            try:
                username = None
                try:
                    peer = await client.get_entity(peer_id)
                    username = getattr(peer, "username", None)
                except (ValueError, TypeError):
                    print("Telegram username unavailable; keeping the caller ID.", flush=True)
                request_id, *_ = save_request(peer_id, username, "", "", None, False)
                print(f"Call recorded: {request_id}", flush=True)
                followup = await talk(calls, peer_id, incoming, config, username, request_id)
                voice_task = None
                await calls.leave_call(peer_id)
                if followup:
                    request_id, date, service, low, high = followup
                    message = f"Murojaat {request_id}. {service}: taxminan {low:,} - {high:,} so'm."
                    if date:
                        message += f" {date.replace(chr(84), chr(32))} uchun diagnostika so'rovi qabul qilindi. Usta vaqtni tasdiqlaydi."
                    await client.send_message(peer_id, message)
            except Exception as error:
                if isinstance(error, ExceptionGroup):
                    error = error.exceptions[0]
                print(f"Gemini audio failed ({type(error).__name__}).", flush=True)
                code = getattr(error, "code", None)
                if isinstance(code, int):
                    print(f"Gemini error code: {code}", flush=True)
                if connected:
                    await calls.leave_call(peer_id)

        @calls.on_update()
        async def on_update(app, update):
            nonlocal caller_id, connected, received_audio, voice_task
            if connected and update.chat_id != caller_id:
                return
            if isinstance(update, ChatUpdate):
                if update.status & ChatUpdate.Status.INCOMING_CALL and not connected:
                    caller_id = update.chat_id
                    connected = True
                    received_audio = False
                    while not incoming.empty():
                        incoming.get_nowait()
                    try:
                        print("Test call received. Connecting audio...", flush=True)
                        await app.play(caller_id, Stream(microphone=AudioStream(MediaSource.EXTERNAL, "")))
                        await app.record(caller_id, RecordStream(audio=True, audio_parameters=AudioParameters(48000, 1)))
                        if connected:
                            voice_task = asyncio.create_task(run_voice(caller_id))
                    except Exception:
                        connected = False
                        raise
                elif connected and update.status & ChatUpdate.Status.LEFT_CALL:
                    connected = False
                    if voice_task and not voice_task.done() and voice_task is not asyncio.current_task():
                        voice_task.cancel()
                        voice_task = None
                    print("Call ended. Waiting for another test call.", flush=True)
            elif (
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
            if words[0] in ("kochir", "kechikaman"):
                request_move(event.sender_id, event.reply_to_msg_id, token)
            elif words[0] in ("boladi", "ha"):
                confirm_offer(event.sender_id, event.reply_to_msg_id, token)

        async def outbound_call(job, greeting, answer):
            nonlocal caller_id, connected, received_audio, voice_task
            caller_id = job["caller_id"]
            connected = True
            received_audio = False
            while not incoming.empty():
                incoming.get_nowait()
            prompt = (
                "You are the avtoservis AI assistant. Speak briefly in Uzbek. "
                "Ask only the question in the greeting. After the caller clearly answers, "
                "call outbound_result with yes or no. If still ambiguous after one follow-up, "
                "report unclear. Speak the instruction the tool returns, then say goodbye. "
                "Never say a time was booked unless the tool confirms it."
            )
            try:
                await asyncio.wait_for(
                    calls.play(caller_id, Stream(microphone=AudioStream(MediaSource.EXTERNAL, ""))), 35,
                )
                if not connected:
                    return
                await calls.record(caller_id, RecordStream(audio=True, audio_parameters=AudioParameters(48000, 1)))
                voice_task = asyncio.create_task(talk(calls, caller_id, incoming, config, outbound={
                    "prompt": prompt, "greeting": greeting, "answer": answer,
                }))
                await asyncio.gather(voice_task, return_exceptions=True)
            except Exception as error:
                print(f"Scheduled Telegram call failed ({type(error).__name__}).", flush=True)
            finally:
                voice_task = None
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
                if connected:
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

                await outbound_call(job, f"Assalomu alaykum, avtoservis AI yordamchisiman. "
                                    f"{job['worker']} usta sizni kutyapti. Ustaxonaga kelyapsizmi?", attendance)
                if outcome == "no_answer":
                    attendance_result(job, outcome)
                if outcome != "cannot_come":
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

                    await outbound_call(candidate, f"Assalomu alaykum, avtoservis AI yordamchisiman. "
                                        f"{job['worker']} usta hozir bo'shadi. Yaqin vaqtda kelib "
                                        "mashinangizni tekshirtirmoqchimisiz?", accept_opening)
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


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
