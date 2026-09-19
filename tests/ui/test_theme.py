"""Giao diện dùng chung: huy hiệu MSB mặc định, tự nhận logo khi có file, CSS tab nổi khối."""
from ui import theme


def test_logo_falls_back_to_msb_badge_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(theme, "_ASSETS", tmp_path)
    assert "mp-logo-badge" in theme.logo_html() and "MSB" in theme.logo_html()
    assert "🧡" not in theme.logo_html()


def test_logo_uses_asset_file_when_present(tmp_path, monkeypatch):
    from PIL import Image

    image = Image.new("RGBA", (40, 40), (237, 28, 36, 255))
    image.putpixel((0, 0), (0, 0, 0, 0))  # có vùng trong suốt thật
    image.save(tmp_path / "msb_logo.png")
    monkeypatch.setattr(theme, "_ASSETS", tmp_path)
    html = theme.logo_html()
    assert "mp-logo-img" in html and "data:image/png;base64," in html


def test_css_styles_tabs_as_raised_blocks_for_both_streamlit_dom_variants():
    assert 'div[role="tab"]' in theme.CSS and 'button[data-baseweb="tab"]' in theme.CSS
    assert "box-shadow" in theme.CSS and "aria-selected" in theme.CSS


def test_logo_accepts_any_image_filename_and_ignores_non_images(tmp_path, monkeypatch):
    (tmp_path / "README.txt").write_text("x", encoding="utf-8")
    from PIL import Image

    Image.new("RGB", (30, 20), (255, 255, 255)).save(tmp_path / "hinh-logo-ngan-hang-msb.webp")
    monkeypatch.setattr(theme, "_ASSETS", tmp_path)
    html = theme.logo_html()
    assert "data:image/" in html and "mp-logo-badge" not in html


def test_transparent_logo_keeps_white_tile_and_solid_logo_uses_its_own_background(tmp_path, monkeypatch):
    from PIL import Image

    monkeypatch.setattr(theme, "_ASSETS", tmp_path)
    Image.new("RGBA", (60, 40), (0, 0, 0, 0)).save(tmp_path / "msb_logo.png")  # trong suốt hoàn toàn
    assert "solid" not in theme.logo_html() and "data:image/png;base64," in theme.logo_html()

    (tmp_path / "msb_logo.png").unlink()
    Image.new("RGB", (900, 600), (0, 0, 0)).save(tmp_path / "logo-nen-den.jpg")  # nền đen liền như logo hào quang
    theme._logo_data.cache_clear()
    html = theme.logo_html()
    assert "mp-logo-img solid" in html and "background:#000000" in html and "data:image/jpeg;base64," in html


def test_logo_is_downscaled_to_keep_the_page_light(tmp_path, monkeypatch):
    import base64
    import io

    from PIL import Image

    monkeypatch.setattr(theme, "_ASSETS", tmp_path)
    Image.new("RGB", (1536, 1024), (0, 0, 0)).save(tmp_path / "big.jpg")
    theme._logo_data.cache_clear()
    uri, _ = theme._logo_data(str(tmp_path / "big.jpg"), (tmp_path / "big.jpg").stat().st_mtime)
    image = Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1])))
    assert max(image.size) <= 320
