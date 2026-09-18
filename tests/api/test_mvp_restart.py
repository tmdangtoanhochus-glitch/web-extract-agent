"""Offline acceptance rehearsal: shared API, real temporary SQLite, full lifespan."""
from contextlib import contextmanager

from fastapi.testclient import TestClient

from src.ai.base import ExtractionResult, FieldExtraction
from src.api.main import create_app
from src.fetch.base import FetchResult, utcnow
from src.runner.repository import Repository
from src.runner.service import Service
from src.storage.sqlite_storage import SQLiteStorage


class SyntheticFetcher:
    def __init__(self, broken=False):
        self.broken = broken

    def fetch(self, url):
        if self.broken:
            raise TypeError("synthetic-private-exception")
        return FetchResult(url, url, 200, "<p>synthetic item</p>", utcnow(), True)


class SyntheticAI:
    def extract(self, markdown, fields):
        return ExtractionResult(records=[{k: FieldExtraction("synthetic item", 0.95) for k in fields}])


@contextmanager
def application(root, broken=False):
    storage = SQLiteStorage(str(root / "crawl.db"))
    repo = Repository(str(root / "runner.db"))
    service = Service(repo, root / "artifacts", clock=lambda: 1000000)
    app = create_app(SyntheticFetcher(broken), SyntheticAI(), storage,
                     runner_service=service, admin_username="synthetic-admin",
                     admin_password="synthetic-admin-password")
    try:
        with TestClient(app) as client:
            yield client, service
    finally:
        repo.close()
        storage.close()


def login(client, name):
    response = client.post("/runner/login", json={"username": name, "password": "synthetic-test-password"})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["session"]}


def start_run(client, service):
    service.add_user("owner", "synthetic-test-password")
    service.add_user("other", "synthetic-test-password")
    headers = login(client, "owner")
    registered = client.post("/runner/agents", headers=headers)
    assert registered.status_code == 200
    pair = registered.json()
    agent_headers = {"Authorization": "Bearer " + pair["agent_token"]}
    created = client.post("/runner/runs", headers=headers, json={
        "agent_id": pair["agent_id"], "config_name": "Synthetic.xlsx", "local_ref": "Synthetic.xlsx"})
    assert created.status_code == 200
    rid = created.json()["run_id"]
    claimed = client.post("/runner/agent/claim", headers=agent_headers)
    assert claimed.status_code == 200 and claimed.json()["run_id"] == rid
    return rid, agent_headers


CRAWL = {"url": "https://example.test/synthetic", "field_descriptions": {"item": "item"},
         "dataset_name": "Synthetic acceptance"}


def test_crawler_and_finished_runner_survive_application_restart(tmp_path):
    with application(tmp_path) as (client, service):
        crawl = client.post("/crawl", json=CRAWL)
        assert crawl.status_code == 200 and crawl.json()["status"] == "saved"
        dataset = crawl.json()["dataset_id"]
        rid, agent_headers = start_run(client, service)
        metrics = {"passed": 1, "failed": 0, "errors": 0, "unverified": 0, "duration": 1}
        assert client.post(f"/runner/agent/runs/{rid}/result", headers=agent_headers, json=metrics).status_code == 200

    with application(tmp_path) as (client, _):
        assert client.get("/health").status_code == 200
        for path in ("/runner/me", "/runner/runs", "/runner/agents"):
            assert client.get(path).status_code == 401
        assert len(client.get(f"/datasets/{dataset}/records").json()) == 1
        crawl = client.post("/crawl", json={**CRAWL, "dataset_id": dataset})
        assert crawl.status_code == 200
        assert len(client.get(f"/datasets/{dataset}/records").json()) == 1  # dedup after reopen
        headers = login(client, "owner")
        result = client.get(f"/runner/runs/{rid}", headers=headers)
        assert result.status_code == 200 and result.json()["status"] == "PASSED"
        assert result.json()["passed"] == 1
        summary = client.get(f"/runner/runs/{rid}/artifacts/summary.json", headers=headers)
        assert summary.status_code == 200 and summary.json()["passed"] == 1
        assert client.get(f"/runner/runs/{rid}", headers=login(client, "other")).status_code == 404
        assert client.post("/runner/agent/claim", headers=agent_headers).json() is None


def test_crawl_failure_report_survives_restart_without_replaying_running_runner(tmp_path):
    with application(tmp_path, broken=True) as (client, service):
        rid, agent_headers = start_run(client, service)
        failed = client.post("/crawl", json={**CRAWL, "url": CRAWL["url"] + "?q=synthetic-private-query"})
        assert failed.status_code == 500
        report = client.post("/crawl-reports", json={
            "request_id": failed.headers["X-Crawl-Request-ID"], "ui_step": 3, "error_type": "TypeError"})
        assert report.status_code == 201
        report_id = report.json()["report_id"]

    with application(tmp_path) as (client, _):
        assert client.get("/admin/crawl-reports").status_code == 401
        reports = client.get("/admin/crawl-reports", auth=("synthetic-admin", "synthetic-admin-password"))
        assert reports.status_code == 200 and reports.json()[0]["id"] == report_id
        assert "synthetic-private" not in reports.text
        assert reports.json()[0]["detail"]["outcomes"][0]["error_type"] == "TypeError"
        state = client.get(f"/runner/runs/{rid}", headers=login(client, "owner"))
        assert state.status_code == 200 and state.json()["status"] == "RUNNING"
        claim = client.post("/runner/agent/claim", headers=agent_headers)
        assert claim.status_code == 200 and claim.json() is None
        # A previous crawl exception must not disable public crawl after reopening.
        assert client.post("/crawl", json=CRAWL).json()["status"] == "saved"
