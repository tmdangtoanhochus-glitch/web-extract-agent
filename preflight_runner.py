"""Check user-filled config without opening browser or reading environment files."""
import argparse
import json
from runner_agent.preparation import read_workbook
from runner_agent.preflight import check

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    try:
        report = check(read_workbook(args.config))
        print(json.dumps(report, ensure_ascii=True, indent=2))
    except Exception as error:
        raise SystemExit(f"Preflight stopped ({type(error).__name__}); no browser or secret checks performed.") from None
    raise SystemExit(0 if report["ready_for_local_review"] else 1)
