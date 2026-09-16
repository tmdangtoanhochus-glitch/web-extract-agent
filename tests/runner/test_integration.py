import io
import json
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from openpyxl import Workbook

from src.api.runner import create_runner_router
from src.runner.repository import Repository
from src.runner.service import RunnerError, Service, safe_path
from runner_agent.client import LocalAgent
from runner_agent.config import validate_workbook


@pytest.fixture
def system(tmp_path):
    repo = Repository()
    now = [1000000.0]
    service = Service(repo, tmp_path / "server", clock=lambda: now[0])
    owner = service.add_user("owner", "synthetic-password-1", "admin")
    other = service.add_user("other", "synthetic-password-2")
    pair = service.register_agent(owner)
    agent = service.agent(pair["agent_token"])
    app = FastAPI()
    @app.exception_handler(RunnerError)
    async def handler(req, exc):
        return JSONResponse(status_code=exc.code, content={"detail": str(exc)})
    app.include_router(create_runner_router(service))
    yield service, repo, now, owner, other, agent, TestClient(app)
    repo.close()


def login(client, name="owner", password="synthetic-password-1"):
    response = client.post("/runner/login", json={"username": name, "password": password})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["session"]}


def create(service, owner, agent):
    return service.create_run(owner, agent["id"], "UAT.xlsx", local_ref="UAT.xlsx")


def metrics():
    return {"passed": 1, "failed": 0, "errors": 0, "unverified": 0, "duration": 2}


def test_login_logout_and_hash_storage(system):
    s, repo, _, owner, _, _, client = system
    auth = login(client)
    assert client.get("/runner/me", headers=auth).status_code == 200
    with repo.transaction():
        raw = repo.get("users", owner["id"])
        assert raw["password_hash"].startswith("$argon2id$")
        assert "synthetic-password-1" not in json.dumps(raw)
    assert client.post("/runner/logout", headers=auth).status_code == 200
    assert client.get("/runner/me", headers=auth).status_code == 401


def test_wrong_password_and_unknown_user_rejected(system):
    client = system[-1]
    for username in ("owner", "missing"):
        assert client.post("/runner/login", json={"username": username, "password": "bad"}).status_code == 401


def test_owner_cannot_read_other_run_or_artifact(system):
    s, _, _, owner, _, agent, client = system
    run = create(s, owner, agent)
    auth = login(client, "other", "synthetic-password-2")
    assert client.get("/runner/runs", headers=auth).json() == []
    for suffix in ("", "/artifacts/summary.json"):
        assert client.get("/runner/runs/" + run["run_id"] + suffix, headers=auth).status_code == 404
    assert client.get("/runner/users", headers=auth).status_code == 403


def test_disabled_user_invalidates_existing_session_and_agent(system):
    s, _, _, _, other, _, client = system
    pair = s.register_agent(other)
    auth = login(client, "other", "synthetic-password-2")
    client.patch("/runner/users/" + other["id"], json={"is_active": False}, headers=login(client))
    assert client.get("/runner/me", headers=auth).status_code == 401
    assert client.post("/runner/agent/claim", headers={"Authorization": "Bearer " + pair["agent_token"]}).status_code == 401


def test_claim_is_atomic_and_never_reexecutes_active_job(system):
    s, _, _, owner, _, agent, _ = system
    run = create(s, owner, agent)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: s.claim(agent), range(4)))
    assert sum(r is not None for r in results) == 1
    assert next(r for r in results if r)["run_id"] == run["run_id"]


def test_run_name_collision_and_temp_deletion(system):
    s, _, _, owner, _, agent, _ = system
    first = s.create_run(owner, agent["id"], "UAT.xlsx", config=b"fake-only-service-test")
    second = create(s, owner, agent)
    assert first["run_id"] != second["run_id"]
    s.claim(agent)
    s.finish(agent, first["run_id"], metrics())
    assert not (s.root / "temp_uploads" / first["run_id"]).exists()


