#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FC3D local number filtering tool."""

import http.server
import datetime
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
THREED178_YEAR_URL = "https://www.3d178.cn/kaijiang/{year}/"
HUINIAO_HISTORY_URL = "https://api.huiniao.top/interface/home/lotteryHistory"
SEGMENT_PATTERNS = {
    "2-2-6": [2, 2, 6],
    "2-3-5": [2, 3, 5],
    "3-3-4": [3, 3, 4],
    "5-5": [5, 5],
}
ADVANCED_CONDITION_TYPES = {
    "sum",
    "sum_tail",
    "average",
    "ac",
    "odd_even",
    "big_small",
    "span",
    "mod012",
    "size_area",
}
ADVANCED_CONDITION_LABELS = {
    "sum": "和值",
    "sum_tail": "和尾",
    "average": "平均值",
    "ac": "AC值",
    "odd_even": "奇偶比",
    "big_small": "大小比",
    "span": "跨度",
    "mod012": "012路比",
    "size_area": "小中大",
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
        curl_cmd = [
            "curl.exe",
            "--silent",
            "--show-error",
            "--location",
            "--fail",
            "--max-time",
            str(max(1, int(timeout))),
        ]
        for key, value in headers.items():
            curl_cmd.extend(["-H", f"{key}: {value}"])
        curl_cmd.append(url)
        try:
            completed = subprocess.run(
                curl_cmd,
                capture_output=True,
                timeout=timeout + 10,
            )
        except (OSError, subprocess.SubprocessError) as curl_error:
            raise RuntimeError(f"request failed: {first_error}; curl fallback failed: {curl_error}") from curl_error
        if completed.returncode != 0 or not completed.stdout:
            stderr = completed.stderr.decode("utf-8", "ignore").strip()
            raise RuntimeError(f"request failed: {first_error}; curl fallback failed: {stderr}")
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


def parse_huiniao_draw_records(data):
    root = data.get("data", {}) if isinstance(data, dict) else {}
    list_data = root.get("data", {}) if isinstance(root.get("data", {}), dict) else {}
    items = list_data.get("list", [])
    if not items and isinstance(root.get("last"), dict):
        items = [root["last"]]

    records = []
    for item in items:
        if not isinstance(item, dict):
            continue
        issue = str(item.get("code", "")).strip()
        digits = [item.get("one"), item.get("two"), item.get("three")]
        draw = "".join(str(d).strip() for d in digits)
        date = str(item.get("day") or item.get("open_time") or "").split(" ")[0].strip()
        if issue.isdigit() and len(issue) >= 5 and draw.isdigit() and len(draw) == 3:
            records.append({"issue": issue, "draw": draw, "date": date})
    if not records:
        raise RuntimeError("huiniao draw api returned no valid records")
    return records


def fetch_huiniao_recent(limit=80):
    url = f"{HUINIAO_HISTORY_URL}?type=fcsd&page=1&limit={int(limit)}"
    text = http_get_text(url, {"User-Agent": "Mozilla/5.0"}, timeout=20)
    return parse_huiniao_draw_records(json.loads(text))


def parse_3d178_draw_records(html):
    records = []
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    row_pattern = re.compile(
        r'<td\s+class="td_qh"[^>]*>\s*<a[^>]+href="/kaijiang/\d{4}/(?P<issue>\d{5,})\.shtml"[^>]*>\s*(?P=issue)\s*</a>\s*</td>\s*'
        r'<td\s+class="td_code"[^>]*>(?P<code>.*?)<td>\s*(?P<date>\d{4}-\d{2}-\d{2})\s*</td>',
        re.S,
    )
    for match in row_pattern.finditer(html):
        digits = re.findall(r"<span>\s*(\d)\s*</span>", match.group("code"))
        draw = "".join(digits[:3])
        issue = match.group("issue")
        if issue.isdigit() and len(draw) == 3:
            records.append({"issue": issue, "draw": draw, "date": match.group("date")})
    if not records:
        raise RuntimeError("3d178 draw page returned no valid records")
    return records


def fetch_3d178_recent(year=None):
    year = year or datetime.date.today().year
    url = THREED178_YEAR_URL.format(year=year)
    html = http_get_text(url, {"User-Agent": "Mozilla/5.0"}, timeout=20)
    return parse_3d178_draw_records(html)


def fetch_official_recent_pages(pages=OFFICIAL_FETCH_PAGES, size=OFFICIAL_PAGE_SIZE):
    records = []
    seen = set()
    huiniao_error_msg = ""
    ip138_error_msg = ""
    threed178_error_msg = ""
    try:
        for record in fetch_huiniao_recent(size * pages):
            issue = str(record.get("issue", ""))
            if issue in seen:
                continue
            seen.add(issue)
            records.append(record)
    except Exception as huiniao_error:
        huiniao_error_msg = str(huiniao_error)

    try:
        for record in fetch_ip138_recent():
            issue = str(record.get("issue", ""))
            if issue in seen:
                continue
            seen.add(issue)
            records.append(record)
    except Exception as ip138_error:
        ip138_error_msg = str(ip138_error)

    try:
        for record in fetch_3d178_recent():
            issue = str(record.get("issue", ""))
            if issue in seen:
                continue
            seen.add(issue)
            records.append(record)
    except Exception as threed178_error:
        threed178_error_msg = str(threed178_error)

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
        if not records:
            raise RuntimeError(f"all draw sources failed; huiniao: {huiniao_error_msg}; ip138: {ip138_error_msg}; 3d178: {threed178_error_msg}; official: {official_error}") from official_error
    if not records:
        raise RuntimeError(f"all draw sources returned no valid records; huiniao: {huiniao_error_msg}; ip138: {ip138_error_msg}; 3d178: {threed178_error_msg}")
    records.sort(key=lambda r: int(str(r.get("issue", "0"))) if str(r.get("issue", "")).isdigit() else 0, reverse=True)
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


def issue_number(record_or_issue):
    issue = record_or_issue if isinstance(record_or_issue, str) else record_or_issue.get("issue", "")
    issue = str(issue)
    return int(issue) if issue.isdigit() else None


def latest_issue_year(records):
    years = []
    for record in records:
        issue = str(record.get("issue", ""))
        if issue.isdigit() and len(issue) >= 5:
            years.append(issue[:4])
    return max(years) if years else ""


def next_issue(records):
    year = latest_issue_year(records)
    numeric = []
    for record in records:
        issue = str(record.get("issue", ""))
        if issue.isdigit() and (not year or issue.startswith(year)):
            numeric.append(int(issue))
    if not numeric:
        return ""
    ordered = sorted(set(numeric))
    current = ordered[0]
    for issue in ordered[1:]:
        if issue == current + 1:
            current = issue
        elif issue > current + 1:
            break
    return str(current + 1)


def contiguous_draw_update(existing_records, fetched_records):
    existing_nums = {issue_number(record) for record in existing_records}
    existing_nums.discard(None)
    fetched_by_num = {}
    for record in fetched_records:
        num = issue_number(record)
        if num is not None:
            fetched_by_num[num] = record

    if not fetched_by_num:
        return [], []
    if not existing_nums:
        return list(fetched_by_num.values()), []

    max_existing = max(existing_nums)
    allowed_nums = {num for num in fetched_by_num if num <= max_existing}
    expected = max_existing + 1
    missing = []
    for num in sorted(n for n in fetched_by_num if n > max_existing):
        if num == expected:
            allowed_nums.add(num)
            expected += 1
        elif num > expected:
            missing = list(range(expected, num))
            break

    mergeable = [fetched_by_num[num] for num in sorted(allowed_nums, reverse=True)]
    return mergeable, [str(num) for num in missing]


def fetch_and_merge_draw_records():
    existing = load_draw_records()
    source_warning = ""
    try:
        fetched = fetch_official_recent_pages()
    except Exception as batch_error:
        source_warning = str(batch_error)
        try:
            fetched = [fetch_latest_draw()]
        except Exception as latest_error:
            raise RuntimeError(f"all draw sources failed; batch: {batch_error}; latest: {latest_error}") from latest_error
    mergeable, missing = contiguous_draw_update(existing, fetched)
    if mergeable:
        records, added = merge_draw_records(mergeable)
    else:
        records, added = existing, 0
    records.sort(key=lambda r: str(r.get("issue", "")), reverse=True)
    return records, added, fetched, missing, source_warning


def recent_draw_records(limit=10):
    records = load_draw_records()
    records.sort(key=lambda r: str(r.get("issue", "")), reverse=True)
    return records[:limit]


def group_hit(filtered, draw):
    if not filtered or not draw:
        return False
    draw_key = "".join(sorted(draw))
    return any("".join(sorted(str(n).zfill(3))) == draw_key for n in filtered)


def direct_hit(filtered, draw):
    if not filtered or not draw:
        return False
    draw = str(draw).zfill(3)
    return any(str(n).zfill(3) == draw for n in filtered)


def history_item_hit(item, draw):
    request = item.get("request") if isinstance(item.get("request"), dict) else {}
    base_mode = str(item.get("base_mode") or item.get("pool_mode") or request.get("base_mode") or request.get("pool_mode") or "input")
    if base_mode in ("direct", "full"):
        return direct_hit(item.get("filtered", []), draw)
    return group_hit(item.get("filtered", []), draw)


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
    normalized_codes = []
    for item in codes:
        digits = str(item.get("digits", ""))
        if not digits:
            continue
        raw_len = item.get("len", item.get("code_len", len(digits)))
        try:
            code_len = int(raw_len)
        except (TypeError, ValueError):
            return {"ok": False, "error": "码数必须是数字"}, 400
        if code_len != len(digits):
            return {"ok": False, "error": f"{digits} 是{len(digits)}码，不能标记为{code_len}码"}, 400
        try:
            combos = generate_code_combos(digits)
        except ValueError as e:
            return {"ok": False, "error": str(e)}, 400
        all_generated.update(combos)
        normalized_codes.append({"digits": digits, "len": code_len})
    if not all_generated:
        return {"ok": False, "error": "没有有效的复式码"}, 400
    generated = sorted(all_generated)
    return {
        "ok": True,
        "generated": generated,
        "count": len(generated),
        "codes": normalized_codes,
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


def normalize_segment_tolerance(data):
    try:
        value = int(data.get("segment_tolerance", data.get("segmentTolerance", 0)))
    except (TypeError, ValueError):
        value = 0
    return max(0, min(2, value))


def passes_segment_filters(number, segment_filters, tolerance=0):
    if not segment_filters:
        return True
    allowed_misses = normalize_segment_tolerance({"segment_tolerance": tolerance})
    misses = sum(
        1
        for item in segment_filters
        if not passes_segment_pattern(number, item["groups"], item["mode"])
    )
    return misses <= allowed_misses


def validate_code_filter(item):
    code_len = int(item.get("code_len", 3))
    if code_len < 3 or code_len > 8:
        raise ValueError(f"码数必须在3-8之间，当前为{code_len}")
    condition = item.get("condition", "012")
    if condition not in ("01", "012", "123", "23"):
        raise ValueError(f"条件只能是01、012、123或23，当前为{condition}")
    digits = str(item.get("digits", ""))
    if len(digits) != code_len:
        raise ValueError(f"需要恰好{code_len}个数字，当前有{len(digits)}个")
    if not digits.isdigit() or len(set(digits)) != len(digits):
        raise ValueError(f"数字必须是不重复的0-9数字")
    raw_count_repeat = item.get("count_repeat", False)
    if isinstance(raw_count_repeat, str):
        count_repeat = raw_count_repeat.strip().lower() in ("1", "true", "yes", "repeat", "count")
    else:
        count_repeat = bool(raw_count_repeat)
    return {"code_len": code_len, "condition": condition, "digits": digits, "count_repeat": count_repeat}


def passes_code_filter(number, code_filter):
    digits = code_filter["digits"]
    condition = code_filter["condition"]
    if code_filter.get("count_repeat"):
        count = sum(1 for d in number if d in digits)
    else:
        count = len(set(number) & set(digits))
    if condition == "01":
        return count in (0, 1)
    elif condition == "012":
        return count in (0, 1, 2)
    elif condition == "123":
        return count in (1, 2, 3)
    elif condition == "23":
        return count in (2, 3)
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
        f"{cf['code_len']}码={cf['condition']}[{cf['digits']}]{'同号计重' if cf.get('count_repeat') else '同号不计重'}"
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
    if kind == "average":
        return _range_values(values, 0, 9, "平均值")
    if kind == "ac":
        return _range_values(values, 1, 3, "AC值")
    if kind in ("sum_tail", "span"):
        label = "和尾" if kind == "sum_tail" else "跨度"
        return _range_values(values, 0, 9, label)
    if kind in ("odd_even", "big_small"):
        label = "奇偶比" if kind == "odd_even" else "大小比"
        return _ratio_values(values, 2, label)
    if kind in ("mod012", "size_area"):
        label = "012路比" if kind == "mod012" else "小中大"
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
    if kind == "average":
        return str(int(sum(digits) / 3 + 0.5))
    if kind == "ac":
        return str(ac_value(number))
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


def segment_desc(segment_filters, tolerance=0):
    text = "; ".join(
        f"{item['mode']} segment [" + " | ".join(item["groups_data"]) + "]"
        for item in segment_filters
    )
    tolerance = normalize_segment_tolerance({"segment_tolerance": tolerance})
    if text and tolerance:
        text += f"; 容错{tolerance}"
    return text


def get_alias(data, *names, default=None):
    for name in names:
        if name in data:
            return data.get(name)
    return default


def unique_numbers_from_text(text):
    matches = re.findall(r"\b\d{3}\b", text or "")
    seen = set()
    unique = []
    for m in matches:
        if m not in seen:
            seen.add(m)
            unique.append(m)
    return unique


def number_shape(number):
    unique_count = len(set(number))
    if unique_count == 1:
        return "baozi"
    if unique_count == 2:
        return "group3"
    return "group6"


def generate_base_pool(mode="input"):
    mode = str(mode or "input").lower()
    if mode in ("direct", "full"):
        return [f"{i:03d}" for i in range(1000)]
    if mode == "baozi":
        return [str(i) * 3 for i in range(10)]

    result = []
    for i in range(1000):
        number = f"{i:03d}"
        shape = number_shape(number)
        if mode == "group3" and shape != "group3":
            continue
        if mode == "group6" and shape != "group6":
            continue
        if mode == "group" and shape not in ("group3", "group6"):
            continue
        if mode in ("group", "group3", "group6"):
            number = "".join(sorted(number))
        result.append(number)

    if mode in ("group", "group3", "group6"):
        return sorted(set(result))
    if mode == "input":
        return []
    raise ValueError(f"invalid base_mode: {mode}")


def normalize_base_mode(data):
    return str(get_alias(data, "base_mode", "baseMode", "pool_mode", "poolMode", default="input") or "input").lower()


def _digits_set(raw, label):
    if raw is None:
        return set()
    if isinstance(raw, list):
        raw = "".join(str(item) for item in raw)
    text = str(raw).strip()
    if not text:
        return set()
    if not text.isdigit():
        raise ValueError(f"{label} must contain digits only")
    return set(text)


def normalize_position_filter(data):
    raw = get_alias(data, "position_filter", "positionFilter")
    if not isinstance(raw, dict):
        return {"include": [set(), set(), set()], "exclude": [set(), set(), set()], "enabled": False}

    include_raw = raw.get("include", raw.get("keep", []))
    exclude_raw = raw.get("exclude", raw.get("kill", []))
    include_raw = include_raw if isinstance(include_raw, list) else []
    exclude_raw = exclude_raw if isinstance(exclude_raw, list) else []

    include = []
    exclude = []
    for idx in range(3):
        include.append(_digits_set(include_raw[idx] if idx < len(include_raw) else "", f"position include {idx}"))
        exclude.append(_digits_set(exclude_raw[idx] if idx < len(exclude_raw) else "", f"position exclude {idx}"))
    for idx in range(3):
        overlap = include[idx] & exclude[idx]
        if overlap:
            raise ValueError(f"position {idx + 1} include/exclude conflict: {''.join(sorted(overlap))}")
    return {
        "include": include,
        "exclude": exclude,
        "enabled": any(include) or any(exclude),
    }


def passes_position_filter(number, position_filter):
    if not position_filter.get("enabled"):
        return True
    for idx, digit in enumerate(number):
        include = position_filter["include"][idx]
        exclude = position_filter["exclude"][idx]
        if include and digit not in include:
            return False
        if exclude and digit in exclude:
            return False
    return True


def serialize_position_filter(position_filter):
    return {
        "include": ["".join(sorted(values)) for values in position_filter.get("include", [])],
        "exclude": ["".join(sorted(values)) for values in position_filter.get("exclude", [])],
    }


def _int_values(raw, low, high, label):
    if raw is None:
        return []
    values = raw if isinstance(raw, list) else [raw]
    result = []
    for item in values:
        text = str(item).strip()
        if not text:
            continue
        if not text.isdigit():
            raise ValueError(f"{label} must contain numbers")
        value = int(text)
        if value < low or value > high:
            raise ValueError(f"{label} must be between {low} and {high}")
        result.append(value)
    return sorted(set(result))


def normalize_shape_filter(data):
    raw = get_alias(data, "shape_filter", "shapeFilter")
    if not isinstance(raw, dict):
        return {"types": [], "mode": "include", "prime_count": [], "values": [], "enabled": False}
    types = raw.get("types", [])
    types = types if isinstance(types, list) else [types]
    allowed = {
        "baozi",
        "group3",
        "group6",
        "pair",
        "consecutive",
        "semi_consecutive",
        "prime_composite",
    }
    normalized_types = []
    for item in types:
        kind = str(item).strip().lower()
        if not kind:
            continue
        if kind not in allowed:
            raise ValueError(f"invalid shape type: {kind}")
        normalized_types.append(kind)
    mode = str(raw.get("mode", "include") or "include").lower()
    if mode not in ("include", "exclude"):
        raise ValueError("shape_filter mode must be include or exclude")
    prime_count = _int_values(raw.get("prime_count", raw.get("primeCount", raw.get("values", []))), 0, 3, "prime_count")
    return {
        "types": sorted(set(normalized_types)),
        "mode": mode,
        "prime_count": prime_count,
        "values": prime_count,
        "enabled": bool(normalized_types),
    }


def is_consecutive(number):
    digits = sorted(set(int(d) for d in number))
    if len(digits) != 3:
        return False
    return digits[1] == digits[0] + 1 and digits[2] == digits[1] + 1


def is_semi_consecutive(number):
    digits = sorted(set(int(d) for d in number))
    if len(digits) < 2 or is_consecutive(number):
        return False
    return any(digits[i + 1] - digits[i] == 1 for i in range(len(digits) - 1))


def shape_type_hit(number, kind, shape_filter=None):
    shape = number_shape(number)
    if kind == "pair":
        return shape == "group3"
    if kind in ("baozi", "group3", "group6"):
        return shape == kind
    if kind == "consecutive":
        return is_consecutive(number)
    if kind == "semi_consecutive":
        return is_semi_consecutive(number)
    if kind == "prime_composite":
        prime_count = sum(1 for d in number if d in "2357")
        allowed = (shape_filter or {}).get("prime_count") or (shape_filter or {}).get("values")
        return prime_count in allowed if allowed else True
    return False


def passes_shape_filter(number, shape_filter):
    if not shape_filter.get("enabled"):
        return True
    hit = any(shape_type_hit(number, kind, shape_filter) for kind in shape_filter["types"])
    return hit if shape_filter.get("mode") != "exclude" else not hit


def normalize_pair_filter(data):
    raw = get_alias(data, "pair_filter", "pairFilter")
    if not isinstance(raw, dict):
        return {"pair_sums": [], "pair_sum_tails": [], "pair_diffs": [], "mode": "include", "enabled": False}
    mode = str(raw.get("mode", "include") or "include").lower()
    if mode not in ("include", "exclude"):
        raise ValueError("pair_filter mode must be include or exclude")
    result = {
        "pair_sums": _int_values(raw.get("pair_sums", raw.get("pairSums", [])), 0, 18, "pair_sums"),
        "pair_sum_tails": _int_values(raw.get("pair_sum_tails", raw.get("pairSumTails", [])), 0, 9, "pair_sum_tails"),
        "pair_diffs": _int_values(raw.get("pair_diffs", raw.get("pairDiffs", [])), 0, 9, "pair_diffs"),
        "mode": mode,
    }
    result["enabled"] = bool(result["pair_sums"] or result["pair_sum_tails"] or result["pair_diffs"])
    return result


def pair_values(number):
    digits = [int(d) for d in number]
    pairs = ((digits[0], digits[1]), (digits[0], digits[2]), (digits[1], digits[2]))
    return {
        "pair_sums": [a + b for a, b in pairs],
        "pair_sum_tails": [(a + b) % 10 for a, b in pairs],
        "pair_diffs": [abs(a - b) for a, b in pairs],
    }


def passes_pair_filter(number, pair_filter):
    if not pair_filter.get("enabled"):
        return True
    values = pair_values(number)
    hit = (
        bool(set(pair_filter["pair_sums"]) & set(values["pair_sums"]))
        or bool(set(pair_filter["pair_sum_tails"]) & set(values["pair_sum_tails"]))
        or bool(set(pair_filter["pair_diffs"]) & set(values["pair_diffs"]))
    )
    return hit if pair_filter.get("mode") != "exclude" else not hit


def _string_values(raw, allowed, label):
    if raw is None:
        return []
    values = raw if isinstance(raw, list) else [raw]
    allowed_set = set(allowed)
    result = []
    for item in values:
        value = str(item).strip()
        if not value:
            continue
        if value not in allowed_set:
            raise ValueError(f"{label} contains invalid value: {value}")
        result.append(value)
    return sorted(set(result))


def _pattern_values(chars, length):
    result = [""]
    for _ in range(length):
        result = [prefix + ch for prefix in result for ch in chars]
    return result


def _two_count_values():
    return [f"{count}:{3 - count}" for count in range(4)]


def _three_count_values():
    return [
        f"{a}:{b}:{3 - a - b}"
        for a in range(3, -1, -1)
        for b in range(3 - a, -1, -1)
    ]


def _pair_code_values():
    return [f"{a}{b}" for a in range(10) for b in range(a, 10)]


def ac_value(number):
    digits = [int(d) for d in number]
    diffs = {
        abs(digits[0] - digits[1]),
        abs(digits[0] - digits[2]),
        abs(digits[1] - digits[2]),
    }
    return len(diffs)


RULE_FILTER_META = {
    "sum": {"kind": "int", "low": 0, "high": 27},
    "sum_tail": {"kind": "int", "low": 0, "high": 9},
    "average": {"kind": "int", "low": 0, "high": 9},
    "ac": {"kind": "int", "low": 1, "high": 3},
    "span": {"kind": "int", "low": 0, "high": 9},
    "first_last_diff": {"kind": "int", "low": 0, "high": 9},
    "pair_sum": {"kind": "int", "low": 0, "high": 18},
    "pair_sum_tail": {"kind": "int", "low": 0, "high": 9},
    "pair_diff": {"kind": "int", "low": 0, "high": 9},
    "pair_sum_diff": {"kind": "int", "low": 0, "high": 18},
    "pair_code": {"kind": "string", "allowed": _pair_code_values()},
    "mod012": {"kind": "string", "allowed": _pattern_values("012", 3)},
    "big_small": {"kind": "string", "allowed": _pattern_values("BS", 3)},
    "odd_even": {"kind": "string", "allowed": _pattern_values("OE", 3)},
    "prime_composite": {"kind": "string", "allowed": _pattern_values("PC", 3)},
    "big_small_count": {"kind": "string", "allowed": _two_count_values()},
    "odd_even_count": {"kind": "string", "allowed": _two_count_values()},
    "prime_composite_count": {"kind": "string", "allowed": _two_count_values()},
    "mod012_count": {"kind": "string", "allowed": _three_count_values()},
    "size_area": {"kind": "string", "allowed": _pattern_values("LMH", 3)},
}


def normalize_rule_filters(data):
    raw = get_alias(data, "rule_filters", "ruleFilters", default=[])
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        if not isinstance(item, dict) or item.get("enabled") is False:
            continue
        kind = str(item.get("type", item.get("kind", ""))).strip()
        if kind not in RULE_FILTER_META:
            raise ValueError(f"invalid rule filter type: {kind}")
        mode = str(item.get("mode", "include") or "include").lower()
        if mode not in ("include", "exclude"):
            raise ValueError(f"{kind} mode must be include or exclude")
        meta = RULE_FILTER_META[kind]
        if meta["kind"] == "int":
            values = _int_values(item.get("values", []), meta["low"], meta["high"], kind)
            values = [str(v) for v in values]
        else:
            values = _string_values(item.get("values", []), meta["allowed"], kind)
        if values:
            result.append({"type": kind, "mode": mode, "values": values})
    return result


def rule_filter_values(number, kind):
    digits = [int(d) for d in number]
    if kind == "sum":
        return {str(sum(digits))}
    if kind == "sum_tail":
        return {str(sum(digits) % 10)}
    if kind == "average":
        return {str(int(sum(digits) / 3 + 0.5))}
    if kind == "ac":
        return {str(ac_value(number))}
    if kind == "span":
        return {str(max(digits) - min(digits))}
    if kind == "first_last_diff":
        return {str(abs(digits[0] - digits[2]))}
    pairs = ((digits[0], digits[1], digits[2]), (digits[0], digits[2], digits[1]), (digits[1], digits[2], digits[0]))
    if kind == "pair_sum":
        return {str(a + b) for a, b, _ in pairs}
    if kind == "pair_sum_tail":
        return {str((a + b) % 10) for a, b, _ in pairs}
    if kind == "pair_diff":
        return {str(abs(a - b)) for a, b, _ in pairs}
    if kind == "pair_sum_diff":
        return {str(abs((a + b) - c)) for a, b, c in pairs}
    if kind == "pair_code":
        return {"".join(sorted((str(a), str(b)))) for a, b, _ in pairs}
    if kind == "mod012":
        return {"".join(str(d % 3) for d in digits)}
    if kind == "big_small":
        return {"".join("B" if d >= 5 else "S" for d in digits)}
    if kind == "odd_even":
        return {"".join("O" if d % 2 else "E" for d in digits)}
    if kind == "prime_composite":
        return {"".join("P" if str(d) in "2357" else "C" for d in digits)}
    if kind == "big_small_count":
        big = sum(1 for d in digits if d >= 5)
        return {f"{big}:{3 - big}"}
    if kind == "odd_even_count":
        odd = sum(1 for d in digits if d % 2)
        return {f"{odd}:{3 - odd}"}
    if kind == "prime_composite_count":
        prime = sum(1 for d in number if d in "2357")
        return {f"{prime}:{3 - prime}"}
    if kind == "mod012_count":
        counts = [0, 0, 0]
        for d in digits:
            counts[d % 3] += 1
        return {":".join(str(n) for n in counts)}
    if kind == "size_area":
        return {"".join("L" if d <= 2 else "M" if d <= 6 else "H" for d in digits)}
    return set()


def passes_rule_filters(number, rule_filters):
    for item in rule_filters:
        values = rule_filter_values(number, item["type"])
        hit = bool(values & set(item["values"]))
        if item["mode"] == "include" and not hit:
            return False
        if item["mode"] == "exclude" and hit:
            return False
    return True


def apply_filter_step(numbers, name, predicate, steps):
    before = len(numbers)
    filtered = [n for n in numbers if predicate(n)]
    steps.append({"name": name, "before": before, "after": len(filtered)})
    return filtered


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
        base_mode = normalize_base_mode(data)
        digits = data.get("digits", "")
        advance_digits = data.get("advance_digits", "")
        kill_digits = data.get("kill_digits", "")
        segment_filters = normalize_segment_filters(data)
        segment_tolerance = normalize_segment_tolerance(data)
        code_filters = normalize_code_filters(data)
        advanced_filter = normalize_advanced_filter(data)
        position_filter = normalize_position_filter(data)
        shape_filter = normalize_shape_filter(data)
        pair_filter = normalize_pair_filter(data)
        rule_filters = normalize_rule_filters(data)

        if base_mode in ("group", "group3", "group6", "baozi") and position_filter["enabled"]:
            raise ValueError("定位筛选需要使用直选全量或输入原始三位号码池，不能用于组选代表号大底")

        unique = unique_numbers_from_text(text) if base_mode == "input" else generate_base_pool(base_mode)

        target_include = set(digits) if digits else set()
        target_advance = set(advance_digits) if advance_digits else set()
        target_kill = set(kill_digits) if kill_digits else set()
        overlap = target_include & target_kill
        if overlap:
            raise ValueError(f"胆码和杀码冲突：{''.join(sorted(overlap))}")

        if (
            not target_include
            and not target_advance
            and not target_kill
            and not segment_filters
            and not code_filters
            and not advanced_filter["enabled"]
            and not position_filter["enabled"]
            and not shape_filter["enabled"]
            and not pair_filter["enabled"]
            and not rule_filters
            and base_mode == "input"
        ):
            self._send_json({"error": "please enter at least one filter condition"}, 400)
            return

        steps = []
        filtered = unique[:]

        def passes_legacy_filters(n):
            if advanced_filter["enabled"] and not passes_advanced_filter(n, advanced_filter):
                return False
            if target_kill and any(d in n for d in target_kill):
                return False
            if target_include and not any(d in n for d in target_include):
                return False
            if target_advance:
                a, b, c = int(n[0]), int(n[1]), int(n[2])
                adv_set = {abs(a - b), abs(a - c), abs(b - c)}
                if not any(str(d) in target_advance for d in adv_set):
                    return False
            if not passes_segment_filters(n, segment_filters, segment_tolerance):
                return False
            if any(not passes_code_filter(n, cf) for cf in code_filters):
                return False
            return True

        filtered = apply_filter_step(filtered, "legacy", passes_legacy_filters, steps)
        if position_filter["enabled"]:
            filtered = apply_filter_step(filtered, "position_filter", lambda n: passes_position_filter(n, position_filter), steps)
        if shape_filter["enabled"]:
            filtered = apply_filter_step(filtered, "shape_filter", lambda n: passes_shape_filter(n, shape_filter), steps)
        if pair_filter["enabled"]:
            filtered = apply_filter_step(filtered, "pair_filter", lambda n: passes_pair_filter(n, pair_filter), steps)
        if rule_filters:
            filtered = apply_filter_step(filtered, "rule_filters", lambda n: passes_rule_filters(n, rule_filters), steps)

        self._send_json({
            "total": len(unique),
            "filtered": filtered,
            "count": len(filtered),
            "percent": round(len(filtered) / len(unique) * 100, 2) if unique else 0,
            "base_mode": base_mode,
            "advance_digits": advance_digits,
            "segment": segment_desc(segment_filters, segment_tolerance),
            "segment_tolerance": segment_tolerance,
            "segment_filters": [
                {"mode": item["mode"], "groups": item["groups_data"]}
                for item in segment_filters
            ],
            "code_desc": code_filter_desc(code_filters),
            "code_filters": [
                {"code_len": cf["code_len"], "condition": cf["condition"], "digits": cf["digits"], "count_repeat": cf.get("count_repeat", False)}
                for cf in code_filters
            ],
            "advanced_desc": advanced_filter_desc(advanced_filter),
            "advanced_filter": {
                "conditions": advanced_filter["conditions"],
                "miss_min": advanced_filter["miss_min"],
                "miss_max": advanced_filter["miss_max"],
            },
            "position_filter": serialize_position_filter(position_filter),
            "shape_filter": {
                "types": shape_filter["types"],
                "mode": shape_filter["mode"],
                "prime_count": shape_filter["prime_count"],
                "values": shape_filter["values"],
            },
            "pair_filter": {
                "pair_sums": pair_filter["pair_sums"],
                "pair_sum_tails": pair_filter["pair_sum_tails"],
                "pair_diffs": pair_filter["pair_diffs"],
                "mode": pair_filter["mode"],
            },
            "rule_filters": rule_filters,
            "steps": steps,
        })

    def _api_generate_codes(self):
        data = self._read_json_body()
        codes = data.get("codes", [])
        result, status = process_generate_codes(codes)
        self._send_json(result, status)

    def _api_update_draws(self):
        try:
            records, added, new_records, missing, source_warning = fetch_and_merge_draw_records()
            warning = ""
            if source_warning:
                if missing:
                    warning = f"批量开奖更新失败，已切换到最新一期兜底，但本地与新开奖号之间缺少 {'、'.join(missing)}，已停止写入后续期号：{source_warning}"
                elif added > 0:
                    warning = f"批量开奖更新失败，已切换到最新一期兜底并完成补写：{source_warning}"
                else:
                    warning = f"批量开奖更新失败，已切换到最新一期兜底，但未新增写入：{source_warning}"
            self._send_json({
                "ok": True,
                "updated": True,
                "added": added,
                "fetched": len(new_records),
                "missingIssues": missing,
                "warning": warning or (f"远端开奖存在跳期，缺少 {'、'.join(missing)}，已停止写入后续期号" if missing else ""),
                "latest": records[0] if records else None,
                "nextIssue": next_issue(records),
                "count": len(records),
                "records": records[:DRAW_LIST_LIMIT],
            })
        except (RuntimeError, urllib.error.URLError, TimeoutError, OSError) as e:
            records = recent_draw_records(DRAW_LIST_LIMIT)
            if not records:
                self._send_json({
                    "ok": True,
                    "updated": False,
                    "error": f"批量开奖更新失败，本地也没有可用于回查的开奖数据：{e}",
                    "added": 0,
                    "fetched": 0,
                    "latest": None,
                    "nextIssue": "",
                    "count": 0,
                    "records": [],
                })
                return
            self._send_json({
                "ok": True,
                "updated": True,
                "warning": f"批量开奖更新失败，已保留本地已有开奖，未写入最新一期以避免跳期：{e}",
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
            next_item["hit"] = history_item_hit(item, draw.get("draw", ""))
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
