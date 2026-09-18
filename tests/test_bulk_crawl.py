from datetime import date
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.bulk_crawl import CrawlOptions, plan_urls, run_bulk, table_rows
from src.fetch.base import FetchResult, utcnow
from src.scheduler import CrawlScheduler
from src.storage.sqlite_storage import SQLiteStorage


HTML = '<table id="history"><tr><th>Date</th><th>Price</th></tr><tr><td>2026-09-15</td><td>10</td></tr><tr><td>2026-09-16</td><td>20</td></tr></table>'


class Fetcher:
    def __init__(self):
        self.calls = []
        self.html = HTML

    def fetch(self, url):
        self.calls.append(url)
        return FetchResult(url=url, final_url=url, status_code=200, html=self.html,
                           fetched_at=utcnow(), success=True)


def options(**kwargs):
    return CrawlOptions(mode="table", columns={"day": 1, "price": 2}, date_field="day", **kwargs)


def test_inclusive_windows_pages_and_limits():
    config = options(start_date=date(2026, 9, 14), end_date=date(2026, 9, 16), window_days=2, pages=2)
    urls = plan_urls("https://example.test/?from={start}&to={end}&page={page}", config)
    assert [u for u, _, _ in urls] == [
        "https://example.test/?from=2026-09-14&to=2026-09-15&page=1",
        "https://example.test/?from=2026-09-14&to=2026-09-15&page=2",
        "https://example.test/?from=2026-09-16&to=2026-09-16&page=1",
        "https://example.test/?from=2026-09-16&to=2026-09-16&page=2"]
    with pytest.raises(ValueError):
        plan_urls("https://example.test/{start}/{page}", options(start_date=date(2020, 1, 1), end_date=date(2026, 1, 1)))
    with pytest.raises(ValueError):
        plan_urls("https://example.test/", options(pages=2))


def test_date_filter_uses_record_date_and_rejects_ambiguous_table():
    rows = table_rows(HTML, options(), date(2026, 9, 16), date(2026, 9, 16))
    assert len(rows) == 1 and rows[0][0]["price"] == "20"
    assert rows[0][1].date() == date(2026, 9, 16)
    # Nhiều bảng khớp selector được gộp (tính năng v2), không còn báo mơ hồ.
    assert len(table_rows(HTML + HTML, options(), None, None)) == 2 * len(table_rows(HTML, options(), None, None))
    with pytest.raises(ValueError):
        table_rows(HTML.replace('<td>10</td>', '<td colspan="2">10</td>'), options(), None, None)


def test_backfill_repeat_append_and_concurrent_overlap():
    store = SQLiteStorage(":memory:")
    fetcher = Fetcher()
    args = dict(url="https://example.test/table", field_descriptions={"day": "Date", "price": "Price"},
                options=options(), fetcher=fetcher, ai_client=None, storage=store)
    initial = run_bulk(**args, dataset_name="History")
    assert initial["saved"] == 2
    repeated = run_bulk(**args, dataset_id=initial["dataset_id"])
    assert repeated["saved"] == 0 and repeated["skipped"] == 2
    fetcher.html = HTML.replace('</table>', '<tr><td>2026-09-17</td><td>30</td></tr></table>')
    with ThreadPoolExecutor(2) as pool:
        runs = list(pool.map(lambda _: run_bulk(**args, dataset_id=initial["dataset_id"]), range(2)))
    assert sum(run["saved"] for run in runs) == 1
    assert len(store.list_records(initial["dataset_id"])) == 3


def test_table_partial_failures_keep_successful_rows():
    class Partial(Fetcher):
        def fetch(self, url):
            if "page=2" in url:
                raise TypeError("synthetic private response")
            return super().fetch(url)
    store = SQLiteStorage(":memory:")
    result = run_bulk(url="https://example.test/?page={page}", field_descriptions={"day": "date", "price": "price"},
                      options=options(pages=2), fetcher=Partial(), ai_client=None, storage=store, dataset_name="History")
    assert result["status"] == "partial" and result["saved"] == 2 and result["failed"] == 1
    assert "private" not in str(result)


