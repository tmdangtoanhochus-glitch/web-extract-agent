"""Read-only bounded local journal diagnostics. No agent, token, config, or network."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path

from .client import JournalError, child_path, load_journal


def protected_name(name):
    name = name.lower()
    return name.startswith(".env") or any(word in name for word in ("credential", "secret", "password", "token"))


def linked(path):
    return path.is_symlink() or getattr(path, "is_junction", lambda: False)()


def diagnose(state, run_id=None, limit=1000):
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("Limit must be 1..1000")
    report = {"schema_version": 1, "scope": "read_only_non_atomic_snapshot",
        "observed_at": datetime.now(timezone.utc).isoformat(), "status": "OK",
        "files": [], "counts": {}, "truncated": False}
    state = Path(state).absolute()
    root = state / "journal"
    if any(protected_name(p.name) or linked(p) for p in (root, *root.parents)):
        report["status"] = "UNSAFE_STATE"
        return report
    if not root.is_dir():
        report["status"] = "STATE_UNAVAILABLE"
        return report

    def inspect(path):
        # File reference identifies a file locally without exposing config/run names.
        item = {"file_ref": hashlib.sha256(path.name.encode()).hexdigest()[:16],
                "kind": "pending" if path.suffix == ".pending" else "journal"}
        if protected_name(path.name):
            item["code"] = "SKIPPED_PROTECTED_NAME"
        elif linked(path):
            item["code"] = "SYMLINK"
        elif path.suffix == ".pending":
            item["code"] = "INTERRUPTED_WRITE"
        else:
            try:
                entry = load_journal(path, root)
                item.update(code="VALID", state=entry["state"],
                    has_result="result" in entry, artifacts_deleted=entry.get("deleted_at") is not None)
            except JournalError as error:
                item["code"] = error.code
            except OSError:
                item["code"] = "UNREADABLE"
        return item

    if run_id is not None:
        try:
            paths = [child_path(root, run_id + suffix) for suffix in (".json", ".pending")]
        except ValueError:
            report["status"] = "UNSAFE_RUN_REFERENCE"
            return report
        for path in paths:
            if path.exists():
                report["files"].append(inspect(path))
        if not report["files"]:
            report["status"] = "RUN_NOT_FOUND"
    else:
        try:
            with os.scandir(root) as entries:
                for entry in entries:
                    if Path(entry.name).suffix not in {".json", ".pending"}:
                        continue
                    if len(report["files"]) == limit:
                        report["truncated"] = True
                        break
                    report["files"].append(inspect(root / entry.name))
        except OSError:
            report["status"] = "STATE_UNAVAILABLE"
    report["counts"] = dict(Counter(item["code"] for item in report["files"]))
    if report["status"] == "OK" and (report["truncated"] or any(item["code"] != "VALID" for item in report["files"])):
        report["status"] = "REVIEW_REQUIRED"
    return report
