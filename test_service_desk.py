from contextlib import closing
from datetime import datetime, timedelta
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch

import service_desk as desk


class BookingTests(TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        database = patch.object(desk, "DB", Path(folder.name) / "service.sqlite3")
        database.start()
        self.addCleanup(database.stop)
        self.day = (datetime.now(desk.UZ).date() + timedelta(days=1)).isoformat()

    def request(self, service="brakes", at="10:00"):
        return desk.save_request(42, "demo", "Cobalt", "Noise", service, True,
                                 visit_date=self.day, visit_time=at)[0]

    def test_previous_offer_code_cannot_confirm_replacement(self):
        request_id = self.request()
        desk.decide(request_id, "offer", self.day + "T10:00")
        old_code = desk.pending_messages()[0]["notice"].split()[-3]
        desk.delivery_result(request_id, 100)
        desk.decide(request_id, "offer", self.day + "T11:00")
        new_code = desk.pending_messages()[0]["notice"].split()[-3]
        desk.delivery_result(request_id, 101)
        self.assertFalse(desk.confirm_offer(42, None, old_code))
        self.assertFalse(desk.confirm_offer(42, 100, None))
        self.assertFalse(desk.confirm_offer(77, None, new_code))
        self.assertTrue(desk.confirm_offer(42, None, new_code))

    def test_saved_conversation_cannot_change_reserved_service(self):
        request_id = self.request()
        desk.decide(request_id, "accept")
        desk.save_request(42, "demo", "Cobalt", "Updated noise", "electrical", True,
                          request_id=request_id, visit_date=self.day, visit_time="10:00")
        with closing(desk.database()) as connection:
            row = connection.execute("SELECT service, issue FROM requests WHERE id=?", (request_id,)).fetchone()
        self.assertEqual(row["service"], desk.TARIFFS["brakes"][0])
        self.assertEqual(row["issue"], "Updated noise")

    def test_staff_can_accept_when_caller_did_not_give_time(self):
        request_id = self.request(at="")
        desk.decide(request_id, "accept", self.day + "T10:30")
        notice = desk.pending_messages()[0]
        self.assertEqual(notice["status"], "accepted")
        self.assertEqual(notice["slot"], self.day + "T10:30")

    def test_banket_deposit_and_room_conflict(self):
        def banquet(at):
            return desk.save_request(42, "demo", "Ali", "20 guests, osh", "banquet", True,
                                     visit_date=self.day, visit_time=at, business="restaurant")[0]

        first = banquet("19:30")
        with self.assertRaises(ValueError):
            desk.decide(first, "accept")
        desk.decide(first, "deposit_paid")
        desk.decide(first, "accept")
        self.assertIn("Banket zali", desk.pending_messages()[0]["notice"])
        overlap = banquet("20:00")
        desk.decide(overlap, "deposit_paid")
        with self.assertRaises(ValueError):
            desk.decide(overlap, "accept")

    def test_operator_can_classify_transcript_into_room(self):
        request_id = desk.save_request(42, "demo", "", "20 guests", None, False, business="restaurant")[0]
        with self.assertRaises(ValueError):
            desk.decide(request_id, "set_service", "brakes")
        desk.decide(request_id, "set_service", "private_room")
        desk.decide(request_id, "deposit_paid")
        desk.decide(request_id, "accept", self.day + "T18:30")
        self.assertIn("Oila xonasi", desk.pending_messages()[0]["notice"])

    def test_specific_future_day_and_exact_banket_time(self):
        future = (datetime.now(desk.UZ).date() + timedelta(days=2)).isoformat()
        service = desk.TARIFFS["banquet"][0]
        exact = future + "T10:00"
        slots = desk.available_slots(service, future)
        self.assertEqual(slots[0], exact)
        self.assertTrue(all(slot.startswith(future + "T") for slot in slots))
        self.assertIsNone(desk.check_slot(service, exact))
        self.assertIsNone(desk.check_slot(service, future + "T10:15"))

    def test_move_request_needs_matching_caller(self):
        request_id = self.request()
        desk.decide(request_id, "accept")
        desk.delivery_result(request_id, 200)
        self.assertFalse(desk.request_move(77, None, request_id))
        self.assertTrue(desk.request_move(42, None, request_id))

    def test_live_call_is_cleared_only_by_same_caller(self):
        desk.set_live_call(42, "abc")
        self.addCleanup(desk.clear_live_call)
        self.assertEqual(desk.live_call()["request_id"], "abc")
        desk.clear_live_call(77)
        self.assertTrue(desk.live_call()["active"])
        desk.clear_live_call(42)
        self.assertFalse(desk.live_call()["active"])

    def test_dashboard_rejects_foreign_host(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), desk.Dashboard)
        self.addCleanup(server.server_close)
        Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        port = server.server_address[1]

        def status(host):
            connection = HTTPConnection("127.0.0.1", port, timeout=5)
            connection.request("GET", "/api/live", headers={"Host": host})
            response = connection.getresponse()
            response.read()
            connection.close()
            return response.status

        self.assertEqual(status(desk.LOCAL_HOSTS[0]), 200)
        self.assertEqual(status("evil.example:8744"), 403)

    def test_active_business_persists(self):
        self.assertEqual(desk.active_business(), "auto")
        desk.set_business("photo")
        self.assertEqual(desk.active_business(), "photo")
        with self.assertRaises(ValueError):
            desk.set_business("unknown")


if __name__ == "__main__":
    main()
