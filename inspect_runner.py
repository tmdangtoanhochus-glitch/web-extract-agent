"""User-operated local inspection of workbook locators on the current browser page."""
import argparse
import json
from pathlib import Path

from runner_agent.inspector import inspect_screen, load_inspection_workbook


def inspect(config, output, prompt=input):
    from playwright.sync_api import sync_playwright

    output = Path(output)
    if output.suffix.lower() != ".json" or output.exists():
        raise ValueError("Choose a new .json output path")
    workbook = load_inspection_workbook(config)
    snapshots = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        try:
            context = browser.new_context()
            context.new_page()
            print("Navigate/login manually. No steps are executed by this tool.")
            print("Select the workbook screen index and browser tab index (both start at 1).")
            for index, screen in enumerate(workbook["screens"], 1):
                print(f"Screen {index}: {screen}")
            while browser.is_connected() and context.pages:
                command = prompt("Check: <screen> <tab> (example: 1 1); q to export and close: ").strip()
                if command.lower() == "q":
                    break
                try:
                    screen, tab = [int(part) for part in command.split()]
                    if not 1 <= tab <= len(context.pages) or not 1 <= screen <= len(workbook["screens"]):
                        raise ValueError()
                except ValueError:
                    print("Invalid indices. Use the screen list and tab order; no URL or input values.")
                    continue
                snapshot = inspect_screen(context.pages[tab - 1], workbook, screen)
                snapshot["tab_index"] = tab
                snapshots.append(snapshot)
                print(json.dumps(snapshot, ensure_ascii=True))
                if len(snapshots) >= 100:
                    print("Snapshot limit reached; exporting report.")
                    break
        finally:
            if browser.is_connected():
                browser.close()
    if not snapshots:
        raise ValueError("No inspection captured")
    report = {"schema_version": 1, "workbook_sha256": workbook["sha256"],
              "scope": "current_page_locator_counts_only", "snapshots": snapshots}
    with output.open("x", encoding="utf-8") as target:
        json.dump(report, target, ensure_ascii=True, indent=2)
    print("Report exported. Locator presence is not a passed testcase or proof of correct target.")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        inspect(args.config, args.output)
    except Exception as error:
        raise SystemExit(f"Inspector stopped ({type(error).__name__}); no automatic retry.") from None
