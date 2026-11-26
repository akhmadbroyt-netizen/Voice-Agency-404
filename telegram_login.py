"""Setup wizard: checks the keys, asks for missing ones and signs in to Telegram.

    python telegram_login.py --check    validate .env without network or sign-in
    python telegram_login.py --setup    ask for missing or invalid keys, then sign in
    python telegram_login.py --reset    ask for every key again and sign in again
"""
import argparse
import sys
import webbrowser
from getpass import getpass
from pathlib import Path

from dotenv import dotenv_values, set_key

root = Path(__file__).resolve().parent
ENV_FILE = root / ".env"
SESSION_DIR = root / ".telegram"
SESSION = SESSION_DIR / "voice-agency"
GEMINI_PAGE = "https://aistudio.google.com/apikey"
TELEGRAM_PAGE = "https://my.telegram.org/apps"


def valid_api_id(value):
    return value.isascii() and value.isdecimal() and int(value) > 0


def valid_api_hash(value):
    return len(value) == 32 and all(char in "0123456789abcdefABCDEF" for char in value)


def problems(config):
    """Return the keys that are missing or malformed."""
    bad = []
    if not (config.get("GEMINI_API_KEY") or "").strip():
        bad.append("GEMINI_API_KEY")
    if not valid_api_id((config.get("TELEGRAM_API_ID") or "").strip()):
        bad.append("TELEGRAM_API_ID")
    if not valid_api_hash((config.get("TELEGRAM_API_HASH") or "").strip()):
        bad.append("TELEGRAM_API_HASH")
    return bad


def masked(value):
    return "…" + value[-4:] if len(value) > 4 else "****"


def gemini_works(key):
    """True if Google accepts the key, False if it rejects it, None if it can't be checked now."""
    try:
        from google import genai

        client = genai.Client(api_key=key)
        next(iter(client.models.list(config={"page_size": 1})), None)
        return True
    except Exception as error:
        text = str(error)
        if any(mark in text for mark in ("API_KEY_INVALID", "API key not valid", "PERMISSION_DENIED", "401", "403", "400")):
            return False
        print(f"   Kalitni hozir tekshirib bo‘lmadi ({type(error).__name__}). Internetni tekshiring, kalit saqlanadi.")
        return None


def ask_gemini():
    print()
    print(" 1-qadam. Gemini API kaliti")
    print(f"   Brauzerda {GEMINI_PAGE} ochiladi.")
    print("   Google akkauntingiz bilan kiring, «Create API key» ni bosing va kalitni nusxalang.")
    webbrowser.open(GEMINI_PAGE)
    while True:
        key = getpass("   Kalitni shu yerga qo‘ying (yozuv ko‘rinmaydi) va Enter bosing: ").strip()
        if not key:
            print("   Kalit bo‘sh. Qaytadan qo‘ying.")
            continue
        print(f"   Qabul qilindi: {masked(key)}. Tekshirilmoqda...")
        if gemini_works(key) is False:
            print("   Google bu kalitni qabul qilmadi. To‘liq nusxalanganini tekshirib, qaytadan qo‘ying.")
            continue
        print("   ✓ Gemini kaliti ishlaydi.")
        return key


def ask_telegram_api():
    print()
    print(" 2-qadam. Telegram API ID va API hash")
    print(f"   Brauzerda {TELEGRAM_PAGE} ochiladi.")
    print("   Telefon raqamingiz bilan kiring. Kod Telegram ilovasiga keladi.")
    print("   «API development tools» bo‘limida istalgan nom bilan ilova yarating")
    print("   (masalan App title: Voice Agency, Short name: voiceagency, Platform: Desktop).")
    print("   Keyin «App api_id» va «App api_hash» qiymatlarini nusxalang.")
    webbrowser.open(TELEGRAM_PAGE)
    while True:
        api_id = input("   App api_id (faqat raqam): ").strip()
        if valid_api_id(api_id):
            break
        print("   api_id faqat raqamlardan iborat bo‘ladi, masalan 12345678. Qaytadan kiriting.")
    while True:
        api_hash = getpass("   App api_hash (32 belgi, yozuv ko‘rinmaydi): ").strip()
        if valid_api_hash(api_hash):
            break
        print(f"   api_hash 32 ta belgidan iborat bo‘lishi kerak, siz {len(api_hash)} ta kiritdingiz. Qaytadan qo‘ying.")
    print(f"   ✓ Qabul qilindi: api_id {api_id}, api_hash {masked(api_hash)}.")
    return api_id, api_hash


