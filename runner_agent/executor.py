"""Worker CLI: chỉ chạy ở máy người dùng, tuyệt đối không import từ API."""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

from .config import validate_workbook


def execute(config, run_id, output, env_path=None):
    source = Path(__file__).resolve().parents[1] / "docs" / "runner.py"
    validate_workbook(Path(config).read_bytes())
    spec = importlib.util.spec_from_file_location("local_uat_runner", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.execute_config(config, run_id=run_id, output_dir=output, env_path=env_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--env-path")
    args = parser.parse_args()
    try:
        execute(args.config, args.run_id, args.output, args.env_path)
    except BaseException:
        # Không đưa exception/DOM/credential vào IPC hoặc stdout.
        output = Path(args.output)
        output.mkdir(parents=True, exist_ok=True)
        (output / "summary.json").write_text(json.dumps({"run_id": args.run_id,
            "status": "ERROR", "passed": 0, "failed": 0, "errors": 1,
            "unverified": 0, "duration": 0, "cases": []}), encoding="utf-8")
        sys.exit(1)
