#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FC3D local number filtering tool."""

import http.server
import json
import os
import re
import socketserver
import subprocess
import threading
import urllib.error
import urllib.request
import webbrowser

PORT = 5000
AUTO_OPEN_BROWSER = os.environ.get("FC3D_AUTO_OPEN_BROWSER", "1") != "0"
ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(ROOT, "draw_records.json")
HISTORY_FILE = os.path.join(ROOT, "history_records.json")
MAX_HISTORY = 80
OFFICIAL_PAGE_SIZE = 30
OFFICIAL_FETCH_PAGES = 10
DRAW_LIST_LIMIT = 50
IP138_3D_URL = "https://caipiao.ip138.com/3d/"
SEGMENT_PATTERNS = {
    "2-2-6": [2, 2, 6],
    "2-3-5": [2, 3, 5],
    "5-5": [5, 5],
}
ADVANCED_CONDITION_TYPES = {
    "sum",
    "sum_tail",
    "odd_even",
    "big_small",
    "span",
    "mod012",
    "size_area",
}
ADVANCED_CONDITION_LABELS = {
    "sum": "和值",
    "sum_tail": "和尾",
    "odd_even": "奇偶比",
    "big_small": "大小比",
    "span": "跨度",
    "mod012": "012路比",
    "size_area": "大中小",
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


def load_history_records():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_history_records(items):
    records = items if isinstance(items, list) else []
    records = records[:MAX_HISTORY]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    return records


def http_get_text(url, headers=None, timeout=20):
    headers = headers or {}
    req = urllib.request.Request(url)
    for key, value in headers.items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, "ignore")
    except Exception as first_error:
        if os.name != "nt":
            raise
        ps_script = (
            "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
            "$ProgressPreference='SilentlyContinue'; "
            "$headers=@{'User-Agent'='Mozilla/5.0'; 'Referer'='https://caipiao.ip138.com/'}; "
            f"$r=Invoke-WebRequest -Uri $args[0] -UseBasicParsing -TimeoutSec {int(timeout)} -Headers $headers; "
            "[Console]::Write($r.Content)"
        )
        try:
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script, url],
                capture_output=True,
                timeout=timeout + 10,
            )
        except (OSError, subprocess.SubprocessError) as ps_error:
            raise RuntimeError(f"request failed: {first_error}; powershell fallback failed: {ps_error}") from ps_error
        if completed.returncode != 0 or not completed.stdout:
            stderr = completed.stderr.decode("utf-8", "ignore").strip()
            raise RuntimeError(f"request failed: {first_error}; powershell fallback failed: {stderr}")
        return completed.stdout.decode("utf-8", "ignore")


def fetch_latest_draw():
    url = "https://cn.apihz.cn/api/caipiao/fucai3d.php?id=88888888&key=88888888"
    text = http_get_text(url, {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}, timeout=30)
    data = json.loads(text)
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
    text = http_get_text(url, {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.cwl.gov.cn/ygkj/fc3d/kjgg/",
        "X-Requested-With": "XMLHttpRequest",
    }, timeout=30)
    data = json.loads(text)

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


def parse_ip138_draw_records(html):
    records = []
    table_match = re.search(r"<h3>\s*历史开奖\s*</h3>.*?<tbody>(.*?)</tbody>", html, re.S)
    body = table_match.group(1) if table_match else html
    row_pattern = re.compile(
        r"<tr>\s*<td>\s*<span>(?P<date>\d{4}-\d{2}-\d{2})</span>\s*</td>\s*"
        r"<td>\s*<span>(?P<issue>\d{5,})</span>\s*</td>\s*"
        r"<td[^>]*class=\"award\"[^>]*>(?P<award>.*?)</td>",
        re.S,
    )
    for match in row_pattern.finditer(body):
        award_html = match.group("award")
        digits = re.findall(r'data-value="(\d)"', award_html)
        if len(digits) < 3:
            digits = re.findall(r">\s*(\d)\s*</span>", award_html)
        draw = "".join(digits[:3])
        issue = match.group("issue")
        if issue.isdigit() and len(draw) == 3:
            records.append({"issue": issue, "draw": draw, "date": match.group("date")})
    if not records:
        raise RuntimeError("ip138 draw page returned no valid records")
    return records


