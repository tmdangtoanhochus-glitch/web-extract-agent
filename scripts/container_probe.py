"""Smoke checks ONLY for isolated disposable containers with synthetic data.

Run via docker exec after setting CONTAINER_SMOKE_ONLY=1 on that test container.
No credential, external URL, dotenv, or browser is used.
"""
import argparse
import io
import json
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import build_opener, ProxyHandler

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def response(path):
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open("http://127.0.0.1:8080" + path, timeout=3) as result:
            return result.status, result.read()
    except HTTPError as error:
        return error.code, b""
    except URLError:
        return 0, b""


def expect(path, status):
    for _ in range(30):
        code, body = response(path)
        if code == status:
            print(json.dumps({"path": path, "status": code}))
            return body
        time.sleep(1)
    raise RuntimeError(f"Unexpected status for {path}: {code}, expected {status}")


def api_probe(mode):
    expect("/health", 200)
    expect("/runner/me", 401)
    expect("/datasets", 200)
    # Exercise imports used lazily by the workbook endpoints in the cloud API.
    from runner_agent.authoring import Recording, draft_workbook
    from openpyxl import load_workbook
    recording = Recording()
    assert recording.accept({"action": "click", "locator": "button:nth-of-type(1)"})
    wb = load_workbook(io.BytesIO(draft_workbook(recording)))
    assert wb["testcases"].max_row == 1 and "settings" not in wb.sheetnames
    wb.close()
    print('{"workbook_headers_only": true}')
    from src.storage.sqlite_storage import SQLiteStorage
    from src.runner.repository import Repository
    # Fixed smoke paths must be explicitly configured on the disposable API.
    assert os.environ.get("DB_PATH") == "/smoke-data/crawl.db"
    assert os.environ.get("RUNNER_DB_PATH") == "/smoke-data/runner.db"
    storage = SQLiteStorage("/smoke-data/crawl.db")
    repo = Repository("/smoke-data/runner.db")
    try:
        if mode == "api-seed":
            assert not storage.list_datasets() and not repo.all("audit")
            storage.create_dataset("container-smoke-synthetic", ["synthetic_field"])
            with repo.transaction():
                repo.put("audit", "container-smoke", {"id": "container-smoke", "event": "SMOKE_TEST"})
        else:
            rows = storage.list_datasets()
            assert len(rows) == 1 and rows[0].dataset_name == "container-smoke-synthetic"
            assert repo.get("audit", "container-smoke")["event"] == "SMOKE_TEST"
        datasets = json.loads(expect("/datasets", 200))
        assert len(datasets) == 1 and datasets[0]["dataset_name"] == "container-smoke-synthetic"
        print(json.dumps({"storage": mode, "crawler_and_runner": "ok"}))
    finally:
        storage.close()
        repo.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("ui", "ui-down", "api-seed", "api-verify", "browser"))
    mode = parser.parse_args().mode
    if os.environ.get("CONTAINER_SMOKE_ONLY") != "1":
        raise SystemExit("Only run in explicitly marked disposable smoke containers")
    if mode == "browser":
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
            try:
                page = browser.new_page()
                page.set_content("<title>synthetic-smoke</title><button>test</button>")
                assert page.title() == "synthetic-smoke"
                assert page.locator("button").count() == 1
                print('{"chromium_synthetic_page": "ok"}')
            finally:
                browser.close()
    elif mode.startswith("api-"):
        api_probe(mode)
    else:
        expect("/health", 200)
        expect("/ready", 200 if mode == "ui" else 502)
        if mode == "ui":
            expect("/", 200)
