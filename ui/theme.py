"""Giao diện dùng chung cho Crawl, Automation và Admin (cùng banner, thẻ nổi khối, tab nổi khối, logo MSB).

Logo: thả một file ảnh (.png/.svg/.jpg/.webp, tên bất kỳ) vào `ui/assets/` — nếu có, banner và biểu tượng tab dùng file đó;
chưa có thì dùng huy hiệu chữ "MSB" cùng bảng màu.
"""
from __future__ import annotations

import base64
import io
from functools import lru_cache
from pathlib import Path
from typing import Optional

import streamlit as st

_ASSETS = Path(__file__).resolve().parent / "assets"
_LOGO_NAMES = ("msb_logo.png", "msb_logo.svg", "msb_logo.jpg", "msb_logo.jpeg", "msb_logo.webp")
_MIME = {".png": "image/png", ".svg": "image/svg+xml", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}

CSS = """
<style>
:root {
  --msb-orange:#FF671F; --msb-red:#ED1C24; --msb-sun:#FFB81C;
  --msb-border:#F0E2DA; --msb-green:#1BA672; --msb-blue:#2E6FE7;
  --mp-shadow:0 2px 6px rgba(120,60,20,.10), 0 8px 20px rgba(120,60,20,.08);
  --mp-shadow-hover:0 4px 10px rgba(120,60,20,.16), 0 12px 26px rgba(120,60,20,.12);
}
.stApp { background:#FBF6F3; }

/* Banner */
.mp-hero {
  background:linear-gradient(120deg,var(--msb-red) 0%, var(--msb-orange) 60%, var(--msb-sun) 100%);
  color:#fff; padding:20px 26px; border-radius:16px; margin-bottom:18px;
  box-shadow:0 6px 18px rgba(237,28,36,.25);
  display:flex; align-items:center; gap:16px;
}
.mp-hero h1 { margin:0 0 4px 0; font-size:22px; color:#fff; }
.mp-hero p { margin:0; opacity:.92; font-size:13.5px; color:#fff; }
.mp-logo-badge {
  flex:0 0 auto; display:inline-flex; align-items:center; justify-content:center;
  width:52px; height:52px; border-radius:14px; background:#fff; color:var(--msb-red);
  font-weight:800; font-size:16px; letter-spacing:.5px;
  box-shadow:0 3px 10px rgba(0,0,0,.18);
}
.mp-logo-img {
  flex:0 0 auto; height:52px; width:auto; max-width:120px; border-radius:12px; background:#fff; padding:6px;
  box-shadow:0 3px 10px rgba(0,0,0,.18); object-fit:contain;
}
/* Ảnh logo có nền liền (không trong suốt): phủ kín khung, màu khung lấy theo nền ảnh */
.mp-logo-img.solid { padding:0; object-fit:cover; max-width:96px; }

.mp-pill {
  display:inline-flex; align-items:center; gap:6px; background:#FFF1E8; color:var(--msb-red);
  padding:5px 12px; border-radius:20px; font-size:12.5px; font-weight:600; margin:3px 4px 3px 0;
}

/* Thẻ nổi khối */
.mp-card {
  background:#fff; border:1px solid var(--msb-border); border-radius:14px;
  padding:18px 20px; margin-bottom:14px; box-shadow:var(--mp-shadow);
}
.mp-section-label {
  font-size:14px; font-weight:600; color:#333; margin:12px 0 6px 0;
  padding-bottom:4px; border-bottom:2px solid var(--msb-border);
}
.mp-hint {
  background:#F0F7FF; border-left:3px solid var(--msb-blue); padding:8px 12px;
  border-radius:0 6px 6px 0; font-size:13px; color:#444; margin:8px 0;
}

/* Nút */
div.stButton > button, div.stDownloadButton > button, button[kind="secondaryFormSubmit"], button[kind="primaryFormSubmit"] {
  border-radius:12px; box-shadow:var(--mp-shadow); transition:transform .12s ease, box-shadow .12s ease;
}
div.stButton > button:hover, div.stDownloadButton > button:hover {
  transform:translateY(-1px); box-shadow:var(--mp-shadow-hover);
}
div.stButton > button[kind="primary"], button[kind="primaryFormSubmit"] {
  background:linear-gradient(135deg,var(--msb-red),var(--msb-orange)); border:none; color:#fff;
}
div.stButton > button[kind="secondary"]:hover {
  border-color:var(--msb-orange); color:var(--msb-orange);
}

/* Tab nổi khối (hỗ trợ cả DOM baseweb cũ lẫn react-aria của Streamlit mới) */
div[data-baseweb="tab-list"], div[role="tablist"] { gap:10px; padding:6px 4px 12px 4px; border-bottom:none !important; flex-wrap:wrap; }
div[data-baseweb="tab-highlight"], div[data-baseweb="tab-border"], div[role="tablist"] [class*="SelectionIndicator"] { display:none !important; }
div[data-testid="stTabs"] div[data-orientation="horizontal"] { border-bottom:none !important; box-shadow:none !important; }
button[data-baseweb="tab"], div[data-testid="stTab"], div[role="tab"] {
  background:#fff; border:1px solid var(--msb-border); border-radius:12px; padding:9px 16px; height:auto;
  box-shadow:var(--mp-shadow); transition:transform .12s ease, box-shadow .12s ease; cursor:pointer;
}
button[data-baseweb="tab"]:hover, div[data-testid="stTab"]:hover, div[role="tab"]:hover { transform:translateY(-1px); box-shadow:var(--mp-shadow-hover); }
button[data-baseweb="tab"] p, div[data-testid="stTab"] p, div[role="tab"] p { font-weight:600; color:#444; margin:0; }
button[data-baseweb="tab"][aria-selected="true"], div[data-testid="stTab"][aria-selected="true"], div[role="tab"][aria-selected="true"] {
  background:linear-gradient(135deg,var(--msb-red),var(--msb-orange)); border-color:transparent;
  box-shadow:0 6px 16px rgba(237,28,36,.30);
}
button[data-baseweb="tab"][aria-selected="true"] p, div[data-testid="stTab"][aria-selected="true"] p, div[role="tab"][aria-selected="true"] p { color:#fff; }

/* Thẻ mở bằng markdown nhưng không đóng được (rỗng) -> ẩn để không thành khung trắng trơ */
.mp-card:empty { display:none; }

/* Khung mở rộng, form, thông báo: cùng phong cách thẻ */
div[data-testid="stExpander"] { background:#fff; border:1px solid var(--msb-border); border-radius:14px; box-shadow:var(--mp-shadow); }
div[data-testid="stForm"] { background:#fff; border:1px solid var(--msb-border); border-radius:14px; box-shadow:var(--mp-shadow); }
div[data-testid="stAlert"] { border-radius:12px; box-shadow:0 1px 4px rgba(0,0,0,.06); }

/* Thanh bên: nền nổi khối, mục điều hướng dạng thẻ nổi, mục đang chọn có gradient */
section[data-testid="stSidebar"] {
  border-right:1px solid var(--msb-border);
  background:linear-gradient(180deg,#FFFFFF 0%,#FFF5EE 100%);
  box-shadow:6px 0 26px rgba(120,60,20,.12);
}
div[data-testid="stSidebarNavItems"] { gap:10px; padding:8px 12px 12px 12px; }
a[data-testid="stSidebarNavLink"] {
  background:#fff; border:1px solid var(--msb-border); border-radius:14px; padding:12px 16px; margin:0;
  box-shadow:var(--mp-shadow); transition:transform .14s ease, box-shadow .14s ease, border-color .14s ease;
}
a[data-testid="stSidebarNavLink"] span, a[data-testid="stSidebarNavLink"] p { font-weight:600; color:#3a2c26; font-size:15px; }
a[data-testid="stSidebarNavLink"]:hover {
  transform:translateY(-2px) translateX(3px); box-shadow:var(--mp-shadow-hover); border-color:var(--msb-orange);
}
a[data-testid="stSidebarNavLink"][aria-current="page"] {
  background:linear-gradient(135deg,var(--msb-red),var(--msb-orange)); border-color:transparent;
  box-shadow:0 8px 20px rgba(237,28,36,.32);
}
a[data-testid="stSidebarNavLink"][aria-current="page"] span, a[data-testid="stSidebarNavLink"][aria-current="page"] p { color:#fff; }

/* Nút đóng/mở thanh bên: nút vuông bo góc nổi khối, rê chuột chuyển gradient */
div[data-testid="stSidebarCollapseButton"] button, button[data-testid="stExpandSidebarButton"],
div[data-testid="stSidebarCollapsedControl"] button {
  width:42px; height:42px; border-radius:14px; background:#fff; border:1px solid var(--msb-border);
  box-shadow:var(--mp-shadow); transition:transform .14s ease, box-shadow .14s ease, background .14s ease;
  display:inline-flex; align-items:center; justify-content:center; opacity:1;
}
div[data-testid="stSidebarCollapseButton"] button:hover, button[data-testid="stExpandSidebarButton"]:hover,
div[data-testid="stSidebarCollapsedControl"] button:hover {
  transform:translateY(-2px) scale(1.05); box-shadow:var(--mp-shadow-hover);
  background:linear-gradient(135deg,var(--msb-red),var(--msb-orange));
}
div[data-testid="stSidebarCollapseButton"] button:hover *, button[data-testid="stExpandSidebarButton"]:hover *,
div[data-testid="stSidebarCollapsedControl"] button:hover * { color:#fff !important; fill:#fff !important; }

.mp-status-saved { color:var(--msb-green); font-weight:700; }
.mp-status-unchanged { color:#8a8380; font-weight:700; }
.mp-status-warn { color:var(--msb-sun); font-weight:700; }
.mp-status-error { color:var(--msb-red); font-weight:700; }
.mp-step-active {
  background:linear-gradient(135deg,var(--msb-red),var(--msb-orange)) !important;
  color:#fff !important;
}
</style>
"""


