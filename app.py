#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FC3D local number filtering tool."""

import http.server
import json
import os
import re
import socketserver
import threading
import urllib.error
import urllib.request
import webbrowser

PORT = 5000
ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(ROOT, "draw_records.json")
OFFICIAL_PAGE_SIZE = 30
SEGMENT_PATTERNS = {
    "2-2-6": [2, 2, 6],
    "2-3-5": [2, 3, 5],
    "5-5": [5, 5],
}

try:
    with open(os.path.join(ROOT, "index.html"), "r", encoding="utf-8") as f:
        HTML_PAGE = f.read()
except FileNotFoundError:
    print("ERROR: index.html not found")
    raise SystemExit(1)


def load_draw_records():
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_draw_records(records):
    records.sort(key=lambda r: str(r.get("issue", "")))
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(records[-500:], f, ensure_ascii=False, indent=2)


def fetch_latest_draw():
    url = "https://cn.apihz.cn/api/caipiao/fucai3d.php?id=88888888&key=88888888"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("code") != 200:
        raise RuntimeError(data.get("msg") or "draw api returned an error")
    draw = str(data.get("number", "")).replace("|", "").replace(",", "").replace(" ", "").strip()
    issue = str(data.get("qihao", "")).strip()
    raw_date = str(data.get("time", "")).split("(")[0].strip()
    if not issue or not draw.isdigit() or len(draw) != 3:
        raise RuntimeError("draw api returned invalid data")
    return {"issue": issue, "draw": draw, "date": raw_date}


def fetch_official_recent(page=1, size=OFFICIAL_PAGE_SIZE):
    url = f"https://www.cwl.gov.cn/ygkj/fc3d/kjgg/?json=1&page={page}&size={size}"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    req.add_header("Referer", "https://www.cwl.gov.cn/ygkj/fc3d/kjgg/")
    req.add_header("X-Requested-With", "XMLHttpRequest")
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    items = data if isinstance(data, list) else data.get("data", [])
    if isinstance(items, dict):
        items = items.get("list", items.get("result", []))

    records = []
    for item in items:
        if not isinstance(item, dict):
            continue
        issue = str(item.get("expect", item.get("issueNumber", ""))).strip()
        raw = item.get("openCode", item.get("blueBall", ""))
        if isinstance(raw, list):
            draw = "".join(str(d).strip() for d in raw)
        else:
            draw = str(raw).replace(" ", "").replace(",", "").replace("|", "").strip()
        date = str(item.get("time", item.get("date", ""))).split("(")[0].strip()
        if issue.isdigit() and len(issue) >= 5 and draw.isdigit() and len(draw) == 3:
            records.append({"issue": issue, "draw": draw, "date": date})
    if not records:
        raise RuntimeError("official draw api returned no valid records")
    return records


def merge_draw_record(record):
    return merge_draw_records([record])


def merge_draw_records(new_records):
    records = load_draw_records()
    by_issue = {str(r.get("issue")): r for r in records}
    added = 0
    for record in new_records:
        key = str(record["issue"])
        if key not in by_issue:
            added += 1
        by_issue[key] = record
    merged = list(by_issue.values())
    save_draw_records(merged)
    return merged, added


def next_issue(records):
    numeric = [int(str(r.get("issue", ""))) for r in records if str(r.get("issue", "")).isdigit()]
    return str(max(numeric) + 1) if numeric else ""


def recent_draw_records(limit=10):
    records = load_draw_records()
    records.sort(key=lambda r: str(r.get("issue", "")), reverse=True)
    return records[:limit]


def group_hit(filtered, draw):
    if not filtered or not draw:
        return False
    draw_key = "".join(sorted(draw))
    return any("".join(sorted(str(n).zfill(3))) == draw_key for n in filtered)


def segment_index(digit, groups):
    for idx, group in enumerate(groups):
        if digit in group:
            return idx
    return -1


def passes_segment_pattern(number, groups, mode):
    hit_groups = {segment_index(d, groups) for d in set(number)}
    hit_groups.discard(-1)
    if mode == "5-5":
        return len(hit_groups) >= 2
    return len(hit_groups) <= 2


def validate_segment_groups(groups_data, mode):
    if not groups_data:
        return []
    sizes = SEGMENT_PATTERNS.get(mode)
    if not sizes:
        raise ValueError(f"invalid segment mode: {mode}")
    if len(groups_data) != len(sizes):
        raise ValueError(f"{mode} requires {len(sizes)} groups")
    groups = []
    used = set()
    for raw, size in zip(groups_data, sizes):
        group = set(str(raw))
        if len(group) != size:
            raise ValueError(f"{mode} group sizes must be {'-'.join(map(str, sizes))}")
        if used & group:
            raise ValueError(f"{mode} groups cannot overlap")
        used |= group
        groups.append(group)
    if used != set("0123456789"):
        raise ValueError(f"{mode} groups must cover digits 0-9")
    return groups


