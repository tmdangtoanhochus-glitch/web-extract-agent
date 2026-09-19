"""Giao diện dùng chung cho Crawl, Automation và Admin (cùng banner, thẻ nổi khối, tab nổi khối, logo MSB).

Logo: đặt file `ui/assets/msb_logo.png` (hoặc .svg/.jpg/.webp) — nếu có, banner và biểu tượng tab dùng file đó;
chưa có thì dùng huy hiệu chữ "MSB" cùng bảng màu.
"""
from __future__ import annotations

import base64
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
section[data-testid="stSidebar"] { border-right:1px solid var(--msb-border); }

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
    for name in _LOGO_NAMES:
        path = _ASSETS / name
        if path.is_file():
            return path
    return None


def logo_html() -> str:
    path = _logo_path()
    if path is None:
        return '<span class="mp-logo-badge">MSB</span>'
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f'<img class="mp-logo-img" alt="MSB" src="data:{_MIME[path.suffix.lower()]};base64,{data}">'


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