def _logo_path() -> Optional[Path]:
    """File logo trong ui/assets: ưu tiên tên `msb_logo.*`, nếu không có thì lấy file ảnh đầu tiên (theo tên) —
    nên `hinh-logo-ngan-hang-msb.webp` hay bất kỳ tên nào đều dùng được, không cần đổi tên."""
    if not _ASSETS.is_dir():
        return None
    for name in _LOGO_NAMES:
        path = _ASSETS / name
        if path.is_file():
            return path
    images = sorted(p for p in _ASSETS.iterdir() if p.is_file() and p.suffix.lower() in _MIME)
    return images[0] if images else None


@lru_cache(maxsize=4)
def _logo_data(path_str: str, mtime: float) -> tuple[str, str | None]:
    """Trả về (data URI, màu nền khung hoặc None).

    - SVG: dùng nguyên file, khung trắng.
    - Ảnh CÓ kênh trong suốt: giữ trong suốt, khung trắng (logo đỏ/cam không chìm vào banner đỏ).
    - Ảnh nền LIỀN (vd. logo trên nền đen có hào quang): lấy màu 4 góc làm màu khung để ảnh hòa vào khung.
    Ảnh được thu nhỏ (<= 320px) để trang nhẹ.
    """
    path = Path(path_str)
    raw = path.read_bytes()
    suffix = path.suffix.lower()
    if suffix == ".svg":
        return f"data:image/svg+xml;base64,{base64.b64encode(raw).decode('ascii')}", None
    try:
        from PIL import Image

        image = Image.open(io.BytesIO(raw))
        image.load()
        has_alpha = image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info)
        if has_alpha:
            rgba = image.convert("RGBA")
            has_alpha = rgba.getchannel("A").getextrema()[0] < 255
        image.thumbnail((320, 320))
        out = io.BytesIO()
        if has_alpha:
            image.convert("RGBA").save(out, format="PNG")
            return f"data:image/png;base64,{base64.b64encode(out.getvalue()).decode('ascii')}", None
        rgb = image.convert("RGB")
        width, height = rgb.size
        corners = [rgb.getpixel(point) for point in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1))]
        color = tuple(sum(channel) // len(corners) for channel in zip(*corners))
        background = None if min(color) > 235 else "#%02x%02x%02x" % color  # nền gần trắng -> giữ khung trắng
        rgb.save(out, format="JPEG", quality=90)
        return f"data:image/jpeg;base64,{base64.b64encode(out.getvalue()).decode('ascii')}", background
    except Exception:  # file ảnh lạ/hỏng: dùng nguyên bản, khung trắng
        return f"data:{_MIME.get(suffix, 'image/png')};base64,{base64.b64encode(raw).decode('ascii')}", None


def logo_html() -> str:
    path = _logo_path()
    if path is None:
        return '<span class="mp-logo-badge">MSB</span>'
    uri, background = _logo_data(str(path), path.stat().st_mtime)
    if background:
        return f'<img class="mp-logo-img solid" alt="MSB" style="background:{background}" src="{uri}">'
    return f'<img class="mp-logo-img" alt="MSB" src="{uri}">'


def apply_theme(page_title: str) -> None:
    """Gọi ĐẦU TIÊN trong mỗi trang (set_page_config phải là lệnh Streamlit đầu tiên)."""
    path = _logo_path()
    icon = str(path) if path is not None and path.suffix.lower() != ".svg" else "🟠"
    st.set_page_config(page_title=page_title, page_icon=icon, layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)


def hero(title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="mp-hero">{logo_html()}<div><h1>{title}</h1><p>{subtitle}</p></div></div>',
        unsafe_allow_html=True,
    )
