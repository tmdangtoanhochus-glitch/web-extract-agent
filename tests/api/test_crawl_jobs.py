from threading import Event
import time
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.bulk_crawl import CrawlOptions, run_bulk
from src.fetch.base import FetchResult, utcnow
from src.storage.sqlite_storage import SQLiteStorage


class Fetcher:
    def __init__(self, blocked=False):
        self.entered, self.release = Event(), Event()
        self.blocked = blocked
        self.calls = []

    def fetch(self, url):
        self.calls.append(url)
        if self.blocked and len(self.calls) == 1:
            self.entered.set()
            assert self.release.wait(4)
        value = url.rsplit("=", 1)[-1]
        return FetchResult(url=url, final_url=url, status_code=200, fetched_at=utcnow(), success=True,
                           html=f"<table><tr><td>{value}</td></tr></table>")


def wait_state(client, job, target):
    for _ in range(300):
        response = client.get(f"/crawl-jobs/{job['id']}", headers={"X-Crawl-Control": job["control"]})
        if response.json()["state"] in target:
            return response.json()
        time.sleep(0.01)
    raise AssertionError(response.json())


def payload():
    return {"url": "https://example.test/?page={page}", "dataset_name": "History",
            "field_descriptions": {"id": "Identifier"},
            "crawl_options": {"mode": "table", "pages": 2, "columns": {"id": 1}}}


def test_api_pause_releases_bulk_lock_resume_refreshes_dedup():
    storage, fetcher = SQLiteStorage(":memory:"), Fetcher(True)
    app = create_app(fetcher, None, storage)
    client = TestClient(app)
    job = client.post("/crawl-jobs", json={"requests": [payload()]}).json()
    headers = {"X-Crawl-Control": job["control"]}
    path = f"/crawl-jobs/{job['id']}"
    try:
        assert fetcher.entered.wait(2)
        assert client.get(path).status_code == 404
        assert client.post(path + "/control", json={"action": "pause"}).status_code == 404
        assert client.post(path + "/control", headers=headers, json={"action": "pause"}).status_code == 200
        fetcher.release.set()
        paused = wait_state(client, job, {"paused"})
        dataset_id = paused["progress"]["dataset_id"]
        assert paused["progress"]["processed"] == 1 and len(fetcher.calls) == 1
        # Another crawl can append while this task is paused; resume must dedup its data.
        outcome = run_bulk(url="https://example.test/?page=2", field_descriptions={"id": "Identifier"},
            options=CrawlOptions(mode="table", columns={"id": 1}), fetcher=Fetcher(), ai_client=None,
            storage=storage, dataset_id=dataset_id)
        assert outcome["saved"] == 1
        client.post(path + "/control", headers=headers, json={"action": "resume"})
        completed = wait_state(client, job, {"completed"})
        assert completed["result"]["items"][0]["skipped"] == 1
        assert len(storage.list_records(dataset_id)) == 2
    finally:
        fetcher.release.set()
        app.state.crawl_tasks.shutdown()


def test_cancel_keeps_saved_data_and_stops_before_next_page():
    storage, fetcher = SQLiteStorage(":memory:"), Fetcher(True)
    app = create_app(fetcher, None, storage)
    client = TestClient(app)
    job = client.post("/crawl-jobs", json={"requests": [payload()]}).json()
    try:
        assert fetcher.entered.wait(2)
        client.post(f"/crawl-jobs/{job['id']}/control", headers={"X-Crawl-Control": job["control"]}, json={"action": "cancel"})
        fetcher.release.set()
        stopped = wait_state(client, job, {"cancelled"})
        assert len(fetcher.calls) == 1
        result = stopped["result"]["items"][0]
        assert result["saved"] == 1 and len(storage.list_records(result["dataset_id"])) == 1
        assert job["control"] not in str([event.detail for event in storage.list_audit_log()])
    finally:
        fetcher.release.set()
        app.state.crawl_tasks.shutdown()


def test_multiple_sources_share_destination_and_restart_loses_only_controls():
    storage, fetcher = SQLiteStorage(":memory:"), Fetcher()
    app = create_app(fetcher, None, storage)
    client = TestClient(app)
    body = payload()
    job = client.post("/crawl-jobs", json={"requests": [body, {**body, "url": "https://other.test/?page={page}"}]}).json()
    try:
        completed = wait_state(client, job, {"completed"})
        assert len(completed["result"]["items"]) == 2
        assert len(storage.list_datasets()) == 1
        assert len(storage.list_records(completed["result"]["dataset_id"])) == 2
        assert client.post("/crawl-jobs", json={"requests": [body, {**body, "dataset_name": "Different"}]}).status_code == 400
        restarted = create_app(fetcher, None, storage)
        assert TestClient(restarted).get(f"/crawl-jobs/{job['id']}", headers={"X-Crawl-Control": job["control"]}).status_code == 404
        restarted.state.crawl_tasks.shutdown()
    finally:
        app.state.crawl_tasks.shutdown()
