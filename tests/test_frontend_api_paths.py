from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_file_opened_page_uses_localhost_api_base():
    html = (ROOT / "index.html").read_text(encoding="utf-8")

    assert "function apiPath(path)" in html
    assert 'window.location.protocol === "file:"' in html
    assert '"http://127.0.0.1:5000" + path' in html
    assert "fetch(apiPath(path), request.config)" in html
