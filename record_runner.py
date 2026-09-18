"""User-operated recorder: fresh browser, no credentials/config loaded."""
import argparse
import json
from pathlib import Path

from runner_agent.authoring import Recording, draft_workbook
from src.runner.scoped_locator import decode, encode, validate_path


def receive_event(recording, source, payload, structural_script):
    """Frame ancestors are resolved locally without URL/name/DOM text."""
    try:
        if isinstance(payload, dict) and "control" in payload:
            accepted = recording.control(payload)
        else:
            if (not isinstance(payload, dict) or not {"action", "locator"} <= set(payload)
                    or set(payload) - {"action", "locator", "widget", "related_locator"}):
                raise ValueError("Invalid event")
            parts = decode(payload["locator"])
            related = decode(payload["related_locator"]) if payload.get("related_locator") else None
            frame = source["frame"]
            depth = 0
            while frame != source["page"].main_frame:
                depth += 1
                if depth > 8 or frame.parent_frame is None:
                    raise ValueError("Invalid frame ancestry")
                element = frame.frame_element()
                try:
                    ancestors = validate_path(element.evaluate(structural_script))
                finally:
                    element.dispose()
                ancestors[-1]["kind"] = "frame"
                parts = ancestors + parts
                if related:
                    related = ancestors + related
                frame = frame.parent_frame
            normalized = {**payload, "locator": encode(parts)}
            if related:
                normalized["related_locator"] = encode(related)
            accepted = recording.accept(normalized)
    except Exception:
        recording.dropped += 1
        accepted = False
    return {"accepted": accepted, "paused": recording.paused, "screen": recording.screen_index}


def record(output, events_output=None):
    from playwright.sync_api import sync_playwright

    output = Path(output)
    if output.suffix.lower() != ".xlsx":
        raise ValueError("Output must be an .xlsx file")
    if output.exists():
        raise ValueError("Output already exists; choose a new filename")
    event_path = Path(events_output) if events_output else None
    if event_path and (event_path.suffix.lower() != ".json" or event_path.exists() or event_path.is_symlink()):
        raise ValueError("Choose a new .json event output")
    recording = Recording(limit=500 if event_path else 1000)
    script = (Path(__file__).parent / "runner_agent" / "recorder.js").read_text(encoding="utf-8")
    structural = (Path(__file__).parent / "runner_agent" / "structural_path.js").read_text(encoding="utf-8")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        try:
            context = browser.new_context()
            def receive(source, payload):
                return receive_event(recording, source, payload, structural)
            context.expose_binding("runnerRecordEvent", receive)
            context.add_init_script(script="window.__runnerStructuralPath = (" + structural + ");\n" + script)
            page = context.new_page()
            print("Navigate manually in the new browser. Close all pages to export the inactive draft.")
            print("Ctrl+Alt+N: next screen; Ctrl+Alt+P: pause/resume recording.")
            print("Hover a target: Ctrl+Alt+W records a wait; Ctrl+Alt+A records an input/select result read (expected stays empty).")
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
    content = draft_workbook(recording)
    trace_content = None
    if event_path:
        from src.runner.recording_plan import RecordingTrace
        trace = RecordingTrace(events=[{"id": i, **event} for i, event in enumerate(recording.events, 1)],
                               dropped=recording.dropped)
        trace_content = json.dumps(trace.model_dump(), ensure_ascii=True, indent=2)
    with output.open("xb") as target:
        target.write(content)
    if event_path:
        with event_path.open("x", encoding="utf-8") as target:
            target.write(trace_content)
    print(f"Exported {len(recording.events)} draft steps; rejected events: {recording.dropped}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--events-output", help="Structural JSON for reviewed AI compilation on the Runner UI")
    args = parser.parse_args()
    try:
        record(args.output, args.events_output)
    except Exception as error:
        # Playwright exceptions may include page details: print only the type.
        raise SystemExit(f"Recorder stopped ({type(error).__name__}); no automatic retry.") from None
