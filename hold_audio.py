import asyncio

from pytgcalls.types import Device

FRAME_BYTES = 960


async def play_hold(calls, peer_id, announcement, music, is_waiting):
    loop = asyncio.get_running_loop()
    deadline = loop.time()
    offset = 0
    while is_waiting():
        if offset < len(announcement):
            frame = announcement[offset:offset + FRAME_BYTES].ljust(FRAME_BYTES, b"\0")
        else:
            start = (offset - len(announcement)) % len(music)
            frame = music[start:start + FRAME_BYTES]
            while len(frame) < FRAME_BYTES:
                frame += music[:FRAME_BYTES - len(frame)]
        await calls.send_frame(peer_id, Device.MICROPHONE, frame)
        offset += FRAME_BYTES
        if offset >= len(announcement) and offset - FRAME_BYTES < len(announcement):
            offset = len(announcement)
        deadline = max(deadline + 0.01, loop.time())
        await asyncio.sleep(max(0, deadline - loop.time()))
