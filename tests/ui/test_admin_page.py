"""Trang Admin chung: tab riêng cho Crawl và Automation, đăng nhập dùng phiên Runner admin."""
from pathlib import Path

import httpx
from streamlit.testing.v1 import AppTest

PAGE = Path(__file__).resolve().parents[2] / "ui" / "pages" / "3_Admin.py"


def _fake_client(monkeypatch, users):
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def _resp(self, data):
            return httpx.Response(200, json=data, request=httpx.Request("GET", "http://t"))
        def get(self, path, **kw):
            return self._resp({"scheduled_job_errors": [], "manual_crawl_errors": []} if path == "/admin/errors" else [])
        def request(self, method, path, json=None):
            if path == "/runner/me":
                return self._resp({"id": "u0", "username": "boss", "role": "admin"})
            if path == "/runner/users":
                return self._resp(users)
            return self._resp([])
    monkeypatch.setattr(httpx, "Client", Client)


def test_admin_page_shows_separate_crawl_and_automation_tabs(monkeypatch):
    _fake_client(monkeypatch, [{"id": "u1", "username": "staff", "role": "user", "is_active": True}])
    app = AppTest.from_file(str(PAGE), default_timeout=30)
    app.session_state["admin_auth"] = {"kind": "bearer", "token": "t"}
    app.run()
    assert not app.exception
    labels = [t.label for t in app.tabs]
    assert any(l.startswith("Crawl ·") for l in labels) and any(l.startswith("Automation ·") for l in labels)
    assert any("staff" in str(m.value) for m in app.markdown) or any("staff" in str(j.value) for j in app.get("json"))


def test_env_admin_sees_notice_instead_of_automation_management(monkeypatch):
    _fake_client(monkeypatch, [])
    app = AppTest.from_file(str(PAGE), default_timeout=30)
    app.session_state["admin_auth"] = {"kind": "basic", "user": "a", "pass": "b"}
    app.run()
    assert not app.exception
    assert any("chỉ dùng cho Crawl" in i.value for i in app.info)
