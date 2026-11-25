from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
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


if __name__ == "__main__":
    main()
