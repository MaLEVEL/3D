import json
import os
import tempfile
import unittest

import app


class HistoryStorageTest(unittest.TestCase):
    def test_server_handles_requests_in_threads(self):
        self.assertTrue(app.ReusableTCPServer.daemon_threads)

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

    def test_save_history_records_strips_large_result_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = app.HISTORY_FILE
            app.HISTORY_FILE = os.path.join(tmp, "history_records.json")
            try:
                full_text = " ".join(f"{i:03d}" for i in range(1000))
                saved = app.save_history_records([
                    {
                        "id": 1,
                        "targetIssue": "2026135",
                        "condition_summary": "直选全量 | 胆码 6",
                        "request": {"base_mode": "direct", "text": full_text, "digits": "6"},
                        "filtered": [f"{i:03d}" for i in range(1000)],
                        "steps": [{"name": "legacy", "before": 1000, "after": 271}],
                        "count": 271,
                    }
                ])

                item = saved[0]
                self.assertNotIn("filtered", item)
                self.assertNotIn("steps", item)
                self.assertEqual("", item["request"]["text"])
                self.assertEqual("direct", item["request"]["base_mode"])
                self.assertEqual("直选全量 | 胆码 6", item["condition_summary"])
            finally:
                app.HISTORY_FILE = original

    def test_save_history_records_keeps_editable_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = app.HISTORY_FILE
            app.HISTORY_FILE = os.path.join(tmp, "history_records.json")
            try:
                saved = app.save_history_records([
                    {"id": 1, "note": "周末主方案", "request": {"base_mode": "direct", "digits": "6"}},
                    {"id": 2, "remark": "备用方案", "request": {"base_mode": "direct", "digits": "8"}},
                    {"id": 3, "name": "杀尾方案", "request": {"base_mode": "direct", "kill_digits": "4"}},
                ])

                self.assertEqual("周末主方案", saved[0]["note"])
                self.assertEqual("备用方案", saved[1]["note"])
                self.assertEqual("杀尾方案", saved[2]["note"])
                self.assertEqual(saved, app.load_history_records())
            finally:
                app.HISTORY_FILE = original

    def test_load_history_records_sanitizes_legacy_large_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = app.HISTORY_FILE
            app.HISTORY_FILE = os.path.join(tmp, "history_records.json")
            try:
                with open(app.HISTORY_FILE, "w", encoding="utf-8") as f:
                    json_text = [
                        {
                            "id": 2,
                            "base_mode": "direct",
                            "text": " ".join(f"{i:03d}" for i in range(1000)),
                            "filtered": [f"{i:03d}" for i in range(1000)],
                            "steps": [{"name": "legacy", "before": 1000, "after": 1000}],
                        }
                    ]
                    json.dump(json_text, f)

                loaded = app.load_history_records()

                self.assertEqual(1, len(loaded))
                self.assertNotIn("filtered", loaded[0])
                self.assertNotIn("steps", loaded[0])
                self.assertEqual("", loaded[0]["request"]["text"])
            finally:
                app.HISTORY_FILE = original

    def test_save_history_replaces_date_like_issue_with_next_draw_issue(self):
        with tempfile.TemporaryDirectory() as tmp:
            original_file = app.HISTORY_FILE
            original_loader = app.load_draw_records
            app.HISTORY_FILE = os.path.join(tmp, "history_records.json")
            app.load_draw_records = lambda: [{"issue": "2026142", "draw": "894"}]
            try:
                saved = app.save_history_records([
                    {
                        "id": 3,
                        "targetIssue": "20260601",
                        "request": {"base_mode": "direct", "digits": "8"},
                        "count": 271,
                    }
                ])
            finally:
                app.HISTORY_FILE = original_file
                app.load_draw_records = original_loader

        self.assertEqual("2026143", saved[0]["targetIssue"])

    def test_save_history_fills_missing_issue_with_next_draw_issue(self):
        with tempfile.TemporaryDirectory() as tmp:
            original_file = app.HISTORY_FILE
            original_loader = app.load_draw_records
            app.HISTORY_FILE = os.path.join(tmp, "history_records.json")
            app.load_draw_records = lambda: [{"issue": "2026142", "draw": "894"}]
            try:
                saved = app.save_history_records([
                    {
                        "id": 4,
                        "request": {"base_mode": "direct", "digits": "8"},
                        "count": 271,
                    }
                ])
            finally:
                app.HISTORY_FILE = original_file
                app.load_draw_records = original_loader

        self.assertEqual("2026143", saved[0]["targetIssue"])

    def test_check_history_items_recomputes_hit_from_light_request(self):
        items = [
            {
                "targetIssue": "2026134",
                "request": {"base_mode": "direct", "digits": "6"},
                "count": 271,
            },
            {
                "targetIssue": "2026134",
                "request": {"base_mode": "direct", "digits": "1"},
                "count": 271,
            },
        ]

        original_loader = app.load_draw_records
        app.load_draw_records = lambda: [{"issue": "2026134", "draw": "654"}]
        try:
            checked = app.check_history_items(items)
        finally:
            app.load_draw_records = original_loader

        self.assertTrue(checked[0]["hit"])
        self.assertFalse(checked[1]["hit"])
        self.assertNotIn("filtered", checked[0])

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
