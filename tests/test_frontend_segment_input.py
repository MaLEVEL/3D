from pathlib import Path


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
