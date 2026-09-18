"""Apply an AI candidate proposal locally, only after live human confirmation."""
from pathlib import Path

from src.runner.discovery import RepairProposal, Snapshot
from .inspector import load_inspection_workbook
from .repair import check_candidate, export_repair, require_supported_step


def read_contract(path, schema):
    path = Path(path)
    if (path.suffix.lower() != ".json" or path.is_symlink() or
            any(part.lower() == "secrets" for part in path.parts) or
            any(word in path.name.lower() for word in ("credential", "secret", "token", "password")) or
            path.stat().st_size > 250000):
        raise ValueError("Expected a structural snapshot/proposal JSON up to 250 KB")
    return schema.model_validate_json(path.read_bytes())


def selected_candidate(snapshot, proposal, step):
    if proposal.snapshot_sha256 != snapshot.fingerprint():
        raise ValueError("Proposal does not belong to this snapshot")
    if proposal.action != step["action"].lower() or proposal.read_method != step.get("read_method", ""):
        raise ValueError("Proposal does not match this step action/read method")
    require_supported_step(step)
    candidate = next((c for c in snapshot.candidates if c.id == proposal.candidate_id), None)
    from src.runner.discovery import compatible
    if candidate is None or not compatible(proposal.action, candidate.kind, proposal.read_method):
        raise ValueError("Invalid candidate")
    return candidate


def apply_proposal(config, row, output, snapshot_path, proposal_path, prompt=input):
    from playwright.sync_api import sync_playwright

    target = Path(output)
    if target.suffix.lower() != ".xlsx" or target.exists():
        raise ValueError("Choose a new .xlsx output path")
    snapshot = read_contract(snapshot_path, Snapshot)
    proposal = read_contract(proposal_path, RepairProposal)
    workbook = load_inspection_workbook(config)
    step = next((s for s in workbook["steps"] if s["row"] == row), None)
    if step is None:
        raise ValueError("No step at this worksheet row")
    candidate = selected_candidate(snapshot, proposal, step)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        try:
            context = browser.new_context()
            context.new_page()
            print("Navigate/login manually to the correct screen. AI has not verified the target.")
            while browser.is_connected() and context.pages:
                command = prompt("Tab index to highlight proposed target (1..), or q to cancel: ").strip()
                if command.lower() == "q":
                    return None
                try:
                    tab = int(command)
                    if not 1 <= tab <= len(context.pages):
                        raise ValueError()
                    page = context.pages[tab - 1]
                    locator = page.locator(candidate.selector)
                    if locator.count() != 1 or not locator.is_visible():
                        raise ValueError()
                    locator.evaluate("element => { window.__runnerRepairTarget = element; }")
                    locator.highlight()
                except Exception:
                    print("Target not uniquely visible; inspect again or select a different tab.")
                    continue
                print(f"Row {row}; candidate {candidate.id}; CSS {candidate.selector}")
                print("Verify the highlighted element yourself. All steps/testcases in the new copy will be inactive.")
                command = prompt("Type EXPORT to confirm, q to cancel, Enter to inspect again: ").strip()
                if command.lower() == "q":
                    return None
                if command != "EXPORT":
                    continue
                if check_candidate(page, step, candidate.selector) != "READY_FOR_REVIEW":
                    print("Target changed; inspect again.")
                    continue
                return export_repair(config, output, row, candidate.selector, workbook["sha256"])
        finally:
            if browser.is_connected():
                browser.close()
    return None
