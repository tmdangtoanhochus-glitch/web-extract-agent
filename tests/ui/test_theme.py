"""Giao diện dùng chung: huy hiệu MSB mặc định, tự nhận logo khi có file, CSS tab nổi khối."""
from ui import theme


def test_logo_falls_back_to_msb_badge_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(theme, "_ASSETS", tmp_path)
    assert "mp-logo-badge" in theme.logo_html() and "MSB" in theme.logo_html()
    assert "🧡" not in theme.logo_html()


def test_logo_uses_asset_file_when_present(tmp_path, monkeypatch):
    (tmp_path / "msb_logo.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    monkeypatch.setattr(theme, "_ASSETS", tmp_path)
    html = theme.logo_html()
    assert "mp-logo-img" in html and "data:image/png;base64," in html


def test_css_styles_tabs_as_raised_blocks_for_both_streamlit_dom_variants():
    assert 'div[role="tab"]' in theme.CSS and 'button[data-baseweb="tab"]' in theme.CSS
    assert "box-shadow" in theme.CSS and "aria-selected" in theme.CSS
