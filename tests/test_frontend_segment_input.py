from pathlib import Path
import json
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_segment_groups_are_text_input_only():
    html = (ROOT / "index.html").read_text(encoding="utf-8")

    assert "data-add-segment" not in html
    assert 'renderPicker("segment-' not in html
    assert "segment-row" not in html


def test_segment_batches_are_visible_and_reusable():
    html = (ROOT / "index.html").read_text(encoding="utf-8")

    assert 'id="segmentBatchSelect"' in html
    assert "function segmentBatchGroups()" in html
    assert "function segmentBatchLabel(batchId)" in html
    assert "function renderSegmentBatchSelect()" in html
    assert "function selectedSegmentBatchId()" in html
    assert "segment-batch-pill" in html
    assert "selectedSegmentBatchId()" in html


def _extract_js_function(source, name):
    marker = f"function {name}"
    start = source.index(marker)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(f"function {name} not found")


def _parse_segment_line(line):
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    function_names = [
        "digitsOnly",
        "cleanDigits",
        "detectSegmentMode",
        "normalizeSegmentGroups",
        "parseBatchSegmentLine",
    ]
    functions = "\n".join(_extract_js_function(html, name) for name in function_names)
    script = f"""
const DIGITS = "0123456789".split("");
const SEGMENT_SIZES = {{"2-2-6":[2,2,6], "2-3-5":[2,3,5], "3-3-4":[3,3,4], "5-5":[5,5]}};
{functions}
console.log(JSON.stringify(parseBatchSegmentLine({json.dumps(line)})));
"""
    result = subprocess.run(["node", "-"], input=script, text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def test_334_segment_line_autofills_last_group_from_remaining_digits():
    assert _parse_segment_line("012-789-1456") == {
        "mode": "3-3-4",
        "groups": ["012", "789", "3456"],
    }
