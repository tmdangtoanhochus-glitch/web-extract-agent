from threading import Event
import time
import pytest

from src.crawl_tasks import CrawlTasks, QueueFull, TaskNotFound


def wait_for(predicate, timeout=4):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    assert predicate()


def test_pause_resume_cancel_and_capability_isolation():
    tasks = CrawlTasks(workers=1)
    entered, release = Event(), Event()
    def execute(checkpoint, progress):
        entered.set()
        release.wait(3)
        if not checkpoint():
            return {"status": "cancelled"}
        progress({"processed": 1})
        return {"status": "completed"}
    job = tasks.submit(execute)
    try:
        assert entered.wait(2)
        with pytest.raises(TaskNotFound):
            tasks.action(job["id"], "wrong", "cancel")
        tasks.action(job["id"], job["control"], "pause")
        release.set()
        wait_for(lambda: tasks.status(job["id"], job["control"])["state"] == "paused")
        assert "control" not in tasks.status(job["id"], job["control"])
        tasks.action(job["id"], job["control"], "resume")
        wait_for(lambda: tasks.status(job["id"], job["control"])["state"] == "completed")
        assert tasks.status(job["id"], job["control"])["progress"]["processed"] == 1
    finally:
        release.set()
        tasks.shutdown()


def test_cancel_queued_job_does_not_execute_and_capacity_is_bounded():
    tasks = CrawlTasks(workers=1, capacity=2)
    entered, release = Event(), Event()
    ran = []
    def first(checkpoint, progress):
        entered.set()
        release.wait(3)
        return {"status": "completed"}
    a = tasks.submit(first)
    assert entered.wait(2)
    b = tasks.submit(lambda *_: ran.append(True))
    try:
        with pytest.raises(QueueFull):
            tasks.submit(lambda *_: {})
        tasks.action(b["id"], b["control"], "cancel")
        release.set()
        wait_for(lambda: tasks.status(b["id"], b["control"])["state"] == "cancelled")
        assert ran == []
    finally:
        release.set()
        tasks.shutdown()


def test_pause_timeout_cancels_and_exceptions_do_not_echo_data():
    tasks = CrawlTasks(workers=1, pause_seconds=0.05)
    entered, release = Event(), Event()
    def execute(checkpoint, progress):
        entered.set()
        release.wait(3)
        return {"status": "completed" if checkpoint() else "cancelled"}
    a = tasks.submit(execute)
    try:
        assert entered.wait(2)
        tasks.action(a["id"], a["control"], "pause")
        release.set()
        wait_for(lambda: tasks.status(a["id"], a["control"])["state"] == "cancelled")
        def broken(*_):
            raise TypeError("synthetic-private-data")
        b = tasks.submit(broken)
        wait_for(lambda: tasks.status(b["id"], b["control"])["state"] == "failed")
        assert "synthetic-private-data" not in str(tasks.status(b["id"], b["control"]))
    finally:
        release.set()
        tasks.shutdown()
