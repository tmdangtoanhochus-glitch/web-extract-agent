from pathlib import Path
import json
from types import SimpleNamespace

import httpx
from streamlit.testing.v1 import AppTest

PAGE = Path(__file__).resolve().parents[2] / "ui" / "pages" / "2_Automation.py"


def test_late_result_is_distinct_from_lost_status(monkeypatch):
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def request(self, method, path, json=None):
            if path == "/runner/me":
                data = {"id": "u1", "username": "tester", "role": "user"}
            elif path == "/runner/runs":
                data = [{"run_id": "run_lost", "status": "LOST", "passed": 0, "failed": 0,
                    "errors": 0, "unverified": 0, "duration": 0, "expires_at": None, "deleted_at": None,
                    "late_result": {"status": "PASSED", "passed": 2, "failed": 0, "errors": 0,
                                    "unverified": 0, "duration": 5, "received_at": 1000000}}]
            else:
                data = []
            return httpx.Response(200, json=data)
    monkeypatch.setattr(httpx, "Client", Client)
    app = AppTest.from_file(str(PAGE))
    app.session_state["runner_session"] = "synthetic-session"
    app.run()
    assert not app.exception
    assert any("không phải một lần chạy lại" in item.value for item in app.info)
    assert any("mất theo dõi run" in item.value for item in app.warning)
    assert any("Giữ trạng thái LOST" in item.value for item in app.caption)


def test_discovery_review_repair_and_logout(monkeypatch):
    import streamlit as st
    snapshot = {"schema_version": 1, "candidates": [
        {"id": "c1", "kind": "input", "selector": "input:nth-of-type(1)"}], "truncated": False}
    content = json.dumps(snapshot).encode()
    monkeypatch.setattr(st, "file_uploader", lambda *a, **kw: SimpleNamespace(size=len(content), getvalue=lambda: content))
    requests = []
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def request(self, method, path, json=None):
            requests.append((path, json))
            if path == "/runner/me":
                return httpx.Response(200, json={"id": "u1", "username": "tester", "role": "user"})
            if path == "/runner/authoring/capabilities":
                return httpx.Response(200, json={"describe": True, "discovery": True, "repair": True})
            if path == "/runner/authoring/repair":
                return httpx.Response(200, content=b"synthetic-proposal")
            return httpx.Response(200, json=[])
    monkeypatch.setattr(httpx, "Client", Client)
    app = AppTest.from_file(str(PAGE))
    app.session_state["runner_session"] = "synthetic-session"
    app.run()
    assert not app.exception
    next(b for b in app.button if b.label == "Tạo đề xuất locator").click().run()
    assert not any(p == "/runner/authoring/repair" for p, _ in requests)
    next(w for w in app.radio if w.label == "Loại đề xuất").set_value("Sửa một locator")
    next(w for w in app.text_area if w.label == "Mô tả thao tác và ID phần tử").set_value("Điền account vào phần tử c1.")
    next(w for w in app.selectbox if w.label.startswith("Action của dòng")).set_value("fill")
    next(w for w in app.checkbox if w.label.startswith("Tôi đã rà soát snapshot")).check()
    next(b for b in app.button if b.label == "Tạo đề xuất locator").click().run()
    assert not app.exception
    payload = next(body for path, body in requests if path == "/runner/authoring/repair")
    assert payload["snapshot"] == snapshot and payload["action"] == "fill"
    assert app.session_state["runner_locator_draft"]["repair"] is True
    next(b for b in app.button if b.label == "Đăng xuất Runner").click().run()
    assert "runner_locator_draft" not in app.session_state


def test_preflight_block_visible_in_history_without_workbook_data(monkeypatch):
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def request(self, method, path, json=None):
            if path == "/runner/me":
                data = {"id": "u1", "username": "tester", "role": "user"}
            elif path == "/runner/runs":
                data = [{"run_id": "run1", "status": "ERROR", "passed": 0, "failed": 0,
                    "errors": 1, "unverified": 0, "duration": 0, "expires_at": None, "deleted_at": None,
                    "preflight": {"status": "blocked", "active_steps": 1, "active_testcases": 0,
                        "issues": [{"sheet": "testcases", "row": 2, "code": "ENTER_AND_ACTIVATE_USER_TESTCASES"}],
                        "warnings": [], "truncated": False}}]
            else:
                data = []
            return httpx.Response(200, json=data)
    monkeypatch.setattr(httpx, "Client", Client)
    app = AppTest.from_file(str(PAGE))
    app.session_state["runner_session"] = "synthetic-session"
    app.run()
    assert not app.exception
    assert any("Bị chặn trước khi mở browser" in error.value for error in app.error)
    assert any("ENTER_AND_ACTIVATE_USER_TESTCASES" in str(frame.value) for frame in app.dataframe)


