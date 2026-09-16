"""User-operated recorder: fresh browser, no credentials/config loaded."""
import argparse
from pathlib import Path

from runner_agent.authoring import Recording, draft_workbook


def record(output):
    from playwright.sync_api import sync_playwright

    output = Path(output)
    if output.suffix.lower() != ".xlsx":
        raise ValueError("Output must be an .xlsx file")
    if output.exists():
        raise ValueError("Output already exists; choose a new filename")
    recording = Recording()
    script = (Path(__file__).parent / "runner_agent" / "recorder.js").read_text(encoding="utf-8")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        try:
            context = browser.new_context()
            def receive(source, payload):
                if source["frame"] == source["page"].main_frame:
                    recording.accept(payload)
            context.expose_binding("runnerRecordEvent", receive)
            context.add_init_script(script=script)
            page = context.new_page()
            print("Navigate manually in the new browser. Close all pages to export the inactive draft.")
            while context.pages and browser.is_connected():
                try:
                    context.pages[0].wait_for_timeout(250)
                except Exception:
                    if not browser.is_connected() or not context.pages:
                        break
                    raise
        finally:
            if browser.is_connected():
                browser.close()
    # Exclusive creation prevents overwriting a file created during recording.
    with output.open("xb") as target:
        target.write(draft_workbook(recording))
    print(f"Exported {len(recording.events)} draft steps; rejected events: {recording.dropped}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        record(args.output)
    except Exception as error:
        # Playwright exceptions may include page details: print only the type.
        raise SystemExit(f"Recorder stopped ({type(error).__name__}); no automatic retry.") from None
