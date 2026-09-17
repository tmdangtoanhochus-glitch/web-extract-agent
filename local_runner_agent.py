"""Chạy agent local bằng lệnh do người vận hành thực hiện."""
import argparse
import getpass
import os
import json
import time

import httpx
from runner_agent.client import LocalAgent
from runner_agent.locking import single_instance


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--configs", default="config")
    parser.add_argument("--state", default="data/local-runner")
    parser.add_argument("--env-path")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--resend-run", help="Resend a completed result from local journal, without running a job")
    mode.add_argument("--journal-status", action="store_true", help="Read-only local journal diagnosis; no token or network")
    parser.add_argument("--run-id", help="Limit --journal-status to a known run ID")
    args = parser.parse_args()
    if args.run_id is not None and not args.journal_status:
        parser.error("--run-id requires --journal-status")
    if args.journal_status:
        from runner_agent.diagnostics import diagnose
        report = diagnose(args.state, run_id=args.run_id)
        print(json.dumps(report, ensure_ascii=True, indent=2))
        raise SystemExit(0 if report["status"] == "OK" else 2)
    token = os.getenv("RUNNER_AGENT_TOKEN") or getpass.getpass("Agent token (UI cấp): ")
    if not token:
        raise SystemExit("Cần agent token")
    agent = LocalAgent(args.api, token, args.configs, args.state,
                       args.env_path or os.getenv("RUNNER_ENV_PATH"))
    with single_instance(agent.state):
        if args.resend_run:
            try:
                agent.resend_result(args.resend_run)
            except (httpx.HTTPError, ValueError, OSError, KeyError):
                raise SystemExit("Không gửi được kết quả; kiểm tra API, đúng agent và journal. Không chạy lại testcase.") from None
            print("Đã gửi lại metadata kết quả; không nhận hoặc thực thi job.")
            raise SystemExit(0)
        agent.recover()
        print("Runner agent đang chờ job; Ctrl+C để dừng.")
        while True:
            try:
                agent.tick()
            except httpx.HTTPError:
                print("Chưa kết nối được API; sẽ thử lại, không chạy lại testcase.")
            time.sleep(5)