def test_login_then_local_run_submission(monkeypatch):
    requests = []
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def request(self, method, path, json=None):
            requests.append((method, path, json))
            data = []
            if path == "/runner/login":
                data = {"session": "synthetic-session", "user": {"username": "tester", "role": "user"}}
            elif path == "/runner/me":
                data = {"id": "user1", "username": "tester", "role": "user"}
            elif path == "/runner/agents":
                data = [{"id": "agent1", "active": True}]
            elif path == "/runner/runs" and method == "POST":
                data = {"run_id": "UAT_20260101_000000"}
            return httpx.Response(200, json=data)
    monkeypatch.setattr(httpx, "Client", Client)
    app = AppTest.from_file(str(PAGE)).run()
    assert not app.exception
    app.text_input[0].set_value("tester")
    app.text_input[1].set_value("synthetic-password")
    app.button[0].click().run()
    assert not app.exception
    name = next(w for w in app.text_input if w.label == "Tên file")
    name.set_value("UAT.xlsx").run()
    next(b for b in app.button if b.label == "Tạo run").click().run()
    assert not app.exception
    payload = next(body for method, path, body in requests if method == "POST" and path == "/runner/runs")
    assert payload == {"agent_id": "agent1", "config_name": "UAT.xlsx", "local_ref": "UAT.xlsx"}


def test_describe_requires_review_and_clears_draft_on_logout(monkeypatch):
    requests = []
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def request(self, method, path, json=None):
            requests.append((method, path, json))
            if path == "/runner/me":
                return httpx.Response(200, json={"id": "user1", "username": "tester", "role": "user"})
            if path == "/runner/authoring/capabilities":
                return httpx.Response(200, json={"describe": True})
            if path == "/runner/authoring/describe":
                return httpx.Response(200, content=b"synthetic-workbook")
            return httpx.Response(200, json=[])
    monkeypatch.setattr(httpx, "Client", Client)
    app = AppTest.from_file(str(PAGE))
    app.session_state["runner_session"] = "synthetic-session"
    app.run()
    assert not app.exception
    app.text_area[0].set_value("Điền role RM rồi bấm đăng nhập.")
    next(b for b in app.button if b.label == "Tạo workbook nháp").click().run()
    assert not any(path == "/runner/authoring/describe" for _, path, _ in requests)
    app.text_area[0].set_value("Điền role RM rồi bấm đăng nhập.")
    app.checkbox[0].check()
    next(b for b in app.button if b.label == "Tạo workbook nháp").click().run()
    assert not app.exception
    payload = next(body for _, path, body in requests if path == "/runner/authoring/describe")
    assert payload["reviewed_no_secrets"] is True
    assert app.session_state["runner_describe_draft"] == b"synthetic-workbook"
    next(b for b in app.button if b.label == "Đăng xuất Runner").click().run()
    assert "runner_describe_draft" not in app.session_state


def test_setup_guide_is_hidden_on_login_screen_and_shown_after_login(monkeypatch):
    app = AppTest.from_file(str(PAGE), default_timeout=30)
    app.run()
    assert not app.exception
    assert not any("Cài môi trường Python" in e.label for e in app.expander)  # chưa đăng nhập: không hiện

    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def request(self, method, path, json=None, **kw):
            data = {"id": "u1", "username": "staff", "role": "user"} if path == "/runner/me" else []
            return httpx.Response(200, json=data, request=httpx.Request(method, "http://t"))
        def post(self, path, json=None, **kw):
            return httpx.Response(200, json={}, request=httpx.Request("POST", "http://t"))
    monkeypatch.setattr(httpx, "Client", Client)
    app = AppTest.from_file(str(PAGE), default_timeout=30)
    app.session_state["runner_session"] = "token"
    app.run()
    assert not app.exception
    guide = next(e for e in app.expander if "Cài môi trường Python" in e.label)
    assert guide.proto.expanded
    assert "python -m venv .venv" in " ".join(str(c.value) for c in app.code)
