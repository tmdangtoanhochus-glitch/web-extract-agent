"""Select a replacement element locally and review before exporting a draft copy."""
import argparse
from pathlib import Path

from runner_agent.inspector import load_inspection_workbook
from runner_agent.repair import check_candidate, export_repair, require_supported_step, validate_candidate


def repair(config, row, output, prompt=input):
    from playwright.sync_api import sync_playwright

    target = Path(output)
    if target.suffix.lower() != ".xlsx" or target.exists():
        raise ValueError("Choose a new .xlsx output path")
    workbook = load_inspection_workbook(config)
    step = next((step for step in workbook["steps"] if step["row"] == row), None)
    if step is None:
        raise ValueError("No step at this worksheet row")
    require_supported_step(step)
    script = (Path(__file__).parent / "runner_agent" / "repair_picker.js").read_text(encoding="utf-8")
    picked = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        try:
            context = browser.new_context()
            def receive(source, payload):
                if source["frame"] != source["page"].main_frame or not isinstance(payload, dict) or set(payload) != {"locator"}:
                    return
                try:
                    selector = validate_candidate(payload["locator"])
                except ValueError:
                    return
                picked.update(page=source["page"], selector=selector)
            context.expose_binding("runnerRepairPick", receive)
            context.add_init_script(script=script)
            context.new_page()
            print(f"Repair worksheet row {row}. Navigate/login manually; hover the target and press Ctrl+Alt+L.")
            while browser.is_connected() and context.pages:
                if not picked:
                    context.pages[0].wait_for_timeout(250)
                    continue
                page, selector = picked["page"], picked["selector"]
                picked.clear()
                state = check_candidate(page, step, selector)
                if state != "READY_FOR_REVIEW":
                    print(state + "; pick the target again.")
                    continue
                print(f"Row {row}: locator_type -> css; locator -> {selector}")
                print("All steps and testcases in the NEW copy will be inactive. Source workbook stays unchanged.")
                command = prompt("Type EXPORT to confirm this target, q to cancel, or Enter to pick again: ").strip()
                if command.lower() == "q":
                    return None
                if command != "EXPORT":
                    continue
                if check_candidate(page, step, selector) != "READY_FOR_REVIEW":
                    print("Selection changed; pick and review again.")
                    continue
                return export_repair(config, target, row, selector, workbook["sha256"])
        finally:
            if browser.is_connected():
                browser.close()
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--row", required=True, type=int)
    parser.add_argument("--output", required=True)
    parser.add_argument("--snapshot", help="Reviewed structural snapshot JSON")
    parser.add_argument("--proposal", help="AI proposal JSON bound to that snapshot")
    args = parser.parse_args()
    try:
        if bool(args.snapshot) != bool(args.proposal):
            raise ValueError("Pass both --snapshot and --proposal, or neither")
        if args.proposal:
            from runner_agent.discovery import apply_proposal
            result = apply_proposal(args.config, args.row, args.output, args.snapshot, args.proposal)
        else:
            result = repair(args.config, args.row, args.output)
        print("Inactive repaired draft exported." if result else "Cancelled; no workbook written.")
    except Exception as error:
        raise SystemExit(f"Repair stopped ({type(error).__name__}); no automatic retry.") from None
