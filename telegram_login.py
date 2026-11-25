import argparse
from getpass import getpass
from pathlib import Path

from dotenv import dotenv_values, set_key
from telethon.sync import TelegramClient

root = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Validate configuration without signing in.")
    parser.add_argument("--setup", action="store_true", help="Prompt for missing local API settings.")
    args = parser.parse_args()

    env_file = root / ".env"
    config = dotenv_values(env_file, encoding="utf-8-sig", interpolate=False)
    keys = ("GEMINI_API_KEY", "TELEGRAM_API_ID", "TELEGRAM_API_HASH")
    added = {}
    if args.setup:
        for key in keys:
            if not config.get(key):
                read = input if key == "TELEGRAM_API_ID" else getpass
                added[key] = read(f"{key}: ").strip()
        config.update(added)
    if not config.get("GEMINI_API_KEY"):
        parser.exit(1, "Set GEMINI_API_KEY in .env.\n")
    api_id = config.get("TELEGRAM_API_ID") or ""
    api_hash = config.get("TELEGRAM_API_HASH") or ""
    if not api_id.isascii() or not api_id.isdecimal() or int(api_id) <= 0:
        parser.exit(1, "Set a valid TELEGRAM_API_ID in .env.\n")
    if len(api_hash) != 32 or any(char not in "0123456789abcdefABCDEF" for char in api_hash):
        parser.exit(1, "Set a valid TELEGRAM_API_HASH in .env.\n")
    if args.check:
        print("Telegram configuration is valid. No sign-in attempted.")
        return

    for key, value in added.items():
        set_key(env_file, key, value, encoding="utf-8-sig")

    session_dir = root / ".telegram"
    session_dir.mkdir(exist_ok=True)
    client = TelegramClient(str(session_dir / "voice-agency"), int(api_id), api_hash)
    client.session.save_entities = False
    try:
        client.start()
        if client.get_me() is None:
            parser.exit(1, "Telegram could not verify the signed-in account.\n")
        print("Telegram sign-in verified. Local session saved.")
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
