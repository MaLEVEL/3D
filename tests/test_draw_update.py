import datetime
import unittest
from unittest import mock

import app


class DrawUpdateTest(unittest.TestCase):
    def test_parse_ip138_draw_records(self):
        html = """
        <h3>历史开奖</h3><tbody>
        <tr>
        <td><span>2026-05-20</span></td>
        <td><span>2026130</span></td>
        <td class="award">
          <span class="icon-redball" data-value="2">2</span>
          <span class="icon-redball" data-value="6">6</span>
          <span class="icon-redball" data-value="7">7</span>
        </td>
        </tr>
        </tbody>
        """

        self.assertEqual(
            [{"issue": "2026130", "draw": "267", "date": "2026-05-20"}],
            app.parse_ip138_draw_records(html),
        )

    def test_parse_3d178_draw_records(self):
        html = """
        <td class="td_qh"><a href="/kaijiang/2026/2026134.shtml" target="_blank">2026134</a></td>
        <td class="td_code"><span>6</span><span>5</span><span>4</span>
        <td>2026-05-24</td>
        <!--<td class="td_qh"><a href="kjjg_data.aspx?except=2013289">2013289</a></td>
        <td class="td_code"><span>7</span><span>4</span><span>0</span><td>2013-10-23</td>-->
        """

        self.assertEqual(
            [{"issue": "2026134", "draw": "654", "date": "2026-05-24"}],
            app.parse_3d178_draw_records(html),
        )

    def test_parse_huiniao_draw_records(self):
        data = {
            "code": 1,
            "data": {
                "last": {
                    "code": "2026135",
                    "day": "2026-05-25",
                    "one": 4,
                    "two": 8,
                    "three": 7,
                },
                "data": {
                    "list": [
                        {
                            "code": "2026135",
                            "day": "2026-05-25",
                            "one": 4,
                            "two": 8,
                            "three": 7,
                        },
                        {
                            "code": "2026133",
                            "open_time": "2026-05-23 21:15:00",
                            "one": 0,
                            "two": 8,
                            "three": 0,
                        },
                    ]
                },
            },
        }

        self.assertEqual(
            [
                {"issue": "2026135", "draw": "487", "date": "2026-05-25"},
                {"issue": "2026133", "draw": "080", "date": "2026-05-23"},
            ],
            app.parse_huiniao_draw_records(data),
        )

    def test_fetch_official_recent_pages_merges_pages_without_duplicates(self):
        huiniao_records = [
            {"issue": "2026006", "draw": "888", "date": "2026-01-06"},
            {"issue": "2026004", "draw": "000", "date": "2026-01-04"},
        ]
        ip138_records = [
            {"issue": "2026004", "draw": "000", "date": "2026-01-04"},
        ]
        threed178_records = [
            {"issue": "2026005", "draw": "999", "date": "2026-01-05"},
            {"issue": "2026004", "draw": "000", "date": "2026-01-04"},
        ]
        pages = {
            1: [
                {"issue": "2026003", "draw": "123", "date": "2026-01-03"},
                {"issue": "2026002", "draw": "456", "date": "2026-01-02"},
            ],
            2: [
                {"issue": "2026002", "draw": "456", "date": "2026-01-02"},
                {"issue": "2026001", "draw": "789", "date": "2026-01-01"},
            ],
            3: [
                {"issue": "2026001", "draw": "789", "date": "2026-01-01"},
            ],
        }

        def fake_fetch(page=1, size=app.OFFICIAL_PAGE_SIZE):
            return pages[page]

        with mock.patch.object(app, "fetch_huiniao_recent", return_value=huiniao_records):
            with mock.patch.object(app, "fetch_ip138_recent", return_value=ip138_records):
                with mock.patch.object(app, "fetch_3d178_recent", return_value=threed178_records):
                    with mock.patch.object(app, "fetch_official_recent", side_effect=fake_fetch):
                        records = app.fetch_official_recent_pages(pages=3)

        self.assertEqual(["2026006", "2026005", "2026004", "2026003", "2026002", "2026001"], [r["issue"] for r in records])

    def test_fetch_recent_pages_raises_when_batch_sources_fail(self):
        with mock.patch.object(app, "fetch_huiniao_recent", side_effect=RuntimeError("huiniao offline")):
            with mock.patch.object(app, "fetch_ip138_recent", side_effect=RuntimeError("ip138 offline")):
                with mock.patch.object(app, "fetch_3d178_recent", side_effect=RuntimeError("3d178 offline")):
                    with mock.patch.object(app, "fetch_official_recent", side_effect=RuntimeError("official offline")):
                        with self.assertRaises(RuntimeError):
                            app.fetch_official_recent_pages(pages=1)

    def test_update_endpoint_writes_latest_draw_when_batch_update_fails(self):
        handler = object.__new__(app.RequestHandler)
        captured = {}
        existing = [{"issue": "2026001", "draw": "123", "date": "2026-01-01"}]
        latest = {"issue": "2026002", "draw": "456", "date": "2026-01-02"}

        def fake_send_json(payload, status=200):
            captured["payload"] = payload
            captured["status"] = status

        handler._send_json = fake_send_json
        with mock.patch.object(app, "fetch_official_recent_pages", side_effect=RuntimeError("offline")):
            with mock.patch.object(app, "fetch_latest_draw", return_value=latest):
                with mock.patch.object(app, "load_draw_records", return_value=existing):
                    with mock.patch.object(app, "merge_draw_records", return_value=([latest] + existing, 1)) as merge_mock:
                        handler._api_update_draws()

        self.assertEqual(200, captured["status"])
        self.assertTrue(captured["payload"]["ok"])
        self.assertTrue(captured["payload"]["updated"])
        self.assertEqual(1, captured["payload"]["added"])
        self.assertEqual(1, captured["payload"]["fetched"])
        self.assertEqual("2026002", captured["payload"]["latest"]["issue"])
        self.assertIn("warning", captured["payload"])
        self.assertIn("兜底", captured["payload"]["warning"])
        merge_mock.assert_called_once_with([latest])

    def test_update_endpoint_keeps_local_draws_when_all_sources_fail(self):
        handler = object.__new__(app.RequestHandler)
        captured = {}
        existing = [{"issue": "2026001", "draw": "123"}]

        def fake_send_json(payload, status=200):
            captured["payload"] = payload
            captured["status"] = status

        handler._send_json = fake_send_json
        with mock.patch.object(app, "fetch_official_recent_pages", side_effect=RuntimeError("batch offline")):
            with mock.patch.object(app, "fetch_latest_draw", side_effect=RuntimeError("latest offline")):
                with mock.patch.object(app, "recent_draw_records", return_value=existing):
                    with mock.patch.object(app, "load_draw_records", return_value=existing):
                        handler._api_update_draws()

        self.assertEqual(200, captured["status"])
        self.assertTrue(captured["payload"]["ok"])
        self.assertTrue(captured["payload"]["updated"])
        self.assertIn("warning", captured["payload"])
        self.assertEqual(0, captured["payload"]["added"])
        self.assertEqual(existing, captured["payload"]["records"])

    def test_update_endpoint_returns_failure_when_no_local_draws_exist(self):
        handler = object.__new__(app.RequestHandler)
        captured = {}

        def fake_send_json(payload, status=200):
            captured["payload"] = payload
            captured["status"] = status

        handler._send_json = fake_send_json
        with mock.patch.object(app, "fetch_official_recent_pages", side_effect=RuntimeError("offline")):
            with mock.patch.object(app, "fetch_latest_draw", side_effect=RuntimeError("latest offline")):
                with mock.patch.object(app, "recent_draw_records", return_value=[]):
                    handler._api_update_draws()

        self.assertEqual(200, captured["status"])
        self.assertTrue(captured["payload"]["ok"])
        self.assertFalse(captured["payload"]["updated"])
        self.assertIn("error", captured["payload"])
        self.assertEqual([], captured["payload"]["records"])

    def test_http_get_text_windows_curl_fallback_keeps_query_and_headers(self):
        completed = mock.Mock(
            returncode=0,
            stdout=b"ok",
            stderr=b"",
        )

        with mock.patch.object(app.os, "name", "nt"):
            with mock.patch.object(app.urllib.request, "urlopen", side_effect=RuntimeError("urllib offline")):
                with mock.patch.object(app.subprocess, "run", return_value=completed) as run_mock:
                    text = app.http_get_text(
                        "https://example.test/path?json=1&page=1&size=30",
                        {"User-Agent": "UnitTest", "Referer": "https://example.test/from"},
                        timeout=7,
                    )

        command = run_mock.call_args.args[0]
        self.assertEqual("ok", text)
        self.assertEqual("curl.exe", command[0])
        self.assertEqual("https://example.test/path?json=1&page=1&size=30", command[-1])
        self.assertIn("User-Agent: UnitTest", command)
        self.assertIn("Referer: https://example.test/from", command)

    def test_check_history_items_marks_saved_predictions(self):
        draws = [{"issue": "2026134", "draw": "654", "date": "2026-05-24"}]
        items = [
            {"targetIssue": "2026134", "filtered": ["456"], "base_mode": "group"},
            {"targetIssue": "2026134", "filtered": ["123"], "base_mode": "group"},
        ]

        with mock.patch.object(app, "load_draw_records", return_value=draws):
            checked = app.check_history_items(items)

        self.assertTrue(checked[0]["hit"])
        self.assertEqual("654", checked[0]["actualDraw"])
        self.assertFalse(checked[1]["hit"])
        self.assertEqual("654", checked[1]["actualDraw"])

    def test_next_issue_stops_at_first_gap(self):
        records = [
            {"issue": "2026001", "draw": "111"},
            {"issue": "2026002", "draw": "222"},
            {"issue": "2026005", "draw": "555"},
        ]

        self.assertEqual("2026003", app.next_issue(records))

    def test_contiguous_update_does_not_write_after_missing_gap(self):
        existing = [{"issue": "2026125", "draw": "954"}]
        fetched = [
            {"issue": "2026130", "draw": "267"},
            {"issue": "2026126", "draw": "111"},
        ]

        mergeable, missing = app.contiguous_draw_update(existing, fetched)

        self.assertEqual(["2026126"], [r["issue"] for r in mergeable])
        self.assertEqual(["2026127", "2026128", "2026129"], missing)

    def test_next_auto_update_at_uses_2126_daily_schedule(self):
        tz = app.ZoneInfo("Asia/Shanghai")
        before = datetime.datetime(2026, 5, 30, 21, 25, 0, tzinfo=tz)
        at_time = datetime.datetime(2026, 5, 30, 21, 26, 0, tzinfo=tz)

        self.assertEqual(
            datetime.datetime(2026, 5, 30, 21, 26, 0, tzinfo=tz),
            app.next_auto_update_at(before),
        )
        self.assertEqual(
            datetime.datetime(2026, 5, 31, 21, 26, 0, tzinfo=tz),
            app.next_auto_update_at(at_time),
        )

    def test_seconds_until_auto_update(self):
        tz = app.ZoneInfo("Asia/Shanghai")
        now = datetime.datetime(2026, 5, 30, 21, 25, 30, tzinfo=tz)

        self.assertEqual(30, app.seconds_until_auto_update(now))

    def test_should_retry_scheduled_update_until_target_issue_exists(self):
        records = [{"issue": "2026140", "draw": "285"}]

        self.assertTrue(app.should_retry_scheduled_update("2026141", records))
        self.assertFalse(app.should_retry_scheduled_update("2026140", records))
        self.assertFalse(app.should_retry_scheduled_update("", records))

    def test_run_scheduled_draw_update_reports_incomplete_target(self):
        records = [{"issue": "2026140", "draw": "285"}]

        with mock.patch.object(app, "fetch_and_merge_draw_records", return_value=(records, 0, [], [], "")):
            self.assertFalse(app.run_scheduled_draw_update("2026141"))
            self.assertTrue(app.run_scheduled_draw_update("2026140"))


if __name__ == "__main__":
    unittest.main()
