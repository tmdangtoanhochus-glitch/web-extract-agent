"""One reviewed local action, never a testcase verdict and never an automatic retry."""
import argparse
from datetime import datetime, timezone
from getpass import getpass, GetPassWarning
import hashlib
import json
import os
from pathlib import Path
import uuid
import warnings

from runner_agent.authoring import STRUCTURAL_SELECTOR
from runner_agent.inspector import load_inspection_workbook, runner_locator_builder
from runner_agent.preparation import read_workbook

SUPPORTED = {"fill", "click", "check", "select", "wait"}


def hidden_value(message):
    with warnings.catch_warnings():
        warnings.simplefilter("error", GetPassWarning)
        return getpass(message)


def select_step(workbook, row):
    step = next((s for s in workbook["steps"] if s["row"] == row), None)
    if step is None:
        raise ValueError("No step at this worksheet row")
    step = dict(step)
    step["action"] = step["action"].lower()
    if (step["action"] not in SUPPORTED or step.get("group") or
            step.get("prefill_check", "N").upper() == "Y" or step.get("dropdown_selector")):
        raise ValueError("Use full Runner for complex step semantics")
    if step["action"] == "wait":
        selector = step.get("wait_selector", "")
        if not STRUCTURAL_SELECTOR.fullmatch(selector) or len(selector) > 2000:
            raise ValueError("Only structural CSS visible waits can be tried here")
        step.update(locator=selector, locator_type="css")
    elif step.get("wait_selector"):
        raise ValueError("Use full Runner for actions with post-action wait commands")
    if (not step["locator"] or step["locator"] in {":not(*)", "RUNNER_REVIEW_REQUIRED", "self::*[false()]"}
            or "{i}" in step["locator"] or len(step["locator"]) > 2000
            or step["locator_type"] not in {"css", "xpath", "role", "text", "label", ""}):
        raise ValueError("Resolve the direct locator before trying this step")
    return step


def write_report(path, report, initial=False):
    """Persist intent before acting. A crash leaves EXECUTION_STARTED, never success."""
    report = {**report, "updated_at": datetime.now(timezone.utc).isoformat()}
    content = json.dumps(report, ensure_ascii=True, indent=2)
    if initial:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        return
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def try_step(config, row, output, prompt=input, value_prompt=hidden_value, builder=None):
    from playwright.sync_api import sync_playwright

    target = Path(output)
    if target.suffix.lower() != ".json" or target.exists():
        raise ValueError("Choose a new .json report path; previous attempts are never replayed")
    workbook = load_inspection_workbook(config)
    step = select_step(workbook, row)
    builder = builder or runner_locator_builder()
    report = {"schema_version": 1, "scope": "single_reviewed_action_not_testcase",
              "workbook_sha256": workbook["sha256"], "row": row, "action": step["action"],
              "status": "PREPARING", "attempts": 0}
    write_report(target, report, initial=True)
    browser, value = None, ""
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=False)
            try:
                context = browser.new_context()
                context.new_page()
                print(f"Row {row}, action {step['action']}. Navigate/login manually in the new browser.")
                print("This may change website data. Execution uses only the temporary value you enter, not testcase data or credential files.")
                command = prompt("Tab index to review (1..), or q to cancel: ").strip()
                if command.lower() == "q":
                    report["status"] = "CANCELLED"
                    return report
                tab = int(command)
                if not 1 <= tab <= len(context.pages):
                    raise ValueError("Invalid tab")
                page = context.pages[tab - 1]
                locator = builder(page, step["locator_type"], step["locator"])
                if locator.count() != 1 or not locator.is_visible():
                    report["status"] = "TARGET_UNAVAILABLE"
                    return report
                # Execute against this exact element, not a freshly resolved locator after review.
                element = locator.element_handle()
                if element is None:
                    report["status"] = "TARGET_UNAVAILABLE"
                    return report
                locator.highlight()
                if step["action"] in {"fill", "select"}:
                    value = value_prompt("Temporary local test value (hidden; not stored in workbook/report): ")
                    if not value:
                        report["status"] = "CANCELLED"
                        return report
                command = prompt(f"Verify the highlighted target. Type EXECUTE {row} to run ONCE, or anything else to cancel: ").strip()
                if command != f"EXECUTE {row}":
                    report["status"] = "CANCELLED"
                    return report
                if hashlib.sha256(read_workbook(config)).hexdigest() != workbook["sha256"]:
                    report["status"] = "WORKBOOK_CHANGED"
                    return report
                if (locator.count() != 1 or not element.is_visible() or
                        not locator.evaluate("(current, reviewed) => current === reviewed", element)):
                    report["status"] = "TARGET_CHANGED"
                    return report
                report.update(status="EXECUTION_STARTED", attempts=1)
                write_report(target, report)
                # Same direct Playwright operations used by the corresponding Runner handlers.
                # Intentionally no force, prefill, post-action wait, group, retry or business assertions.
                match step["action"]:
                    case "fill": element.fill(value, timeout=10000)
                    case "click": element.click(timeout=10000)
                    case "check": element.check(timeout=10000)
                    case "select": element.select_option(label=value, timeout=10000)
                    case "wait": element.wait_for_element_state("visible", timeout=10000)
                report["status"] = "ACTION_COMPLETED"
                return report
            finally:
                value = ""
                try:
                    if browser is not None and browser.is_connected():
                        browser.close()
                except Exception:
                    # Browser cleanup failure does not turn a completed action into a retry.
                    pass
    except BaseException as exc:
        report["status"] = ("OUTCOME_UNKNOWN" if report["attempts"] else
                            "CANCELLED" if isinstance(exc, KeyboardInterrupt) else "PREPARATION_ERROR")
        return report
    finally:
        value = ""
        write_report(target, report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--row", required=True, type=int)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        result = try_step(args.config, args.row, args.output)
        print(result["status"] + "; no automatic retry. ACTION_COMPLETED is not a passed testcase.")
    except Exception as error:
        raise SystemExit(f"Step trial stopped ({type(error).__name__}); inspect the report before any new attempt.") from None
