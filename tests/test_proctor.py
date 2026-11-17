"""State and warning rules shared by both proctored assessment types."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from job_hunting_agent import db, ops_db, proctor


class ProctorStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old = (db.DATA_DIR, db.DATABASE_URL, db.IS_POSTGRES)
        self.addCleanup(self._restore)
        db.DATA_DIR = Path(self.tmp.name)
        db.DATABASE_URL = f"sqlite:///{db.DATA_DIR / 'test.db'}"
        db.IS_POSTGRES = False
        db.init_db()
        proctor.start("candidate@example.com", "mock_test", 1)

    def _restore(self):
        db.DATA_DIR, db.DATABASE_URL, db.IS_POSTGRES = self.old

    def test_two_warnings_then_termination_and_no_resumption(self):
        email = "candidate@example.com"
        first = proctor.report(email, "mock_test", 1, event_id="one", signal="tab_hidden")
        self.assertEqual((first["status"], first["warnings"]), ("active", 1))
        self.assertEqual(proctor.report(email, "mock_test", 1, event_id="one", signal="tab_hidden")["warnings"], 1)
        self.assertEqual(proctor.report(email, "mock_test", 1, event_id="burst", signal="tab_hidden")["warnings"], 1)
        second = proctor.report(email, "mock_test", 1, event_id="two", signal="multiple_faces")
        self.assertEqual((second["status"], second["warnings"]), ("active", 2))
        third = proctor.report(email, "mock_test", 1, event_id="three", signal="device_visible")
        self.assertEqual((third["status"], third["warnings"]), ("terminated", 3))
        with self.assertRaises(ValueError):
            proctor.require_active(email, "mock_test", 1)
        proctor.finish(email, "mock_test", 1)
        self.assertEqual(proctor.state(email, "mock_test", 1)["status"], "terminated")

    def test_lost_heartbeat_terminates_and_user_deletion_erases_events(self):
        email = "candidate@example.com"
        proctor.report(email, "mock_test", 1, event_id="one", signal="tab_hidden")
        with db.connection() as conn:
            ops_db._q(conn, "UPDATE assessment_proctor SET last_seen = 1 WHERE user_email = ?", (email,))
        with patch.object(proctor.time, "time", return_value=100):
            self.assertEqual(proctor.heartbeat(email, "mock_test", 1)["status"], "terminated")
        ops_db.delete_user_rows(email)
        self.assertIsNone(proctor.state(email, "mock_test", 1))
        self.assertEqual(proctor.events(email), [])


if __name__ == "__main__":
    unittest.main()