def test_result_is_idempotent_and_retention_preserves_audit(system):
    s, repo, now, owner, _, agent, _ = system
    run = create(s, owner, agent)
    s.claim(agent)
    done = s.finish(agent, run["run_id"], metrics())
    now[0] += 100
    assert s.finish(agent, run["run_id"], metrics())["finished_at"] == done["finished_at"]
    folder = s.root / "runs" / run["run_id"]
    folder.mkdir()
    (folder / "summary.json").write_text("{}")
    now[0] = done["expires_at"] - 86400
    s.maintenance()
    assert folder.exists()
    now[0] = done["expires_at"]
    s.maintenance()
    assert not folder.exists()
    with repo.transaction():
        r = repo.get("runs", run["run_id"])
        assert r["deleted_at"] == now[0]
        assert any(e["event"] == "RUN_ARTIFACTS_DELETED" for e in repo.all("audit"))


def test_late_notice_delays_deletion_and_offline_run_never_requeues(system):
    s, repo, now, owner, _, agent, _ = system
    r = create(s, owner, agent)
    s.claim(agent)
    now[0] += 301
    s.maintenance()
    with repo.transaction():
        assert repo.get("runs", r["run_id"])["status"] == "LOST"
    assert s.claim(agent) is None
    now[0] += 8 * 86400
    s.maintenance()
    with repo.transaction():
        assert repo.get("runs", r["run_id"])["deleted_at"] is None
    now[0] += 86400
    s.maintenance()
    with repo.transaction():
        assert repo.get("runs", r["run_id"])["deleted_at"] is not None


@pytest.mark.parametrize("name", ["../data", "a/b", "C:\\x", "..", "a:b"])
def test_paths_stay_inside_artifact_root(tmp_path, name):
    with pytest.raises(RunnerError):
        safe_path(tmp_path, name)


def workbook():
    wb = Workbook()
    wb.active.title = "settings"
    wb.active.append(["key", "value"])
    wb.active.append(["url", "https://example.test"])
    ws = wb.create_sheet("steps")
    ws.append(["screen", "step", "action", "value_source"])
    ws.append(["login", "username", "fill", "account"])
    ws = wb.create_sheet("testcases")
    ws.append(["tc_id", "role_code"])
    ws.append(["T1", "RM"])
    stream = io.BytesIO()
    wb.save(stream)
    return stream.getvalue()


def test_agent_local_config_never_uploaded_and_never_deleted(tmp_path):
    configs = tmp_path / "configs"
    configs.mkdir()
    source = configs / "UAT.xlsx"
    source.write_bytes(workbook())
    seen = []
    def handler(req):
        seen.append((req.method, req.url.path, req.content))
        return httpx.Response(200, json={})
    client = httpx.Client(base_url="http://localhost:8000", transport=httpx.MockTransport(handler))
    agent = LocalAgent("http://localhost:8000", "fake", configs, tmp_path / "local", client=client)
    calls = []
    def worker(config, rid, output):
        calls.append(rid)
        assert config.read_bytes() == source.read_bytes()
        return metrics()
    run = {"run_id": "UAT_20260101_000000", "local_ref": "UAT.xlsx"}
    agent.run(run, worker=worker)
    agent.run(run, worker=worker)
    assert calls == [run["run_id"]]
    assert source.exists()
    assert not (agent.state / "temp_uploads" / run["run_id"]).exists()
    assert len(seen) == 1
    assert set(json.loads(seen[0][2])) == set(metrics())


def test_agent_blocks_remote_plain_http(tmp_path):
    with pytest.raises(ValueError):
        LocalAgent("http://remote.example", "fake", tmp_path, tmp_path)


def test_workbook_rejects_formula_and_plaintext_credential():
    for column, value in [("password", "synthetic-secret"), ("foo", "=1+1")]:
        wb = Workbook()
        wb.active.title = "settings"
        wb.create_sheet("steps")
        sheet = wb.create_sheet("testcases")
        sheet.append([column])
        sheet.append([value])
        stream = io.BytesIO()
        wb.save(stream)
        with pytest.raises((ValueError, StopIteration)):
            validate_workbook(stream.getvalue())
