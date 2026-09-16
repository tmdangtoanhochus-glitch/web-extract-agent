import copy
import importlib.util
import io
from pathlib import Path

from openpyxl import load_workbook
import pytest
from pydantic import ValidationError

from src.runner.workbook_schema import STEP_COLUMNS, WorkbookPlan
from runner_agent.authoring import planned_workbook


def full_plan():
    return {
        "settings": {"screen_flow": "login,search,result", "login_screen": "login", "result_screen": "result"},
        "steps": [
            {"screen": "login", "step": "username", "action": "fill", "value_source": "account"},
            {"screen": "login", "step": "password", "action": "fill", "value_source": "account"},
            {"screen": "login", "step": "submit", "action": "click", "value_source": "empty"},
            {"screen": "search", "step": "cif", "action": "fill_enter", "value_source": "testcase"},
            {"screen": "result", "step": "read_amount", "action": "read_result_single",
             "value_source": "empty", "read_method": "css_input", "match_type": "exact"}],
        "testcases": [
            {"tc_id": "FOUND_001", "mo_ta": "Tìm thấy khách hàng", "role_code": "RM",
             "data": {"cif": "${CASE1_CIF}"}, "expected": {"expected_amount": "${CASE1_AMOUNT}"}},
            {"tc_id": "FOUND_002", "mo_ta": "Khách hàng thứ hai", "role_code": "RM",
             "data": {"cif": "${CASE2_CIF}"}, "expected": {"expected_amount": "${CASE2_AMOUNT}"}},
        ],
    }


@pytest.fixture
def runner():
    path = Path(__file__).resolve().parents[2] / "docs" / "runner.py"
    spec = importlib.util.spec_from_file_location("workbook_runner_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_full_sheets_round_trip_through_actual_runner(tmp_path, runner):
    content = planned_workbook(WorkbookPlan.model_validate(full_plan()))
    wb = load_workbook(io.BytesIO(content))
    assert wb.sheetnames == ["settings", "steps", "testcases", "review"]
    assert list(next(wb["steps"].values)) == STEP_COLUMNS
    headers = list(next(wb["testcases"].values))
    assert headers == ["tc_id", "mo_ta", "active", "role_code", "specialized_bank", "cif", "expected_amount"]
    settings = dict(list(wb["settings"].values)[1:])
    assert settings["screen_flow"] == "login,search,result"
    assert {"browser", "popup_timeout", "read_method"} - set(settings) == {"read_method"}
    assert wb["testcases"].max_row == 3
    # Only activate synthetic rows to exercise the real loader/validator. No execution.
    for sheet in (wb["steps"], wb["testcases"]):
        columns = list(next(sheet.values))
        active = columns.index("active") + 1
        for row in range(2, sheet.max_row + 1):
            assert sheet.cell(row, active).value == "N"
            sheet.cell(row, active, "Y")
    path = tmp_path / "generated.xlsx"
    wb.save(path)
    wb.close()
    loaded_settings = runner.load_settings(path)
    loaded_steps = runner.load_steps(path)
    cases = runner.load_testcases(path)
    assert runner.validate_config(loaded_steps, cases, loaded_settings)
    assert cases[1]["expected_amount"] == "${CASE2_AMOUNT}"


@pytest.mark.parametrize("mutate", [
    lambda p: p["testcases"][0]["data"].clear(),
    lambda p: p["testcases"][0]["expected"].update(expected_typo="${EXPECTED}"),
    lambda p: p["testcases"][0]["data"].update(cif="literal-sensitive-value"),
    lambda p: p["steps"][0].update(active="Y"),
    lambda p: p["steps"][0].update(locator="#guessed"),
    lambda p: p["steps"][1].update(step="username"),
    lambda p: p["testcases"][1].update(tc_id="FOUND_001"),
    lambda p: p["settings"].update(screen_flow="login,result"),
    lambda p: p["settings"].update(login_screen="search"),
    lambda p: p["steps"][-1].update(screen="search"),
    lambda p: p["testcases"][0].update(mo_ta="=HYPERLINK(1)"),
])
def test_cross_sheet_validation_rejects_incomplete_or_unsafe_workbook(mutate):
    data = copy.deepcopy(full_plan())
    mutate(data)
    with pytest.raises(ValidationError):
        WorkbookPlan.model_validate(data)


def test_expected_placeholder_is_resolved_locally_and_redacted(runner, monkeypatch, capsys):
    import pandas as pd
    monkeypatch.setenv("CASE1_AMOUNT", "123.45")
    runner.RESULT_SCREEN = "result"
    monkeypatch.setattr(runner, "read_result_field", lambda *a, **kw: "123.45")
    steps = pd.DataFrame([{"screen": "result", "step": "read_amount", "action": "read_result_single",
                           "active": "Y", "match_type": "exact"}])
    passed, rows = runner.read_and_verify(object(), {"expected_amount": "${CASE1_AMOUNT}"}, "FAKE", steps, mode="single")
    assert passed and rows[0]["pass_amount"] == "PASS"
    assert "123.45" not in capsys.readouterr().out
    monkeypatch.delenv("CASE1_AMOUNT")
    with pytest.raises(ValueError, match="Thieu bien local"):
        runner.read_and_verify(object(), {"expected_amount": "${CASE1_AMOUNT}"}, "FAKE", steps, mode="single")


def test_generated_columns_cover_current_executor_settings_and_step_access(runner):
    import ast
    from src.runner.workbook_schema import WorkbookSettings
    tree = ast.parse(Path(runner.__file__).read_text(encoding="utf-8-sig"))
    used = {"settings": set(), "step": set()}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id in used
                and node.func.attr == "get" and node.args and isinstance(node.args[0], ast.Constant)):
            used[node.func.value.id].add(node.args[0].value)
        elif (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
              and node.value.id in used and isinstance(node.slice, ast.Constant)):
            used[node.value.id].add(node.slice.value)
    assert used["settings"] <= set(WorkbookSettings.model_fields)
    assert used["step"] <= set(STEP_COLUMNS)
