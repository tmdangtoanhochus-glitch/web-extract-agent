import pytest
from fastapi.testclient import TestClient
from src.api.main import create_app
from src.scheduler import CrawlScheduler
from src.storage.sqlite_storage import SQLiteStorage


def make_job(storage, scheduler):
    ds = storage.create_dataset("History", ["id"])
    return scheduler.add_job(ds.dataset_id, "https://example.test/?page={page}", {"id": "Identifier"},
        "interval", {"hours": 2}, crawl_options={"mode": "table", "columns": {"id": 1}, "pages": 2})


def test_pause_edit_restart_resume_preserves_data_and_history(tmp_path):
    path = str(tmp_path / "schedule.sqlite")
    storage = SQLiteStorage(path)
    scheduler = CrawlScheduler(None, None, storage)
    job = make_job(storage, scheduler)
    storage.update_scheduled_job_run(job.job_id, "completed")
    scheduler.configure(job.job_id, enabled=False)
    changed = scheduler.configure(job.job_id, trigger_type="cron",
                                   trigger_args={"hour": 8, "minute": 30, "timezone": "Asia/Ho_Chi_Minh"})
    assert changed.enabled is False and changed.last_status == "completed"
    assert changed.dataset_id == job.dataset_id and changed.crawl_options == job.crawl_options
    assert scheduler._scheduler.get_job(job.job_id) is None
    storage.close()
    storage = SQLiteStorage(path)
    scheduler = CrawlScheduler(None, None, storage)
    scheduler.start()
    try:
        assert scheduler._scheduler.get_job(job.job_id) is None
        resumed = scheduler.configure(job.job_id, enabled=True)
        described = scheduler.describe(resumed)
        assert described["next_run_at"] and described["timezone"] == "Asia/Ho_Chi_Minh"
        assert resumed.last_status == "completed"
    finally:
        scheduler.shutdown(wait=True)


def test_disabled_job_does_not_fetch_when_already_queued():
    class Forbidden:
        def fetch(self, url):
            raise AssertionError("Paused job executed")
    storage = SQLiteStorage(":memory:")
    scheduler = CrawlScheduler(Forbidden(), None, storage)
    job = make_job(storage, scheduler)
    scheduler.configure(job.job_id, enabled=False)
    scheduler._run_job(job.job_id)
    assert storage.get_scheduled_job(job.job_id).last_status is None


@pytest.mark.parametrize("kind,args", [("interval", {"seconds": 0}), ("interval", {"minutes": -1}),
    ("cron", {"hour": 25}), ("cron", {"hour": 8, "timezone": "Invalid/Zone"}), ("other", {})])
def test_invalid_create_leaves_no_persisted_job(kind, args):
    storage = SQLiteStorage(":memory:")
    scheduler = CrawlScheduler(None, None, storage)
    with pytest.raises(ValueError):
        scheduler.add_job(None, "https://example.test", {"id": "id"}, kind, args)
    assert storage.list_scheduled_jobs() == []


def test_api_update_is_partial_and_invalid_changes_leave_schedule_intact():
    storage = SQLiteStorage(":memory:")
    scheduler = CrawlScheduler(None, None, storage)
    job = make_job(storage, scheduler)
    client = TestClient(create_app(None, None, storage, scheduler=scheduler))
    path = f"/schedules/{job.job_id}"
    assert client.patch(path, json={"enabled": False}).status_code == 200
    assert client.patch(path, json={"trigger_type": "cron"}).status_code == 422
    assert client.patch(path, json={"url": "https://changed.test"}).status_code == 422
    assert client.patch(path, json={"trigger_type": "interval", "trigger_args": {"hours": 0}}).status_code == 400
    assert storage.get_scheduled_job(job.job_id).trigger_args == {"hours": 2}
    assert storage.get_scheduled_job(job.job_id).enabled is False
    assert client.patch("/schedules/missing", json={"enabled": True}).status_code == 404


def test_live_registration_failure_rolls_back_db(monkeypatch):
    storage = SQLiteStorage(":memory:")
    scheduler = CrawlScheduler(None, None, storage)
    job = make_job(storage, scheduler)
    def fail(*args):
        raise RuntimeError("synthetic registration failure")
    monkeypatch.setattr(scheduler, "_register_job", fail)
    with pytest.raises(RuntimeError):
        scheduler.configure(job.job_id, trigger_type="interval", trigger_args={"hours": 3})
    assert storage.get_scheduled_job(job.job_id).trigger_args == {"hours": 2}
