from contextlib import closing
from datetime import date, datetime, time, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from business_profiles import BUSINESSES, BY_LABEL, CATALOG

ROOT = Path(__file__).resolve().parent
UZ = timezone(timedelta(hours=5))
TARIFFS = {key: item[1:4] for key, item in CATALOG.items()}
WORKERS = {key: item[4:6] for key, item in CATALOG.items()}
SERVICE_STAFF = {label: item[4:6] for label, item in BY_LABEL.items()}
DB = ROOT / ".data" / "service.sqlite3"
PORT = 8744


def database():
    DB.parent.mkdir(exist_ok=True)
    connection = sqlite3.connect(DB)
    connection.row_factory = sqlite3.Row
    connection.execute("""CREATE TABLE IF NOT EXISTS requests (
        id TEXT PRIMARY KEY, created TEXT NOT NULL, visit TEXT,
        caller_id INTEGER NOT NULL, username TEXT, phone TEXT,
        car TEXT NOT NULL, issue TEXT NOT NULL, service TEXT NOT NULL,
        low INTEGER NOT NULL, high INTEGER NOT NULL
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS decisions (
        request_id TEXT PRIMARY KEY, status TEXT NOT NULL, slot TEXT,
        notice TEXT NOT NULL, delivery TEXT NOT NULL, message_id INTEGER
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS callbacks (
        request_id TEXT PRIMARY KEY, reason TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS dispatch (
        request_id TEXT PRIMARY KEY, worker TEXT, consent INTEGER NOT NULL DEFAULT 0,
        waitlist INTEGER NOT NULL DEFAULT 0, dialed_slot TEXT, attendance TEXT
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS request_languages (
        request_id TEXT PRIMARY KEY, language TEXT NOT NULL
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS request_business (
        request_id TEXT PRIMARY KEY, business TEXT NOT NULL, deposit_paid INTEGER NOT NULL DEFAULT 0
    )""")
    details = {"guests": "INTEGER", "visit_until": "TEXT", "menu_items": "TEXT", "menu_edited": "INTEGER NOT NULL DEFAULT 0"}
    business_columns = {row["name"] for row in connection.execute("PRAGMA table_info(request_business)")}
    if details.keys() - business_columns:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            business_columns = {row["name"] for row in connection.execute("PRAGMA table_info(request_business)")}
            for name, definition in details.items():
                if name not in business_columns:
                    connection.execute(f"ALTER TABLE request_business ADD COLUMN {name} {definition}")
    connection.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY, value TEXT NOT NULL
    )""")
    required = {"previous_slot": "TEXT", "move_requested": "INTEGER NOT NULL DEFAULT 0",
                "reminder": "TEXT", "offer_code": "TEXT"}
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(decisions)")}
    if required.keys() - columns or connection.execute(
        "SELECT 1 FROM sqlite_master WHERE name='unique_reserved_slot'"
    ).fetchone():
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(decisions)")}
            for name, definition in required.items():
                if name not in columns:
                    connection.execute(f"ALTER TABLE decisions ADD COLUMN {name} {definition}")
            connection.execute("DROP INDEX IF EXISTS unique_reserved_slot")
    return connection


def active_business():
    with closing(database()) as connection:
        row = connection.execute("SELECT value FROM settings WHERE key='business'").fetchone()
    return row["value"] if row else "auto"


def set_business(business):
    if business not in BUSINESSES:
        raise ValueError("Xizmat yo‘nalishi topilmadi.")
    with closing(database()) as connection, connection:
        connection.execute("INSERT OR REPLACE INTO settings VALUES ('business', ?)", (business,))


def business_for(service):
    return BUSINESSES[BY_LABEL.get(service, CATALOG["diagnostic"])[0]]


def deposit_for(service):
    return BY_LABEL.get(service, CATALOG["diagnostic"])[6]


def booking_notice(request_id, slot, worker, service):
    role = business_for(service).resource
    deposit = deposit_for(service)
    details = f" Omonat qayd qilindi ({deposit:,} so‘m)." if deposit else ""
    return (f"Bron tasdiqlandi. {slot.replace('T', ' ')}. {role}: {worker}.{details} "
            f"Vaqtni ko‘chirish uchun KOCHIR {request_id} deb yozing.")


def clean_menu(items):
    return list(dict.fromkeys(item.strip()[:120] for item in items[:30]
                              if isinstance(item, str) and item.strip()))


def save_request(caller_id, username, car, issue, service, wants_visit, phone="", request_id=None, visit_time="", visit_date="", business="auto", guests=None, visit_until=None, menu_items=None):
    now = datetime.now(UZ)
    visit = None
    if wants_visit:
        try:
            requested = date.fromisoformat(visit_date) if visit_date else now.date() + timedelta(days=1)
            if requested >= now.date():
                visit = requested.isoformat()
        except ValueError:
            pass
    if visit and visit_time:
        try:
            visit += "T" + time.fromisoformat(visit_time).strftime("%H:%M")
        except ValueError:
            pass
    label, low, high = TARIFFS[service] if service else ("Qo'ng'iroq", 0, 0)
    request_id = request_id or uuid4().hex[:12]
    with closing(database()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        reserved = connection.execute("""SELECT r.visit, r.service, r.low, r.high
            FROM requests r JOIN decisions d ON d.request_id=r.id
            WHERE r.id=? AND d.status IN ('accepted', 'offered')""", (request_id,)).fetchone()
        if reserved:
            visit, label, low, high = reserved
        connection.execute("""INSERT OR IGNORE INTO request_business(request_id, business)
            VALUES (?, ?)""", (request_id, business))
        if not reserved and business == "restaurant" and visit and "T" in visit:
            connection.execute("""UPDATE request_business SET guests=COALESCE(?, guests),
                visit_until=COALESCE(?, visit_until) WHERE request_id=?""",
                               (guests, visit_until, request_id))
        if business == "restaurant" and menu_items and not reserved:
            connection.execute("""UPDATE request_business SET menu_items=?
                WHERE request_id=? AND menu_edited=0""", (json.dumps(clean_menu(menu_items), ensure_ascii=False), request_id))
        if not reserved:
            connection.execute("""UPDATE request_business SET deposit_paid=0
                WHERE request_id=? AND EXISTS (SELECT 1 FROM requests WHERE id=? AND service<>?)""",
                               (request_id, request_id, label))
        connection.execute("""INSERT INTO requests VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET username=excluded.username, phone=excluded.phone,
            visit=excluded.visit, car=excluded.car, issue=excluded.issue,
            service=excluded.service, low=excluded.low, high=excluded.high""",
                           (request_id, now.isoformat(), visit, caller_id, username, phone,
                            car, issue, label, low, high))
    return request_id, visit, label, low, high


def save_transcript_note(request_id, text):
    with closing(database()) as connection, connection:
        connection.execute("UPDATE requests SET issue=? WHERE id=? AND service=?",
                           (text, request_id, "Qo'ng'iroq"))


class Dashboard(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            body = (ROOT / "dashboard.html").read_bytes()
            content_type = "text/html; charset=utf-8"
        elif self.path == "/api/business":
            body = json.dumps({"active": active_business(), "profiles": [
                dict(id=key, name=profile.name, resource=profile.resource,
                     opens=profile.opens, closes=profile.closes,
                     resources=list(dict.fromkeys(CATALOG[item][4] for item in profile.services(key))),
                     services=[dict(id=item, label=CATALOG[item][1], resource=CATALOG[item][4])
                               for item in profile.services(key)])
                for key, profile in BUSINESSES.items()
            ]}, ensure_ascii=False).encode()
            content_type = "application/json; charset=utf-8"
        elif self.path == "/api/requests":
            with closing(database()) as connection:
                rows = connection.execute("SELECT r.*, d.status, d.slot, d.delivery, d.previous_slot, d.move_requested, d.reminder, c.reason AS callback, c.done AS callback_done, x.worker AS assigned_worker, x.consent, x.waitlist, x.attendance, COALESCE(b.business, 'auto') AS business, COALESCE(b.deposit_paid, 0) AS deposit_paid, b.guests, b.visit_until, b.menu_items FROM requests r LEFT JOIN request_business b ON b.request_id=r.id LEFT JOIN decisions d ON d.request_id = r.id LEFT JOIN callbacks c ON c.request_id = r.id LEFT JOIN dispatch x ON x.request_id = r.id ORDER BY r.created DESC")
                body = json.dumps([dict(row, worker=row["assigned_worker"] or staff(row["service"])[0], duration=staff(row["service"])[1], deposit=deposit_for(row["service"]), menu_items=json.loads(row["menu_items"] or "[]")) for row in rows], ensure_ascii=False).encode()
            content_type = "application/json; charset=utf-8"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if (self.path not in ("/api/decision", "/api/business") or self.headers.get_content_type() != "application/json"
                or self.headers.get("Origin") not in (f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}")):
            self.send_error(403)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 2048:
                raise ValueError("Invalid request size.")
            payload = json.loads(self.rfile.read(length))
            if self.path == "/api/business":
                set_business(payload["business"])
            else:
                decide(payload["id"], payload["action"], payload.get("worker") if payload["action"] == "assign" else payload.get("slot"))
            body, status = {"ok": True}, 200
        except (ValueError, KeyError, TypeError) as error:
            body, status = {"error": str(error)}, 400
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def log_message(self, *args):
        pass


def dashboard_server():
    return ThreadingHTTPServer(("127.0.0.1", PORT), Dashboard)



def decide(request_id, action, slot=None):
    with closing(database()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        request = connection.execute("""SELECT r.*, COALESCE(b.business, 'auto') AS business FROM requests r
            LEFT JOIN request_business b ON b.request_id=r.id WHERE r.id=?""", (request_id,)).fetchone()
        if not request:
            raise ValueError("Murojaat topilmadi.")
        profile = BUSINESSES[request["business"]]
        if action == "save_menu":
            if request["business"] != "restaurant" or not isinstance(slot, list):
                raise ValueError("Menyu faqat restoran kartasida tahrirlanadi.")
            items = clean_menu(slot)
            connection.execute("UPDATE request_business SET menu_items=?, menu_edited=1 WHERE request_id=?",
                               (json.dumps(items, ensure_ascii=False), request_id))
            return
        if action == "set_service":
            entry = CATALOG.get(slot) if isinstance(slot, str) else None
            if not entry or entry[0] != request["business"]:
                raise ValueError("Shu yo‘nalishdan xizmat tanlang.")
            booking = connection.execute("SELECT status FROM decisions WHERE request_id=?", (request_id,)).fetchone()
            if booking and booking["status"] in ("accepted", "offered"):
                raise ValueError("Faol bron yoki taklifda xizmatni o‘zgartirib bo‘lmaydi.")
            if request["service"] != entry[1]:
                connection.execute("UPDATE requests SET service=?, low=?, high=? WHERE id=?", (*entry[1:4], request_id))
                connection.execute("UPDATE request_business SET deposit_paid=0 WHERE request_id=?", (request_id,))
                connection.execute("UPDATE dispatch SET worker=NULL WHERE request_id=?", (request_id,))
            return
        if action == "deposit_paid":
            if not deposit_for(request["service"]):
                raise ValueError("Bu xizmatda omonat talab qilinmaydi.")
            connection.execute("UPDATE request_business SET deposit_paid=1 WHERE request_id=?", (request_id,))
            return
        if action == "assign":
            allowed = {item[4] for item in CATALOG.values() if BUSINESSES[item[0]] == profile}
            if profile.resource in {"Xona", "Studiya"}:
                allowed = {staff(request["service"])[0]}
            if slot not in allowed:
                raise ValueError("Ustani tanlang.")
            booking = connection.execute("SELECT status FROM decisions WHERE request_id=?", (request_id,)).fetchone()
            if booking and booking["status"] in ("accepted", "offered"):
                raise ValueError("Avval faol bron yoki taklif yakunlanishi kerak.")
            connection.execute("""INSERT INTO dispatch(request_id, worker) VALUES (?,?)
                ON CONFLICT(request_id) DO UPDATE SET worker=excluded.worker""", (request_id, slot))
            return
        if action == "callback_done":
            connection.execute("UPDATE callbacks SET done=1 WHERE request_id=?", (request_id,))
            return
        if not request["issue"]:
            raise ValueError("Mijoz tafsilotlari hali kiritilmagan.")
        previous = connection.execute("SELECT * FROM decisions WHERE request_id=?", (request_id,)).fetchone()
        if action == "retry" and previous and previous["delivery"] == "failed":
            connection.execute("UPDATE decisions SET delivery='queued' WHERE request_id=?", (request_id,))
            return
        moving = previous and previous["status"] == "accepted" and previous["move_requested"] and action == "offer"
        if previous and (previous["delivery"] == "queued" or (previous["status"] == "accepted" and not moving)):
            raise ValueError("Bu murojaat band qilingan yoki xabari yuborilmoqda.")
        previous_slot = (previous["slot"] if moving else previous["previous_slot"]) if previous else None
        offer_code = None
        if action == "reject" and previous_slot:
            raise ValueError("Eski bron saqlangan. Boshqa vaqtni taklif qiling.")
        if action == "reject":
            status, slot = "rejected", None
            notice = "So'ragan vaqtingizga xizmat ko‘rsata olmaymiz."
        elif action in ("accept", "offer"):
            if request["service"] not in BY_LABEL:
                raise ValueError("Avval xizmatni tanlang.")
            if deposit_for(request["service"]):
                payment = connection.execute("SELECT deposit_paid FROM request_business WHERE request_id=?", (request_id,)).fetchone()
                if not payment or not payment["deposit_paid"]:
                    raise ValueError("Avval tashqarida olingan omonatni qayd qiling.")
            slot = (slot or request["visit"]) if action == "accept" else slot
            with_error = booking_error(connection, request["service"], slot, request_id)
            if with_error:
                raise ValueError(with_error)
            label = slot.replace("T", " ")
            worker = assigned_staff(connection, request["service"], request_id)
            status = "accepted" if action == "accept" else "offered"
            if status == "offered":
                offer_code = uuid4().hex[:12]
            notice = (booking_notice(request_id, slot, worker, request["service"]) if action == "accept" else
                      f"{label}. {profile.resource}: {worker}. Shu vaqt sizga qulaymi? "
                      f"Ushbu xabarga Bo‘ladi deb javob bering yoki BO'LADI {offer_code} deb yozing.")
        else:
            raise ValueError("Amal tanlanmagan.")
        connection.execute("""INSERT INTO decisions
            (request_id,status,slot,notice,delivery,previous_slot,reminder,offer_code)
            VALUES (?, ?, ?, ?, 'queued', ?, NULL, ?)
            ON CONFLICT(request_id) DO UPDATE SET status=excluded.status, slot=excluded.slot,
            notice=excluded.notice, delivery='queued', message_id=NULL,
            previous_slot=excluded.previous_slot, move_requested=0, reminder=NULL, offer_code=excluded.offer_code""",
                           (request_id, status, slot, notice, previous_slot, offer_code))


def staff(service):
    return SERVICE_STAFF.get(service, WORKERS["diagnostic"])


def assigned_staff(connection, service, request_id):
    row = connection.execute("SELECT worker FROM dispatch WHERE request_id=?", (request_id,)).fetchone()
    return row["worker"] if row and row["worker"] else staff(service)[0]


def slot_available(connection, service, slot, exclude=None, worker_override=None):
    _, duration = staff(service)
    worker = worker_override or assigned_staff(connection, service, exclude)
    start = datetime.fromisoformat(slot)
    end = start + timedelta(minutes=duration)
    rows = connection.execute("""SELECT d.slot, d.previous_slot, r.service, d.request_id FROM decisions d
        JOIN requests r ON r.id=d.request_id WHERE d.status IN ('accepted','offered')
        AND d.request_id IS NOT ?""", (exclude,))
    for row in rows:
        _, other_duration = staff(row["service"])
        other_worker = assigned_staff(connection, row["service"], row["request_id"])
        if worker != other_worker:
            continue
        for value in (row["slot"], row["previous_slot"]):
            if value:
                other = datetime.fromisoformat(value)
                if start < other + timedelta(minutes=other_duration) and other < end:
                    return False
    return True


def booking_error(connection, service, slot, request_id=None):
    try:
        when = datetime.fromisoformat(slot or "")
        if len(slot) != 16 or when.tzinfo or when.replace(tzinfo=UZ) <= datetime.now(UZ):
            raise ValueError
    except (ValueError, TypeError):
        return "Kelajakdagi sana va aniq vaqtni tanlang."
    profile = business_for(service)
    end = when + timedelta(minutes=staff(service)[1])
    if when.time() < time(profile.opens) or end > when.replace(hour=profile.closes, minute=0):
        return f"Ish vaqti {profile.opens:02}:00 dan {profile.closes:02}:00 gacha."
    if not slot_available(connection, service, slot, request_id):
        return f"{profile.resource} bu vaqtda band."
    return None


def check_slot(service, slot, request_id=None):
    with closing(database()) as connection:
        return booking_error(connection, service, slot, request_id)


def available_slots(service, requested_date="", request_id=None):
    try:
        day = date.fromisoformat(requested_date) if requested_date else datetime.now(UZ).date()
    except ValueError:
        return []
    profile = business_for(service)
    with closing(database()) as connection:
        options = []
        for offset in range(1 if requested_date else 4):
            for index in range(profile.opens * 2, profile.closes * 2):
                candidate = datetime.combine(day + timedelta(days=offset), time(index // 2, index % 2 * 30))
                slot = candidate.isoformat(timespec="minutes")
                if not booking_error(connection, service, slot, request_id):
                    options.append(slot)
        return options


def queue_callback(request_id, reason):
    with closing(database()) as connection, connection:
        connection.execute("""INSERT INTO callbacks(request_id, reason) VALUES (?, ?)
            ON CONFLICT(request_id) DO UPDATE SET reason=excluded.reason, done=0""",
                           (request_id, reason))


def request_move(caller_id, message_id, request_id):
    with closing(database()) as connection, connection:
        cursor = connection.execute("""UPDATE decisions SET move_requested=1
            WHERE status='accepted' AND slot>? AND request_id IN (
                SELECT id FROM requests WHERE caller_id=?
            ) AND ((? IS NOT NULL AND message_id=?) OR request_id=?)""",
                                    (datetime.now(UZ).isoformat(timespec="minutes")[:16], caller_id,
                                     message_id, message_id, request_id))
        return cursor.rowcount > 0

def pending_messages():
    now = datetime.now(UZ).replace(tzinfo=None)
    with closing(database()) as connection:
        notices = [dict(row, kind="decision") for row in connection.execute("""
            SELECT d.*, r.caller_id, r.username FROM decisions d
            JOIN requests r ON r.id=d.request_id WHERE d.delivery='queued'""")]
        reminders = connection.execute("""SELECT d.request_id, d.slot, r.caller_id, r.username
            FROM decisions d JOIN requests r ON r.id=d.request_id
            WHERE d.status='accepted' AND d.delivery='sent' AND d.reminder IS NULL
            AND d.slot>? AND d.slot<=?""", (now.isoformat(), (now + timedelta(hours=1)).isoformat()))
        for row in reminders:
            label = row["slot"].replace("T", " ")
            code = row["request_id"]
            notices.append(dict(row, kind="reminder", notice=(
                f"Eslatma: {label} da tashrifingiz bor. Vaqtni ko'chirish uchun KOCHIR {code} deb yozing."
            )))
        return notices


def delivery_result(request_id, message_id=None, kind="decision"):
    delivery = "sent" if message_id else "failed"
    with closing(database()) as connection, connection:
        if kind == "reminder":
            connection.execute("UPDATE decisions SET reminder=? WHERE request_id=?", (delivery, request_id))
        else:
            connection.execute("UPDATE decisions SET delivery=?, message_id=? WHERE request_id=?",
                               (delivery, message_id, request_id))

def confirm_offer(caller_id, message_id, offer_code):
    with closing(database()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        offer = connection.execute("""SELECT d.*, r.service, b.deposit_paid FROM decisions d JOIN requests r ON r.id=d.request_id
            LEFT JOIN request_business b ON b.request_id=r.id
            WHERE r.caller_id=? AND d.status='offered' AND d.delivery='sent'
            AND ((? IS NOT NULL AND COALESCE(d.offer_code, d.request_id)=?)
                 OR (? IS NULL AND d.message_id=?))""",
                                   (caller_id, offer_code, offer_code, offer_code, message_id)).fetchone()
        if not offer or (deposit_for(offer["service"]) and not offer["deposit_paid"]) or datetime.fromisoformat(offer["slot"]).replace(tzinfo=UZ) <= datetime.now(UZ):
            return False
        worker = assigned_staff(connection, offer["service"], offer["request_id"])
        connection.execute("""UPDATE decisions SET status='accepted', delivery='queued',
            notice=?, message_id=NULL, previous_slot=NULL, move_requested=0, reminder=NULL WHERE request_id=?""",
                           (booking_notice(offer["request_id"], offer["slot"], worker, offer["service"]),
                            offer["request_id"]))
        return True



def record_contact_preferences(request_id, consent=None, waitlist=None, language=None):
    with closing(database()) as connection, connection:
        connection.execute("INSERT OR IGNORE INTO dispatch(request_id) VALUES (?)", (request_id,))
        if isinstance(language, str):
            code = language.lower().split("-")[0]
            if len(code) in (2, 3) and code.isascii() and code.isalpha():
                connection.execute("""INSERT INTO request_languages VALUES (?,?)
                    ON CONFLICT(request_id) DO UPDATE SET language=excluded.language""", (request_id, code))
        if isinstance(consent, bool):
            connection.execute("UPDATE dispatch SET consent=? WHERE request_id=?", (consent, request_id))
        if isinstance(waitlist, bool):
            connection.execute("UPDATE dispatch SET waitlist=? WHERE request_id=?", (waitlist, request_id))


def claim_attendance_call():
    now = datetime.now(UZ).replace(tzinfo=None)
    with closing(database()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("""SELECT r.id, r.caller_id, r.username, r.service, d.slot, l.language
            FROM decisions d JOIN requests r ON d.request_id=r.id JOIN dispatch x ON x.request_id=r.id
            LEFT JOIN request_languages l ON l.request_id=r.id
            WHERE d.status='accepted' AND x.consent=1 AND d.slot<=? AND d.slot>=?
            AND x.dialed_slot IS NOT d.slot ORDER BY d.slot LIMIT 1""",
          (now.isoformat(timespec="minutes"), (now-timedelta(minutes=15)).isoformat(timespec="minutes"))).fetchone()
        if row:
            connection.execute("UPDATE dispatch SET dialed_slot=?, attendance='calling' WHERE request_id=?",
                               (row["slot"], row["id"]))
            return dict(row, worker=assigned_staff(connection, row["service"], row["id"]))
    return None


def attendance_result(job, answer):
    with closing(database()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        current = connection.execute("SELECT status, slot FROM decisions WHERE request_id=?", (job["id"],)).fetchone()
        if not current or current["status"] != "accepted" or current["slot"] != job["slot"]:
            return
        connection.execute("UPDATE dispatch SET attendance=? WHERE request_id=?", (answer, job["id"]))
        if answer == "cannot_come":
            connection.execute("UPDATE decisions SET status='cancelled', slot=NULL WHERE request_id=?", (job["id"],))


def waitlist_candidates(job):
    with closing(database()) as connection:
        rows = connection.execute("""SELECT r.id, r.caller_id, r.username, r.service, d.slot, l.language
            FROM requests r JOIN dispatch x ON x.request_id=r.id
            LEFT JOIN decisions d ON d.request_id=r.id
            LEFT JOIN request_languages l ON l.request_id=r.id
            WHERE r.caller_id<>? AND x.consent=1 AND x.waitlist=1 AND r.service=?
            AND (d.status IS NULL OR d.status='accepted') AND (d.slot IS NULL OR d.slot>?)
            ORDER BY r.created""", (job["caller_id"], job["service"], job["slot"]))
        seen = set()
        candidates = []
        for row in rows:
            if row["caller_id"] not in seen:
                seen.add(row["caller_id"])
                candidates.append(dict(row))
        return candidates


def book_opening(candidate, job):
    start = datetime.now(UZ).replace(tzinfo=None, second=0, microsecond=0) + timedelta(minutes=10)
    slot = start.isoformat(timespec="minutes")
    profile = business_for(candidate["service"])
    if deposit_for(candidate["service"]):
        return None
    with closing(database()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        origin = connection.execute("SELECT status FROM decisions WHERE request_id=?", (job["id"],)).fetchone()
        eligible = connection.execute("""SELECT x.consent, x.waitlist, d.status, d.slot
            FROM dispatch x LEFT JOIN decisions d ON d.request_id=x.request_id WHERE x.request_id=?""",
                                      (candidate["id"],)).fetchone()
        if (not origin or origin["status"] != "cancelled" or not eligible
                or not eligible["consent"] or not eligible["waitlist"]
                or eligible["status"] not in (None, "accepted")
                or (eligible["slot"] and eligible["slot"] <= slot)
                or start > datetime.fromisoformat(job["slot"]) + timedelta(minutes=30)):
            return None
        if start.time() < time(profile.opens) or start + timedelta(minutes=staff(candidate["service"])[1]) > start.replace(hour=profile.closes, minute=0):
            return None
        if not slot_available(connection, candidate["service"], slot, candidate["id"], job["worker"]):
            return None
        connection.execute("""INSERT INTO decisions(request_id,status,slot,notice,delivery)
            VALUES (?, 'accepted', ?, ?, 'queued') ON CONFLICT(request_id) DO UPDATE SET
            status='accepted', slot=excluded.slot, notice=excluded.notice, delivery='queued',
            message_id=NULL, previous_slot=NULL, move_requested=0, reminder=NULL""",
            (candidate["id"], slot, booking_notice(candidate["id"], slot, job["worker"], candidate["service"])))
        connection.execute("UPDATE dispatch SET worker=?, waitlist=0, attendance=NULL WHERE request_id=?",
                           (job["worker"], candidate["id"]))
        return slot