def fetch_ip138_recent():
    html = http_get_text(IP138_3D_URL, {"User-Agent": "Mozilla/5.0"}, timeout=20)
    return parse_ip138_draw_records(html)


def fetch_official_recent_pages(pages=OFFICIAL_FETCH_PAGES, size=OFFICIAL_PAGE_SIZE):
    ip138_error_msg = ""
    try:
        return fetch_ip138_recent()
    except Exception as ip138_error:
        ip138_error_msg = str(ip138_error)

    records = []
    seen = set()
    try:
        for page in range(1, pages + 1):
            page_records = fetch_official_recent(page=page, size=size)
            new_count = 0
            for record in page_records:
                issue = str(record.get("issue", ""))
                if issue in seen:
                    continue
                seen.add(issue)
                records.append(record)
                new_count += 1
            if new_count == 0:
                break
    except Exception as official_error:
        raise RuntimeError(f"all draw sources failed; ip138: {ip138_error_msg}; official: {official_error}") from official_error
    if not records:
        raise RuntimeError(f"all draw sources returned no valid records; ip138: {ip138_error_msg}")
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


def generate_code_combos(digits):
    """Generate all 组六 + 组三 combos from N unique digits (N=3~8)."""
    digits = str(digits)
    if len(digits) < 3:
        raise ValueError("至少需要3个不同数字")
    if len(digits) > 8:
        raise ValueError("最多支持8个不同数字")
    if len(set(digits)) != len(digits) or not digits.isdigit():
        raise ValueError("数字必须是不重复的0-9数字")
    arr = list(digits)
    n = len(arr)
    result = []
    # 组六: C(n,3) — three different digits
    for i in range(n):
        for j in range(i + 1, n):
            for k in range(j + 1, n):
                result.append(arr[i] + arr[j] + arr[k])
    # 组三: n * (n-1) — pair + another digit
    for i in range(n):
        for j in range(n):
            if i != j:
                result.append(arr[i] + arr[i] + arr[j])
    return result


def process_generate_codes(codes):
    """Process a list of code specs and return (result_dict, status_code)."""
    if not isinstance(codes, list):
        return {"ok": False, "error": "codes must be a list"}, 400
    if not codes:
        return {"ok": False, "error": "请提供复式码列表"}, 400
    all_generated = set()
    for item in codes:
        digits = str(item.get("digits", ""))
        if not digits:
            continue
        try:
            combos = generate_code_combos(digits)
        except ValueError as e:
            return {"ok": False, "error": str(e)}, 400
        all_generated.update(combos)
    if not all_generated:
        return {"ok": False, "error": "没有有效的复式码"}, 400
    generated = sorted(all_generated)
    return {
        "ok": True,
        "generated": generated,
        "count": len(generated),
        "codes": [{"digits": c.get("digits", ""), "len": c.get("len", len(c.get("digits", "")))} for c in codes],
    }, 200


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


def validate_code_filter(item):
    code_len = int(item.get("code_len", 3))
    if code_len < 3 or code_len > 8:
        raise ValueError(f"码数必须在3-8之间，当前为{code_len}")
    condition = item.get("condition", "012")
    if condition not in ("01", "012", "123"):
        raise ValueError(f"条件只能是01、012或123，当前为{condition}")
    digits = str(item.get("digits", ""))
    if len(digits) != code_len:
        raise ValueError(f"需要恰好{code_len}个数字，当前有{len(digits)}个")
    if not digits.isdigit() or len(set(digits)) != len(digits):
        raise ValueError(f"数字必须是不重复的0-9数字")
    return {"code_len": code_len, "condition": condition, "digits": digits}


