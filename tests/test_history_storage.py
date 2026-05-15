import os
import tempfile
import unittest

import app


class HistoryStorageTest(unittest.TestCase):
    def test_server_reuses_address_between_restarts(self):
        self.assertTrue(app.ReusableTCPServer.allow_reuse_address)

    def test_save_history_records_limits_and_loads_json_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = app.HISTORY_FILE
            app.HISTORY_FILE = os.path.join(tmp, "history_records.json")
            try:
                items = [{"id": i, "filtered": [str(i).zfill(3)]} for i in range(100)]

                saved = app.save_history_records(items)

                self.assertEqual(80, len(saved))
                self.assertEqual(0, saved[0]["id"])
                self.assertEqual(79, saved[-1]["id"])
                self.assertEqual(saved, app.load_history_records())
            finally:
                app.HISTORY_FILE = original

    def test_load_history_records_returns_empty_list_for_bad_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = app.HISTORY_FILE
            app.HISTORY_FILE = os.path.join(tmp, "history_records.json")
            try:
                with open(app.HISTORY_FILE, "w", encoding="utf-8") as f:
                    f.write("{bad json")

                self.assertEqual([], app.load_history_records())
            finally:
                app.HISTORY_FILE = original


if __name__ == "__main__":
    unittest.main()