def sign_in(api_id, api_hash, reset=False):
    from telethon.errors import ApiIdInvalidError
    from telethon.sync import TelegramClient

    print()
    print(" 3-qadam. Telegram akkauntiga ulanish")
    SESSION_DIR.mkdir(exist_ok=True)
    session_file = SESSION.with_suffix(".session")
    if reset and session_file.exists():
        session_file.unlink()
    if session_file.exists():
        print("   Saqlangan sessiya tekshirilmoqda...")
    else:
        print("   Robot qaysi akkauntga kelgan qo‘ng‘iroqlarga javob bersa, o‘sha akkaunt raqamini kiriting.")
        print("   Bu oddiy Telegram akkaunti bo‘ladi, bot emas.")
    client = TelegramClient(str(SESSION), int(api_id), api_hash)
    client.session.save_entities = False
    try:
        client.start(
            phone=lambda: input("   Telefon raqam (+998901234567): ").strip(),
            code_callback=lambda: input("   Telegram ilovasiga kelgan kod: ").strip(),
            password=lambda: getpass("   Ikki bosqichli tasdiqlash paroli (yozuv ko‘rinmaydi): "),
            max_attempts=3,
        )
        me = client.get_me()
        if me is None:
            print("   Telegram akkauntni tasdiqlamadi.")
            return False
        name = " ".join(part for part in (me.first_name, me.last_name) if part) or "akkaunt"
        print(f"   ✓ Telegram ulandi: {name}" + (f" (@{me.username})" if me.username else "") + ".")
        return True
    except ApiIdInvalidError:
        print("   Telegram bu api_id va api_hash juftligini qabul qilmadi. Ularni qayta kiritish kerak.")
        return None
    finally:
        client.disconnect()


def main():
    parser = argparse.ArgumentParser(description="Voice Agency 404 setup")
    parser.add_argument("--check", action="store_true", help="Validate .env without network or sign-in.")
    parser.add_argument("--setup", action="store_true", help="Ask for missing or invalid keys, then sign in.")
    parser.add_argument("--reset", action="store_true", help="Ask for every key again and sign in again.")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")

    config = {k: (v or "").strip() for k, v in dotenv_values(ENV_FILE, encoding="utf-8-sig", interpolate=False).items()}
    bad = problems(config)

    if args.check:
        if bad:
            parser.exit(1, "Sozlanmagan yoki noto‘g‘ri: " + ", ".join(bad) + "\n")
        print("Kalitlar joyida. Telegram sessiyasi: " + ("bor" if SESSION.with_suffix(".session").exists() else "yo‘q"))
        return

    if args.reset:
        bad = ["GEMINI_API_KEY", "TELEGRAM_API_ID", "TELEGRAM_API_HASH"]
    if bad:
        print()
        print(" Voice Agency 404 sozlash ustasi")
        print(" Kalitlar faqat shu kompyuterdagi .env fayliga yoziladi va GitHub’ga yuborilmaydi.")
    ENV_FILE.touch(exist_ok=True)

    while True:
        if "GEMINI_API_KEY" in bad:
            config["GEMINI_API_KEY"] = ask_gemini()
            set_key(ENV_FILE, "GEMINI_API_KEY", config["GEMINI_API_KEY"], encoding="utf-8-sig")
        if "TELEGRAM_API_ID" in bad or "TELEGRAM_API_HASH" in bad:
            config["TELEGRAM_API_ID"], config["TELEGRAM_API_HASH"] = ask_telegram_api()
            set_key(ENV_FILE, "TELEGRAM_API_ID", config["TELEGRAM_API_ID"], encoding="utf-8-sig")
            set_key(ENV_FILE, "TELEGRAM_API_HASH", config["TELEGRAM_API_HASH"], encoding="utf-8-sig")
        result = sign_in(config["TELEGRAM_API_ID"], config["TELEGRAM_API_HASH"], reset=args.reset)
        if result is None:
            bad = ["TELEGRAM_API_ID", "TELEGRAM_API_HASH"]
            args.reset = False
            continue
        if not result:
            parser.exit(1)
        break
    print()
    print(" ✓ Sozlash tugadi. Robot va dashboard ishga tushadi.")


if __name__ == "__main__":
    main()