def test_schedule_reload_and_rolling_window(tmp_path):
    path = str(tmp_path / "schedule.sqlite")
    store = SQLiteStorage(path)
    dataset = store.create_dataset("History", ["day", "price"])
    scheduler = CrawlScheduler(Fetcher(), None, store)
    job = scheduler.add_job(dataset.dataset_id, "https://example.test/?from={start}&to={end}",
                            {"day": "date", "price": "price"}, "interval", {"hours": 1},
                            crawl_options=options(lookback_days=7, window_days=7).model_dump(mode="json"))
    store.close()
    reopened = SQLiteStorage(path)
    restored = reopened.get_scheduled_job(job.job_id)
    assert restored.crawl_options["lookback_days"] == 7
    plan = plan_urls(restored.url, CrawlOptions.model_validate(restored.crawl_options), today=date(2026, 9, 16))
    assert plan[0][0].endswith("from=2026-09-10&to=2026-09-16")
    fetcher = Fetcher()
    # No real clock-dependent expected dates: schedule without range also survives reload.
    stable = CrawlScheduler(fetcher, None, reopened)
    stable._run_job(job.job_id)
    assert reopened.get_scheduled_job(job.job_id).last_status == "completed"


def test_api_bulk_then_schedule_and_validation():
    store = SQLiteStorage(":memory:")
    client = TestClient(create_app(Fetcher(), None, store))
    body = dict(url="https://example.test/", dataset_name="History", field_descriptions={"day": "date", "price": "price"},
                crawl_options=options().model_dump(mode="json"))
    response = client.post("/crawl", json=body)
    assert response.status_code == 200 and response.json()["saved"] == 2
    body.update(dataset_id=response.json()["dataset_id"], trigger_type="interval", trigger_args={"hours": 1})
    assert client.post("/schedules", json=body).status_code == 200
    body["crawl_options"]["table_selector"] = "["
    assert client.post("/crawl", json=body).status_code == 422
    body["cookie_header"] = {"synthetic_sensitive": "do_not_echo"}
    invalid = client.post("/crawl", json=body)
    assert invalid.status_code == 422 and "do_not_echo" not in invalid.text


def test_file_table_append(tmp_path, monkeypatch):
    from src.storage import file_writer
    # Supply an explicit exports_root through the real writer while retaining sandbox isolation.
    from src import bulk_crawl
    original = file_writer.write_record
    monkeypatch.setattr(bulk_crawl, "write_record", lambda **kwargs: original(**kwargs, exports_root=tmp_path))
    result = run_bulk(url="https://example.test/", field_descriptions={"day": "date", "price": "price"},
                      options=options(), fetcher=Fetcher(), ai_client=None, storage=SQLiteStorage(":memory:"),
                      storage_mode="file", file_path="history.json")
    assert result["saved"] == 2 and (tmp_path / "history.json").exists()


def test_dedup_checks_history_beyond_first_page():
    store = SQLiteStorage(":memory:")
    fetcher = Fetcher()
    args = dict(url="https://example.test/", field_descriptions={"day": "date", "price": "price"},
                options=options(), fetcher=fetcher, ai_client=None, storage=store)
    initial = run_bulk(**args, dataset_name="History")
    for index in range(1001):
        store.save_record(initial["dataset_id"], "https://example.test/archive", {"day": "", "price": str(index)}, f"filler-{index}")
    repeated = run_bulk(**args, dataset_id=initial["dataset_id"])
    assert repeated["saved"] == 0 and repeated["skipped"] == 2


def test_existing_sqlite_jobs_migrate_without_losing_data(tmp_path):
    import sqlite3
    path = str(tmp_path / "legacy.sqlite")
    store = SQLiteStorage(path)
    job = store.create_scheduled_job(None, "https://example.test", {"price": "Price"}, "interval", {"hours": 1})
    store.close()
    with sqlite3.connect(path) as connection:
        connection.execute("ALTER TABLE scheduled_jobs DROP COLUMN crawl_options")
    migrated = SQLiteStorage(path)
    restored = migrated.get_scheduled_job(job.job_id)
    assert restored.url == "https://example.test" and restored.crawl_options is None