def passes_code_filter(number, code_filter):
    digits = code_filter["digits"]
    condition = code_filter["condition"]
    count = len(set(number) & set(digits))
    if condition == "01":
        return count in (0, 1)
    elif condition == "012":
        return count in (0, 1, 2)
    elif condition == "123":
        return count in (1, 2, 3)
    return True


def normalize_code_filters(data):
    filters = data.get("code_filters")
    if isinstance(filters, list):
        result = []
        for item in filters:
            if not isinstance(item, dict) or not item.get("enabled", True):
                continue
            cf = validate_code_filter(item)
            result.append(cf)
        return result
    return []


def code_filter_desc(code_filters):
    return "; ".join(
        f"{cf['code_len']}码={cf['condition']}[{cf['digits']}]"
        for cf in code_filters
    )


def _range_values(values, low, high, label):
    result = []
    for raw in values:
        value = str(raw).strip()
        if not value:
            continue
        if not value.isdigit():
            raise ValueError(f"{label}只能选择数字")
        number = int(value)
        if number < low or number > high:
            raise ValueError(f"{label}必须在{low}-{high}之间")
        result.append(str(number))
    return sorted(set(result), key=lambda x: int(x))


def _ratio_values(values, parts, label):
    result = []
    for raw in values:
        value = str(raw).strip()
        nums = value.split(":")
        if len(nums) != parts or any(not n.isdigit() for n in nums):
            raise ValueError(f"{label}格式应为{':'.join(['0'] * parts)}")
        counts = [int(n) for n in nums]
        if sum(counts) != 3:
            raise ValueError(f"{label}三位计数合计必须为3")
        result.append(":".join(str(n) for n in counts))
    return sorted(set(result))


def normalize_advanced_condition_values(kind, values):
    if not isinstance(values, list):
        values = [values]
    if kind == "sum":
        return _range_values(values, 0, 27, "和值")
    if kind in ("sum_tail", "span"):
        label = "和尾" if kind == "sum_tail" else "跨度"
        return _range_values(values, 0, 9, label)
    if kind in ("odd_even", "big_small"):
        label = "奇偶比" if kind == "odd_even" else "大小比"
        return _ratio_values(values, 2, label)
    if kind in ("mod012", "size_area"):
        label = "012路比" if kind == "mod012" else "大中小"
        return _ratio_values(values, 3, label)
    raise ValueError(f"未知高级条件: {kind}")


def normalize_advanced_filter(data):
    raw = data.get("advanced_filter")
    if not isinstance(raw, dict):
        return {"enabled": False, "conditions": [], "miss_min": 0, "miss_max": 0}

    conditions = []
    raw_conditions = raw.get("conditions", raw.get("condition_filters", []))
    if isinstance(raw_conditions, list):
        for item in raw_conditions:
            if not isinstance(item, dict) or not item.get("enabled", True):
                continue
            kind = str(item.get("type", "")).strip()
            if kind not in ADVANCED_CONDITION_TYPES:
                raise ValueError(f"未知高级条件: {kind}")
            values = normalize_advanced_condition_values(kind, item.get("values", []))
            if values:
                conditions.append({"type": kind, "values": values})

    miss_min = int(raw.get("miss_min", 0) or 0)
    miss_max = int(raw.get("miss_max", 0) or 0)
    if miss_min < 0 or miss_max < 0:
        raise ValueError("容错个数不能小于0")
    if miss_min > miss_max:
        raise ValueError("容错下限不能大于上限")
    if conditions and miss_max > len(conditions):
        raise ValueError("容错上限不能超过高级条件数量")
    if not conditions:
        miss_min = 0
        miss_max = 0

    enabled = bool(conditions)
    return {
        "enabled": enabled,
        "conditions": conditions,
        "miss_min": miss_min,
        "miss_max": miss_max,
    }


