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

    def test_fetch_official_recent_pages_merges_pages_without_duplicates(self):
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

        with mock.patch.object(app, "fetch_ip138_recent", side_effect=RuntimeError("ip138 offline")):
            with mock.patch.object(app, "fetch_official_recent", side_effect=fake_fetch):
                records = app.fetch_official_recent_pages(pages=3)

        self.assertEqual(["2026003", "2026002", "2026001"], [r["issue"] for r in records])

    def test_update_no_longer_uses_latest_only_fallback(self):
        with mock.patch.object(app, "fetch_ip138_recent", side_effect=RuntimeError("ip138 offline")):
            with mock.patch.object(app, "fetch_official_recent", side_effect=RuntimeError("official offline")):
                with self.assertRaises(RuntimeError):
                    app.fetch_official_recent_pages(pages=1)

    def test_update_endpoint_returns_ok_payload_when_batch_update_fails(self):
        handler = object.__new__(app.RequestHandler)
        captured = {}

        def fake_send_json(payload, status=200):
            captured["payload"] = payload
            captured["status"] = status

        handler._send_json = fake_send_json
        with mock.patch.object(app, "fetch_official_recent_pages", side_effect=RuntimeError("offline")):
            with mock.patch.object(app, "recent_draw_records", return_value=[{"issue": "2026001", "draw": "123"}]):
                with mock.patch.object(app, "load_draw_records", return_value=[{"issue": "2026001", "draw": "123"}]):
                    handler._api_update_draws()

        self.assertEqual(200, captured["status"])
        self.assertTrue(captured["payload"]["ok"])
        self.assertFalse(captured["payload"]["updated"])
        self.assertEqual(0, captured["payload"]["added"])


if __name__ == "__main__":
    unittest.main()
