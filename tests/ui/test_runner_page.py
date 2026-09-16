from pathlib import Path

import httpx
from streamlit.testing.v1 import AppTest

PAGE = Path(__file__).resolve().parents[2] / "ui" / "pages" / "8_Runner.py"


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