def advanced_condition_value(number, kind):
    digits = [int(d) for d in number]
    if kind == "sum":
        return str(sum(digits))
    if kind == "sum_tail":
        return str(sum(digits) % 10)
    if kind == "odd_even":
        odd = sum(1 for d in digits if d % 2 == 1)
        return f"{odd}:{3 - odd}"
    if kind == "big_small":
        big = sum(1 for d in digits if d >= 5)
        return f"{big}:{3 - big}"
    if kind == "span":
        return str(max(digits) - min(digits))
    if kind == "mod012":
        counts = [0, 0, 0]
        for d in digits:
            counts[d % 3] += 1
        return ":".join(str(n) for n in counts)
    if kind == "size_area":
        small = sum(1 for d in digits if d <= 2)
        middle = sum(1 for d in digits if 3 <= d <= 6)
        big = sum(1 for d in digits if d >= 7)
        return f"{small}:{middle}:{big}"
    return ""


def passes_advanced_filter(number, advanced_filter):
    if not advanced_filter.get("enabled"):
        return True

    conditions = advanced_filter.get("conditions", [])
    if not conditions:
        return True

    miss_count = 0
    for condition in conditions:
        actual = advanced_condition_value(number, condition["type"])
        if actual not in condition["values"]:
            miss_count += 1
    return advanced_filter["miss_min"] <= miss_count <= advanced_filter["miss_max"]


def advanced_filter_desc(advanced_filter):
    if not advanced_filter.get("enabled"):
        return ""
    parts = []
    for condition in advanced_filter.get("conditions", []):
        label = ADVANCED_CONDITION_LABELS.get(condition["type"], condition["type"])
        parts.append(f"{label}={','.join(condition['values'])}")
    if advanced_filter.get("conditions"):
        parts.append(f"容错{advanced_filter['miss_min']}-{advanced_filter['miss_max']}")
    return "; ".join(parts)


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
        if self.path.startswith("/api/history"):
            return self._api_history_get()
        if self.path in ("/", "/index.html"):
            self._send_html(HTML_PAGE)
        else:
            self._send_html("<h1>404 Not Found</h1>", 404)

    def do_DELETE(self):
        if self.path == "/api/history":
            save_history_records([])
            return self._send_json({"ok": True, "items": []})
        self._send_json({"error": "Not Found"}, 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        try:
            if self.path == "/api/generate_codes":
                return self._api_generate_codes()
            if self.path == "/api/filter":
                return self._api_filter()
            if self.path == "/api/update_draws":
                return self._api_update_draws()
            if self.path == "/api/check_history":
                return self._api_check_history()
            if self.path == "/api/history":
                return self._api_history_save()
            self._send_json({"error": "Not Found"}, 404)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _api_filter(self):
        data = self._read_json_body()
        text = data.get("text", "")
        digits = data.get("digits", "")
        advance_digits = data.get("advance_digits", "")
        kill_digits = data.get("kill_digits", "")
        segment_filters = normalize_segment_filters(data)
        code_filters = normalize_code_filters(data)
        advanced_filter = normalize_advanced_filter(data)

        matches = re.findall(r"\b\d{3}\b", text)
        seen = set()
        unique = []
        for m in matches:
            if m not in seen:
                seen.add(m)
                unique.append(m)

        target_include = set(digits) if digits else set()
        target_advance = set(advance_digits) if advance_digits else set()
        target_kill = set(kill_digits) if kill_digits else set()

        if (
            not target_include
            and not target_advance
            and not target_kill
            and not segment_filters
            and not code_filters
            and not advanced_filter["enabled"]
        ):
            self._send_json({"error": "please enter at least one filter condition"}, 400)
            return

        filtered = []
        for n in unique:
            if advanced_filter["enabled"] and not passes_advanced_filter(n, advanced_filter):
                continue
            if target_kill and any(d in n for d in target_kill):
                continue
            if target_include and not any(d in n for d in target_include):
                continue
            if target_advance:
                a, b, c = int(n[0]), int(n[1]), int(n[2])
                adv_set = {abs(a - b), abs(a - c), abs(b - c)}
                if not any(str(d) in target_advance for d in adv_set):
                    continue
            if any(not passes_segment_pattern(n, item["groups"], item["mode"]) for item in segment_filters):
                continue
            if any(not passes_code_filter(n, cf) for cf in code_filters):
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
            "code_desc": code_filter_desc(code_filters),
            "code_filters": [
                {"code_len": cf["code_len"], "condition": cf["condition"], "digits": cf["digits"]}
                for cf in code_filters
            ],
            "advanced_desc": advanced_filter_desc(advanced_filter),
            "advanced_filter": {
                "conditions": advanced_filter["conditions"],
                "miss_min": advanced_filter["miss_min"],
                "miss_max": advanced_filter["miss_max"],
            },
        })

    def _api_generate_codes(self):
        data = self._read_json_body()
        codes = data.get("codes", [])
        result, status = process_generate_codes(codes)
        self._send_json(result, status)

    def _api_update_draws(self):
        try:
            new_records = fetch_official_recent_pages()
            records, added = merge_draw_records(new_records)
            records.sort(key=lambda r: str(r.get("issue", "")), reverse=True)
            self._send_json({
                "ok": True,
                "added": added,
                "fetched": len(new_records),
                "latest": records[0] if records else None,
                "nextIssue": next_issue(records),
                "count": len(records),
                "records": records[:DRAW_LIST_LIMIT],
            })
        except (RuntimeError, urllib.error.URLError, TimeoutError, OSError) as e:
            records = recent_draw_records(DRAW_LIST_LIMIT)
            self._send_json({
                "ok": True,
                "updated": False,
                "error": f"批量开奖更新失败，已保留本地已有开奖，未写入最新一期以避免跳期：{e}",
                "added": 0,
                "fetched": 0,
                "latest": records[0] if records else None,
                "nextIssue": next_issue(load_draw_records()),
                "count": len(load_draw_records()),
                "records": records,
            })

    def _api_draws(self):
        records = recent_draw_records(DRAW_LIST_LIMIT)
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
        checked = check_history_items(items)
        self._send_json({"ok": True, "items": checked, "drawCount": len(load_draw_records())})

    def _api_history_get(self):
        self._send_json({"ok": True, "items": load_history_records()})

    def _api_history_save(self):
        body = self._read_json_body()
        items = save_history_records(body.get("items", []))
        self._send_json({"ok": True, "items": items, "count": len(items)})