def normalize_segment_filters(data):
    filters = data.get("segment_filters")
    if isinstance(filters, list):
        result = []
        for item in filters:
            if not isinstance(item, dict) or not item.get("enabled", True):
                continue
            mode = item.get("mode", "2-3-5")
            groups_data = [g for g in item.get("groups", []) if g and str(g).strip()]
            groups = validate_segment_groups(groups_data, mode)
            if groups:
                result.append({"mode": mode, "groups_data": groups_data, "groups": groups})
        return result

    mode = data.get("segment_mode", "2-3-5")
    groups_data = data.get("groups", [])
    if not groups_data:
        groups_data = [data.get("group1", ""), data.get("group2", ""), data.get("group3", "")]
    groups_data = [g for g in groups_data if g and str(g).strip()]
    groups = validate_segment_groups(groups_data, mode)
    return [{"mode": mode, "groups_data": groups_data, "groups": groups}] if groups else []


def segment_desc(segment_filters):
    return "; ".join(
        f"{item['mode']} segment [" + " | ".join(item["groups_data"]) + "]"
        for item in segment_filters
    )


class RequestHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html, status=200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            return {}
        return json.loads(self.rfile.read(content_length).decode("utf-8"))

    def do_GET(self):
        if self.path.startswith("/api/draws"):
            return self._api_draws()
        if self.path in ("/", "/index.html"):
            self._send_html(HTML_PAGE)
        else:
            self._send_html("<h1>404 Not Found</h1>", 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        try:
            if self.path == "/api/filter":
                return self._api_filter()
            if self.path == "/api/update_draws":
                return self._api_update_draws()
            if self.path == "/api/check_history":
                return self._api_check_history()
            self._send_json({"error": "Not Found"}, 404)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _api_filter(self):
        data = self._read_json_body()
        text = data.get("text", "")
        digits = data.get("digits", "")
        advance_digits = data.get("advance_digits", "")
        segment_filters = normalize_segment_filters(data)

        matches = re.findall(r"\b\d{3}\b", text)
        seen = set()
        unique = []
        for m in matches:
            if m not in seen:
                seen.add(m)
                unique.append(m)

        target_include = set(digits) if digits else set()
        target_advance = set(advance_digits) if advance_digits else set()

        if not target_include and not target_advance and not segment_filters:
            self._send_json({"error": "please enter at least one filter condition"}, 400)
            return

        filtered = []
        for n in unique:
            if target_include and not any(d in n for d in target_include):
                continue
            if target_advance:
                a, b, c = int(n[0]), int(n[1]), int(n[2])
                adv_set = {abs(a - b), abs(a - c), abs(b - c)}
                if not any(str(d) in target_advance for d in adv_set):
                    continue
            if any(not passes_segment_pattern(n, item["groups"], item["mode"]) for item in segment_filters):
                continue
            filtered.append(n)

        self._send_json({
            "total": len(unique),
            "filtered": filtered,
            "count": len(filtered),
            "percent": round(len(filtered) / len(unique) * 100, 2) if unique else 0,
            "advance_digits": advance_digits,
            "segment": segment_desc(segment_filters),
            "segment_filters": [
                {"mode": item["mode"], "groups": item["groups_data"]}
                for item in segment_filters
            ],
        })

    def _api_update_draws(self):
        try:
            try:
                new_records = fetch_official_recent()
            except Exception:
                new_records = [fetch_latest_draw()]
            records, added = merge_draw_records(new_records)
            records.sort(key=lambda r: str(r.get("issue", "")), reverse=True)
            self._send_json({
                "ok": True,
                "added": added,
                "latest": records[0] if records else None,
                "nextIssue": next_issue(records),
                "count": len(records),
                "records": records[:50],
            })
        except urllib.error.URLError as e:
            self._send_json({"ok": False, "error": f"draw api request failed: {e}"}, 500)

    def _api_draws(self):
        records = recent_draw_records(10)
        self._send_json({
            "ok": True,
            "records": records,
            "latest": records[0] if records else None,
            "nextIssue": next_issue(records),
            "count": len(load_draw_records()),
        })

    def _api_check_history(self):
        body = self._read_json_body()
        items = body.get("items", [])
        records = load_draw_records()
        by_issue = {str(r.get("issue")): r for r in records}
        checked = []
        for item in items:
            target_issue = str(item.get("targetIssue") or item.get("issue") or "")
            draw = by_issue.get(target_issue)
            next_item = dict(item)
            if draw:
                next_item["actualIssue"] = draw.get("issue")
                next_item["actualDraw"] = draw.get("draw")
                next_item["hit"] = group_hit(item.get("filtered", []), draw.get("draw", ""))
            checked.append(next_item)
        self._send_json({"ok": True, "items": checked, "drawCount": len(records)})


def open_browser():
    webbrowser.open("http://127.0.0.1:5000/")


if __name__ == "__main__":
    print("=" * 60)
    print("  FC3D local filter service")
    print("  URL: http://127.0.0.1:5000")
    print("  Ctrl+C to stop")
    print("=" * 60)
    threading.Timer(1.0, open_browser).start()
    with socketserver.TCPServer(("", PORT), RequestHandler) as httpd:
        httpd.serve_forever()
