"""User-operated browser discovery. Exports only reviewed structural candidates."""
import argparse
import json
from pathlib import Path

from src.runner.discovery import Snapshot


def capture(page):
    script = (Path(__file__).parent / "runner_agent" / "discovery.js").read_text(encoding="utf-8")
    return Snapshot.model_validate(page.evaluate(script))


def discover(output, prompt=input):
    from playwright.sync_api import sync_playwright

    target = Path(output)
    if target.suffix.lower() != ".json" or target.exists():
        raise ValueError("Choose a new .json output path")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        try:
            context = browser.new_context()
            context.new_page()
            print("Navigate/login manually. Capture one screen at a time; no actions are executed.")
            while browser.is_connected() and context.pages:
                command = prompt("Enter tab index to inspect (1..), or q to cancel: ").strip()
                if command.lower() == "q":
                    return None
                try:
                    index = int(command)
                    if not 1 <= index <= len(context.pages):
                        raise ValueError()
                    page = context.pages[index - 1]
                    snapshot = capture(page)
                except ValueError:
                    print("Invalid tab or no supported elements. Choose another screen.")
                    continue
                print(json.dumps(snapshot.model_dump(), indent=2))
                print("Use candidate IDs in your description. Snapshot has no labels, page text, input values or URLs.")
                while True:
                    command = prompt("Candidate ID to highlight; EXPORT to save, q to cancel: ").strip()
                    if command.lower() == "q":
                        return None
                    if command == "EXPORT":
                        if capture(page).fingerprint() != snapshot.fingerprint():
                            print("Page structure changed; capture again.")
                            break
                        with target.open("x", encoding="utf-8") as file:
                            json.dump(snapshot.model_dump(), file, indent=2)
                        return snapshot
                    candidate = next((c for c in snapshot.candidates if c.id == command), None)
                    if candidate:
                        page.locator(candidate.selector).highlight()
                    else:
                        print("Unknown candidate ID")
        finally:
            if browser.is_connected():
                browser.close()
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        result = discover(args.output)
        print("Snapshot exported for review." if result else "Cancelled; no snapshot written.")
    except Exception as error:
        raise SystemExit(f"Discovery stopped ({type(error).__name__}); no automatic retry.") from None