def check_history_items(items):
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
    return checked


class ReusableTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def open_browser():
    webbrowser.open("http://127.0.0.1:5000/")


def _free_port(port):
    """Kill any process occupying the given port."""
    try:
        import subprocess
        if os.name == "nt":
            out = subprocess.check_output(
                ["netstat", "-ano"], text=True, timeout=10
            )
            for line in out.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.strip().split()
                    pid = parts[-1]
                    subprocess.run(
                        ["taskkill", "/F", "/PID", pid],
                        capture_output=True, timeout=10,
                    )
                    print(f"  [auto] Killed old process PID {pid} on port {port}")
        else:
            import signal
            out = subprocess.check_output(["lsof", "-ti", f":{port}"], text=True)
            for pid in out.strip().splitlines():
                os.kill(int(pid), signal.SIGTERM)
                print(f"  [auto] Killed old process PID {pid} on port {port}")
    except Exception:
        pass


if __name__ == "__main__":
    _free_port(PORT)
    print("=" * 60)
    print("  FC3D local filter service")
    print("  URL: http://127.0.0.1:5000")
    print("  Ctrl+C to stop")
    print("=" * 60)
    if AUTO_OPEN_BROWSER:
        threading.Timer(1.0, open_browser).start()
    for _ in range(5):
        try:
            with ReusableTCPServer(("", PORT), RequestHandler) as httpd:
                httpd.serve_forever()
        except OSError:
            import time
            time.sleep(0.5)
        else:
            break
