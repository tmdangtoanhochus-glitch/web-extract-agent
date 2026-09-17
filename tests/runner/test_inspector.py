import json
from types import SimpleNamespace

import pytest

from runner_agent.authoring import Recording, draft_workbook
from runner_agent.inspector import inspect_screen, load_inspection_workbook, runner_locator_builder


def workbook(action="click", locator="button", **overrides):
    step = {"row": 2, "screen_index": 1, "screen": "login", "step": "submit", "active": "N",
            "action": action, "locator_type": "css", "locator": locator, "wait_selector": ""}
    step.update(overrides)
    return {"screens": ["login"], "steps": [step]}


class Locator:
    def __init__(self, count=1, visible=True):
        self.matches, self.visible = count, visible
    def count(self): return self.matches
    def is_visible(self): return self.visible
    # No click/fill/input_value/inner_text or DOM API provided: checks must not use them.


@pytest.mark.parametrize("count,visible,status", [(0, False, "NOT_FOUND"), (2, True, "AMBIGUOUS"),
                                                  (1, False, "HIDDEN"), (1, True, "UNIQUE_VISIBLE")])
def test_checks_inactive_steps_without_reading_values_or_executing(count, visible, status):
    result = inspect_screen(object(), workbook(), 1, builder=lambda *a: Locator(count, visible))
    assert result["rows"] == [{"row": 2, "checks": [{"kind": "target", "status": status, "match_count": count}]}]
    assert result["counts"] == {status: 1}
    assert "submit" not in json.dumps(result)


def test_reuses_runner_locator_builder_for_role_semantics():
    calls = []
    page = SimpleNamespace(get_by_role=lambda role, **kwargs: (calls.append((role, kwargs)) or Locator()))
    result = inspect_screen(page, workbook(locator_type="role", locator="button|Login"), 1,
                            builder=runner_locator_builder())
    assert calls == [("button", {"name": "Login"})]
    assert result["counts"] == {"UNIQUE_VISIBLE": 1}


@pytest.mark.parametrize("action,selector,extra,status", [
    ("click", ":not(*)", {}, "UNRESOLVED"),
    ("click", "", {}, "UNRESOLVED"),
    ("fill_sequence", "input", {}, "MANUAL_REVIEW"),
    ("fill", "input:nth-child({i})", {}, "MANUAL_REVIEW"),
    ("wait", "", {"wait_selector": "timeout_reload:1000"}, "MANUAL_REVIEW"),
    ("read_result_single", "field", {"read_method": "label_input"}, "MANUAL_REVIEW"),
])
def test_unresolved_and_complex_commands_never_execute(action, selector, extra, status):
    def forbidden(*args):
        pytest.fail("Inspector must not evaluate this command")
    result = inspect_screen(object(), workbook(action, selector, **extra), 1, builder=forbidden)
    assert result["counts"] == {status: 1}


def test_selector_error_does_not_echo_selector_or_page_details():
    def error(*args): raise ValueError("synthetic-private-selector")
    result = inspect_screen(object(), workbook(locator="synthetic-private-selector"), 1, builder=error)
    assert result["counts"] == {"CHECK_ERROR": 1}
    assert "synthetic-private" not in json.dumps(result)


def test_read_method_uses_css_without_reading_result_and_flags_wait():
    calls = []
    def build(page, kind, selector):
        calls.append((kind, selector))
        return Locator()
    result = inspect_screen(object(), workbook("read_result_single", "input", locator_type="label",
                                               read_method="css_input", wait_selector="spin"), 1, builder=build)
    assert calls == [("css", "input")]
    assert result["counts"] == {"UNIQUE_VISIBLE": 1, "MANUAL_REVIEW": 1}


def test_visible_target_does_not_certify_group_and_other_screens_are_skipped():
    data = workbook(action="select_antd", group="repeated")
    data["screens"].append("other")
    data["steps"].append({**data["steps"][0], "screen_index": 2, "row": 3})
    result = inspect_screen(object(), data, 1, builder=lambda *a: Locator())
    assert len(result["rows"]) == 1
    assert result["rows"][0]["row"] == 2
    assert result["counts"] == {"UNIQUE_VISIBLE": 1, "MANUAL_REVIEW": 2}
    assert result["observed_at"].endswith("+00:00")


def test_load_inactive_workbook_retains_row_numbers_without_testcase_data(tmp_path):
    recording = Recording()
    recording.accept({"action": "fill", "locator": "input:nth-of-type(1)"})
    path = tmp_path / "draft.xlsx"
    content = draft_workbook(recording)
    path.write_bytes(content)
    loaded = load_inspection_workbook(path)
    assert loaded["screens"] == ["recorded"]
    assert loaded["steps"][0]["row"] == 2
    assert loaded["steps"][0]["active"] == "N"
    assert "testcases" not in loaded
    assert len(loaded["sha256"]) == 64
    assert path.read_bytes() == content


def test_cli_manual_screen_selection_export_and_no_overwrite(tmp_path, monkeypatch):
    import playwright.sync_api
    import inspect_runner

    source = tmp_path / "draft.xlsx"
    recording = Recording()
    recording.accept({"action": "click", "locator": "button:nth-of-type(1)"})
    source.write_bytes(draft_workbook(recording))
    original = source.read_bytes()
    page = SimpleNamespace(locator=lambda selector: Locator())
    context = SimpleNamespace(pages=[page], new_page=lambda: page)
    closed = []
    browser = SimpleNamespace(new_context=lambda: context, is_connected=lambda: True,
                              close=lambda: closed.append(True))
    class Playwright:
        def __enter__(self): return SimpleNamespace(chromium=SimpleNamespace(launch=lambda **kw: browser))
        def __exit__(self, *args): pass
    monkeypatch.setattr(playwright.sync_api, "sync_playwright", Playwright)
    commands = iter(["wrong", "2 1", "1 2", "1 1", "q"])
    output = tmp_path / "inspection.json"
    report = inspect_runner.inspect(source, output, prompt=lambda _: next(commands))
    assert len(report["snapshots"]) == 1
    assert report["snapshots"][0]["counts"] == {"UNIQUE_VISIBLE": 1}
    assert json.loads(output.read_text()) == report
    assert source.read_bytes() == original
    assert "button:nth-of-type(1)" not in output.read_text()
    assert closed == [True]
    with pytest.raises(ValueError):
        inspect_runner.inspect(source, output)
    assert closed == [True]
