from contextlib import closing
from datetime import date, datetime, time, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
UZ = timezone(timedelta(hours=5))
TARIFFS = {
    "diagnostic": ("Umumiy diagnostika", 100000, 150000),
    "brakes": ("Tormoz tekshiruvi", 100000, 180000),
    "oil": ("Moy almashtirish (ish haqi)", 80000, 120000),
    "electrical": ("Elektr tizimi diagnostikasi", 120000, 220000),
}
WORKERS = {
    "diagnostic": ("Aziz", 30), "brakes": ("Aziz", 45),
    "oil": ("Bekzod", 30), "electrical": ("Bekzod", 60),
}
SERVICE_STAFF = {TARIFFS[key][0]: assignment for key, assignment in WORKERS.items()}
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
    required = {"previous_slot": "TEXT", "move_requested": "INTEGER NOT NULL DEFAULT 0",
                "reminder": "TEXT"}
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


def save_request(caller_id, username, car, issue, service, wants_visit, phone="", request_id=None, visit_time="", visit_date=""):
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
        connection.execute("""INSERT INTO requests VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET username=excluded.username, phone=excluded.phone,
            visit=excluded.visit, car=excluded.car, issue=excluded.issue,
            service=excluded.service, low=excluded.low, high=excluded.high""",
                           (request_id, now.isoformat(), visit, caller_id, username, phone,
                            car, issue, label, low, high))
    return request_id, visit, label, low, high


