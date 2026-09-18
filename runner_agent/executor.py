"""Worker CLI: chỉ chạy ở máy người dùng, tuyệt đối không import từ API."""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

from .preflight import check
from src.runner.preflight_contract import metadata


def execute(config, run_id, output, env_path=None):
    source = Path(__file__).resolve().parents[1] / "docs" / "runner.py"
    try:
        report = metadata(check(Path(config).read_bytes()))
    except Exception:
        report = metadata({"active_steps": 0, "active_testcases": 0,
            "issues": [{"sheet": "workbook", "code": "INVALID_WORKBOOK"}], "warnings": []})
    folder = Path(output)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "preflight.json").write_text(json.dumps(report), encoding="utf-8")
    if report["status"] == "blocked":
        summary = {"run_id": run_id, "status": "ERROR", "passed": 0, "failed": 0,
                   "errors": 1, "unverified": 0, "duration": 0, "cases": [], "preflight": report}
        (folder / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
        return summary
    spec = importlib.util.spec_from_file_location("local_uat_runner", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.execute_config(config, run_id=run_id, output_dir=output, env_path=env_path)
    summary_path = folder / "summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["preflight"] = report
        summary_path.write_text(json.dumps(summary), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--env-path")
    args = parser.parse_args()
    try:
        summary = execute(args.config, args.run_id, args.output, args.env_path)
    except BaseException:
        # Không đưa exception/DOM/credential vào IPC hoặc stdout.
        output = Path(args.output)
        output.mkdir(parents=True, exist_ok=True)
        (output / "summary.json").write_text(json.dumps({"run_id": args.run_id,
            "status": "ERROR", "passed": 0, "failed": 0, "errors": 1,
            "unverified": 0, "duration": 0, "cases": []}), encoding="utf-8")
        sys.exit(1)
    if isinstance(summary, dict) and summary.get("preflight", {}).get("status") == "blocked":
        sys.exit(2)
