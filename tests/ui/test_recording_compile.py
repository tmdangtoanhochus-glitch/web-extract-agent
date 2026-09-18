import json
from types import SimpleNamespace

import streamlit as st
from streamlit.testing.v1 import AppTest


def test_recording_ui_requires_review_and_invalidates_draft_when_input_changes(monkeypatch):
    import ui.runner_recording as module
    trace = {"schema_version": 1, "events": [
        {"id": 1, "screen": "recorded", "action": "fill", "locator": "input:nth-of-type(1)"}], "dropped": 0}
    content = json.dumps(trace).encode()
    monkeypatch.setattr(st, "file_uploader", lambda *a, **kw: SimpleNamespace(size=len(content), getvalue=lambda: content))
    calls = []
    def api(method, path, body, binary=False):
        calls.append((method, path, body, binary))
        return b"synthetic-workbook"
    monkeypatch.setattr(module, "_test_api", api, raising=False)
    app = AppTest.from_string("import ui.runner_recording as m\nm.render(m._test_api, {'recording': True})").run()
    app.text_area(key="runner_recording_description").set_value("Nhập mã hồ sơ tại sự kiện 1.").run()
    app.button(key="runner_recording_compile").click().run()
    assert not calls and not app.exception
    app.checkbox(key="runner_recording_reviewed").check().run()
    app.button(key="runner_recording_compile").click().run()
    assert len(calls) == 1 and calls[0][1] == "/authoring/recording" and calls[0][3]
    assert calls[0][2]["recording"]["events"][0]["locator"] == "input:nth-of-type(1)"
    assert app.session_state["runner_recording_draft"] == b"synthetic-workbook"
    app.text_area(key="runner_recording_description").set_value("Nhập mã khác cho sự kiện 1.").run()
    assert not app.exception
    assert "runner_recording_draft" not in app.session_state
    assert not app.session_state["runner_recording_reviewed"]


def test_recording_ui_rejects_raw_data_before_ai(monkeypatch):
    import ui.runner_recording as module
    content = b'{"schema_version":1,"events":[{"value":"synthetic-private"}]}'
    monkeypatch.setattr(st, "file_uploader", lambda *a, **kw: SimpleNamespace(size=len(content), getvalue=lambda: content))
    def forbidden(*a, **kw): raise AssertionError("AI must not be called")
    monkeypatch.setattr(module, "_test_api", forbidden, raising=False)
    app = AppTest.from_string("import ui.runner_recording as m\nm.render(m._test_api, {'recording': True})").run()
    assert not app.exception and app.error
    assert all("synthetic-private" not in item.value for item in app.error)
