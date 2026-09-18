import dataclasses
import json

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.admin import create_admin_router
from src.api.main import create_app
from src.ai.debug_assistant import DebugSuggestion
from src.fetch.base import AllowAllRobotsChecker
from src.fetch.httpx_fetcher import HttpxFetcher
from src.storage.sqlite_storage import SQLiteStorage


def test_cookie_scoped_redirect_and_next_request():
    requests = []
    def handler(req):
        requests.append((str(req.url), req.headers.get("Cookie")))
        if req.url.path == "/redirect":
            return httpx.Response(302, headers={"location": "https://other.test/"})
        return httpx.Response(200, text="<p>synthetic-cookie-value</p>")
    fetcher = HttpxFetcher("test", robots_checker=AllowAllRobotsChecker(), client=httpx.Client(transport=httpx.MockTransport(handler)))
    scoped = fetcher.with_request_cookie("https://example.test/", "session=synthetic-cookie-value")
    assert "synthetic-cookie-value" not in scoped.fetch("https://example.test/").html
    assert scoped.fetch("https://example.test/redirect").error == "cookie_cross_origin_redirect_blocked"
    fetcher.fetch("https://example.test/")
    assert requests[-1][1] is None and len(requests) == 3


def test_error_report_preserves_context_without_cookie_or_query():
    class Broken:
        def fetch(self, url):
            raise TypeError("synthetic-private-value")
    store = SQLiteStorage(":memory:")
    client = TestClient(create_app(Broken(), None, store, admin_username="test", admin_password="synthetic"))
    response = client.post("/crawl", json={"url": "https://example.test/table?secret=synthetic-query", "dataset_name": "d", "field_descriptions": {"price": "Price"}})
    assert response.status_code == 500
    request_id = response.headers["X-Crawl-Request-ID"]
    report = client.post("/crawl-reports", json={"request_id": request_id, "ui_step": 3, "error_type": "TypeError"})
    assert report.status_code == 201
    assert client.get("/admin/crawl-reports").status_code == 401
    inbox = client.get("/admin/crawl-reports", auth=("test", "synthetic")).json()
    assert inbox[0]["detail"]["outcomes"][0]["error_type"] == "TypeError"
    assert "synthetic-private" not in str(inbox) and "synthetic-query" not in str(inbox)
    bad = client.post("/crawl-reports", json={"ui_step": 3, "cookie_header": "synthetic-cookie"})
    assert bad.status_code == 422 and "synthetic-cookie" not in bad.text


def test_admin_diagnosis_persists_and_uses_metadata_only():
    store = SQLiteStorage(":memory:")
    report = store.add_audit_log("user_crawl_report", detail={"client_error_type": "TypeError", "ui_step": 3})
    calls = []
    def ai(**kwargs):
        calls.append(kwargs)
        return DebugSuggestion("Check numeric formatting")
    app = FastAPI()
    app.include_router(create_admin_router(store, "", "", "", suggest_fix_fn=ai, admin_username="test", admin_password="synthetic"))
    client = TestClient(app)
    path = f"/admin/crawl-reports/{report.id}/diagnose"
    assert client.post(path).status_code == 401
    assert client.post(path, auth=("test", "synthetic")).status_code == 200
    assert json.loads(calls[0]["traceback_text"])["client_error_type"] == "TypeError"
    assert store.list_audit_log(job_id=report.id)[0].detail["content"] == "Check numeric formatting"


def test_api_cookie_not_stored_or_used_by_other_requests():
    seen = []
    def handler(req):
        seen.append(req.headers.get("cookie"))
        return httpx.Response(200, text='<table><tr><td>10</td></tr></table>')
    store = SQLiteStorage(":memory:")
    fetcher = HttpxFetcher("test", robots_checker=AllowAllRobotsChecker(), client=httpx.Client(transport=httpx.MockTransport(handler)))
    client = TestClient(create_app(fetcher, None, store))
    body = {"url": "https://example.test/", "field_descriptions": {"price": "Price"}, "dataset_name": "d",
            "crawl_options": {"mode": "table", "columns": {"price": 1}},
            "cookie_origin": "https://example.test", "cookie_header": "session=synthetic-cookie"}
    response = client.post("/crawl", json=body)
    assert response.status_code == 200
    assert seen == ["session=synthetic-cookie"]
    assert not store.list_site_credentials()
    assert "synthetic-cookie" not in str([dataclasses.asdict(e) for e in store.list_audit_log()])
    del body["cookie_header"]
    assert client.post("/crawl", json=body).status_code == 200
    assert seen[-1] is None
    body.update(cookie_header="session=synthetic-cookie", cookie_origin="https://other.test")
    assert client.post("/crawl", json=body).status_code == 400
