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
    connection.execute("""CREATE UNIQUE INDEX IF NOT EXISTS unique_reserved_slot
        ON decisions(slot) WHERE status IN ('accepted', 'offered')""")
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
                rows = connection.execute("SELECT r.*, d.status, d.slot, d.delivery FROM requests r LEFT JOIN decisions d ON d.request_id = r.id ORDER BY r.created DESC")
                body = json.dumps([dict(row) for row in rows], ensure_ascii=False).encode()
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
            decide(payload["id"], payload["action"], payload.get("slot"))
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
        if not request["issue"]:
            raise ValueError("Mijoz tafsilotlari hali kiritilmagan.")
        previous = connection.execute("SELECT * FROM decisions WHERE request_id=?", (request_id,)).fetchone()
        if action == "retry" and previous and previous["delivery"] == "failed":
            connection.execute("UPDATE decisions SET delivery='queued' WHERE request_id=?", (request_id,))
            return
        if previous and (previous["status"] == "accepted" or previous["delivery"] == "queued"):
            raise ValueError("Bu murojaat band qilingan yoki xabari yuborilmoqda.")
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
            slot = when.isoformat(timespec="minutes")
            label = slot.replace("T", " ")
            status = "accepted" if action == "accept" else "offered"
            notice = (f"Bo'ldi, {label} da diagnostikaga keling." if action == "accept" else
                      f"{label} da diagnostikaga kela olasizmi? Ushbu xabarga Bo'ladi deb javob bering "
                      f"yoki BO'LADI {request_id} deb yozing.")
        else:
            raise ValueError("Amal tanlanmagan.")
        if slot:
            starts = datetime.fromisoformat(slot)
            before = (starts - timedelta(minutes=30)).isoformat(timespec="minutes")
            after = (starts + timedelta(minutes=30)).isoformat(timespec="minutes")
            collision = connection.execute("""SELECT 1 FROM decisions
                WHERE status IN ('accepted', 'offered') AND request_id<>?
                AND slot>? AND slot<?""", (request_id, before, after)).fetchone()
            if collision:
                raise ValueError("Bu vaqt band yoki boshqa mijozga taklif qilingan.")
        try:
            connection.execute("""INSERT INTO decisions VALUES (?, ?, ?, ?, 'queued', NULL)
                ON CONFLICT(request_id) DO UPDATE SET status=excluded.status, slot=excluded.slot,
                notice=excluded.notice, delivery='queued', message_id=NULL""",
                               (request_id, status, slot, notice))
        except sqlite3.IntegrityError:
            raise ValueError("Bu vaqt band yoki boshqa mijozga taklif qilingan.") from None


def pending_messages():
    with closing(database()) as connection:
        return connection.execute("""SELECT d.*, r.caller_id, r.username FROM decisions d
            JOIN requests r ON r.id=d.request_id WHERE d.delivery='queued'""").fetchall()


def delivery_result(request_id, message_id=None):
    with closing(database()) as connection, connection:
        connection.execute("UPDATE decisions SET delivery=?, message_id=? WHERE request_id=?",
                           ("sent" if message_id else "failed", message_id, request_id))


def confirm_offer(caller_id, message_id, request_id):
    with closing(database()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        offer = connection.execute("""SELECT d.* FROM decisions d JOIN requests r ON r.id=d.request_id
            WHERE r.caller_id=? AND d.status='offered' AND d.delivery='sent'
            AND ((? IS NOT NULL AND d.message_id=?) OR d.request_id=?)""",
                                   (caller_id, message_id, message_id, request_id)).fetchone()
        if not offer or datetime.fromisoformat(offer["slot"]).replace(tzinfo=UZ) <= datetime.now(UZ):
            return False
        label = offer["slot"].replace("T", " ")
        connection.execute("""UPDATE decisions SET status='accepted', delivery='queued',
            notice=?, message_id=NULL WHERE request_id=?""",
                           (f"Bo'ldi, {label} da diagnostikaga keling.", offer["request_id"]))
        return True
