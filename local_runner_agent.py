"""Chạy agent local bằng lệnh do người vận hành thực hiện."""
import argparse
import getpass
import os
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
    args = parser.parse_args()
    token = os.getenv("RUNNER_AGENT_TOKEN") or getpass.getpass("Agent token (UI cấp): ")
    if not token:
        raise SystemExit("Cần agent token")
    agent = LocalAgent(args.api, token, args.configs, args.state,
                       args.env_path or os.getenv("RUNNER_ENV_PATH"))
    with single_instance(agent.state):
        agent.recover()
        print("Runner agent đang chờ job; Ctrl+C để dừng.")
        while True:
            try:
                agent.tick()
            except httpx.HTTPError:
                print("Chưa kết nối được API; sẽ thử lại, không chạy lại testcase.")
            time.sleep(5)