class Dashboard(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            body = (ROOT / "dashboard.html").read_bytes()
            content_type = "text/html; charset=utf-8"
        elif self.path == "/api/requests":
            with closing(database()) as connection:
                rows = connection.execute("SELECT r.*, d.status, d.slot, d.delivery, d.previous_slot, d.move_requested, d.reminder, c.reason AS callback, c.done AS callback_done, x.worker AS assigned_worker, x.consent, x.waitlist, x.attendance FROM requests r LEFT JOIN decisions d ON d.request_id = r.id LEFT JOIN callbacks c ON c.request_id = r.id LEFT JOIN dispatch x ON x.request_id = r.id ORDER BY r.created DESC")
                body = json.dumps([dict(row, worker=row["assigned_worker"] or staff(row["service"])[0], duration=staff(row["service"])[1]) for row in rows], ensure_ascii=False).encode()
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
        if (self.path != "/api/decision" or self.headers.get_content_type() != "application/json"
                or self.headers.get("Origin") not in (f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}")):
            self.send_error(403)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 2048:
                raise ValueError("Invalid request size.")
            payload = json.loads(self.rfile.read(length))
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
        request = connection.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
        if not request:
            raise ValueError("Murojaat topilmadi.")
        if action == "assign":
            if slot not in {name for name, _ in WORKERS.values()}:
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
        if action == "reject" and previous_slot:
            raise ValueError("Eski bron saqlangan. Boshqa vaqtni taklif qiling.")
        if action == "reject":
            status, slot = "rejected", None
            notice = "So'ragan vaqtingizga avtoservis qabul qila olmaydi."
        elif action in ("accept", "offer"):
            slot = request["visit"] if action == "accept" else slot
            try:
                when = datetime.fromisoformat(slot or "")
                if len(slot) != 16 or when.tzinfo or when.replace(tzinfo=UZ) <= datetime.now(UZ):
                    raise ValueError
            except (ValueError, TypeError):
                raise ValueError("Kelajakdagi sana va aniq vaqtni tanlang.") from None
            end = when + timedelta(minutes=staff(request["service"])[1])
            if when.time() < time(9) or end > when.replace(hour=18, minute=0):
                raise ValueError("Usta jadvali 09:00 dan 18:00 gacha.")
            slot = when.isoformat(timespec="minutes")
            label = slot.replace("T", " ")
            worker = assigned_staff(connection, request["service"], request_id)
            status = "accepted" if action == "accept" else "offered"
            notice = (f"Bo'ldi, {label} da {worker} usta sizga xizmat korsatadi. Diagnostikaga keling. Vaqtni ko'chirish uchun KOCHIR {request_id} deb yozing." if action == "accept" else
                      f"{label} da {worker} ustaga diagnostikaga kela olasizmi? Ushbu xabarga Bo'ladi deb javob bering "
                      f"yoki BO'LADI {request_id} deb yozing.")
        else:
            raise ValueError("Amal tanlanmagan.")
        if slot and not slot_available(connection, request["service"], slot, request_id):
            raise ValueError("Bu ustaning vaqti band.")
        connection.execute("""INSERT INTO decisions
            (request_id,status,slot,notice,delivery,previous_slot,reminder)
            VALUES (?, ?, ?, ?, 'queued', ?, NULL)
            ON CONFLICT(request_id) DO UPDATE SET status=excluded.status, slot=excluded.slot,
            notice=excluded.notice, delivery='queued', message_id=NULL,
            previous_slot=excluded.previous_slot, move_requested=0, reminder=NULL""",
                           (request_id, status, slot, notice, previous_slot))


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


def available_slots(service, requested_date="", request_id=None):
    now = datetime.now(UZ)
    try:
        day = date.fromisoformat(requested_date) if requested_date else now.date()
    except ValueError:
        day = now.date()
    with closing(database()) as connection:
        options = []
        for offset in range(4):
            for index in range(18, 36):
                candidate = datetime.combine(day + timedelta(days=offset), time(index // 2, index % 2 * 30), UZ)
                if candidate <= now or candidate + timedelta(minutes=staff(service)[1]) > candidate.replace(hour=18, minute=0):
                    continue
                slot = candidate.replace(tzinfo=None).isoformat(timespec="minutes")
                if slot_available(connection, service, slot, request_id):
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
                f"Eslatma: {label} da avtoservisga tashrifingiz bor. Vaqtni ko'chirish uchun KOCHIR {code} deb yozing."
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

def confirm_offer(caller_id, message_id, request_id):
    with closing(database()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        offer = connection.execute("""SELECT d.*, r.service FROM decisions d JOIN requests r ON r.id=d.request_id
            WHERE r.caller_id=? AND d.status='offered' AND d.delivery='sent'
            AND ((? IS NOT NULL AND d.message_id=?) OR d.request_id=?)""",
                                   (caller_id, message_id, message_id, request_id)).fetchone()
        if not offer or datetime.fromisoformat(offer["slot"]).replace(tzinfo=UZ) <= datetime.now(UZ):
            return False
        label = offer["slot"].replace("T", " ")
        worker = assigned_staff(connection, offer["service"], offer["request_id"])
        connection.execute("""UPDATE decisions SET status='accepted', delivery='queued',
            notice=?, message_id=NULL, previous_slot=NULL, move_requested=0, reminder=NULL WHERE request_id=?""",
                           (f"Bo'ldi, {label} da {worker} usta sizga xizmat korsatadi. Diagnostikaga keling. Vaqtni ko'chirish uchun KOCHIR {offer['request_id']} deb yozing.", offer["request_id"]))
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
        if start.time() < time(9) or start + timedelta(minutes=staff(candidate["service"])[1]) > start.replace(hour=18, minute=0):
            return None
        if not slot_available(connection, candidate["service"], slot, candidate["id"], job["worker"]):
            return None
        connection.execute("""INSERT INTO decisions(request_id,status,slot,notice,delivery)
            VALUES (?, 'accepted', ?, ?, 'queued') ON CONFLICT(request_id) DO UPDATE SET
            status='accepted', slot=excluded.slot, notice=excluded.notice, delivery='queued',
            message_id=NULL, previous_slot=NULL, move_requested=0, reminder=NULL""",
            (candidate["id"], slot, f"{slot.replace('T', ' ')} da {job['worker']} usta sizga xizmat korsatadi."))
        connection.execute("UPDATE dispatch SET worker=?, waitlist=0, attendance=NULL WHERE request_id=?",
                           (job["worker"], candidate["id"]))
        return slot
