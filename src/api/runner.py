"""HTTP contracts của Runner; mọi run/artifact đều kiểm tra owner hoặc agent."""
import base64
from typing import Literal
from threading import BoundedSemaphore

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from ..runner.service import RunnerError, TERMINAL, digest, safe_path


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(StrictModel):
    username: str
    password: str


class UserCreate(Login):
    role: Literal["user", "admin"] = "user"


class Active(StrictModel):
    is_active: bool


class RunCreate(StrictModel):
    agent_id: str
    config_name: str
    config_base64: str | None = Field(default=None, max_length=14_000_000)
    local_ref: str | None = None


class Result(StrictModel):
    passed: int = Field(ge=0, le=100000)
    failed: int = Field(ge=0, le=100000)
    errors: int = Field(ge=0, le=100000)
    unverified: int = Field(ge=0, le=100000)
    duration: float = Field(ge=0, le=604800, allow_inf_nan=False)


class Describe(StrictModel):
    description: str = Field(min_length=10, max_length=6000)
    reviewed_no_secrets: Literal[True]


def create_runner_router(service, planner=None):
    router = APIRouter(prefix="/runner", tags=["runner"])
    repo = service.repo
    planning_slots = BoundedSemaphore(2)

    def bearer(authorization: str = Header(default="")):
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "Cần đăng nhập")
        return authorization[7:]

    def user(token=Depends(bearer)):
        with repo.transaction():
            return service.authenticate(token)

    def admin(u=Depends(user)):
        if u["role"] != "admin":
            raise HTTPException(403, "Cần quyền admin")
        return u

    def agent(token=Depends(bearer)):
        with repo.transaction():
            return service.agent(token)

    @router.get("/authoring/capabilities")
    def authoring_capabilities(u=Depends(user)):
        return {"describe": planner is not None, "inspector": False, "local_inspector": True,
                "local_repair": True, "repair": False}

    @router.post("/authoring/describe")
    def describe(req: Describe, u=Depends(user)):
        if planner is None:
            raise HTTPException(503, "Describe AI chưa được bật.")
        from ..runner.planner import PlanError, validate_description
        from runner_agent.authoring import planned_workbook
        if not planning_slots.acquire(blocking=False):
            raise HTTPException(429, "Đang có yêu cầu tạo nháp; thử lại sau.")
        try:
            plan = planner.plan(validate_description(req.description))
            content = planned_workbook(plan)
            with repo.transaction():
                service.audit("DRAFT_GENERATED", u["id"])
            return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            headers={"Content-Disposition": 'attachment; filename="Describe_Draft.xlsx"',
                                     "Cache-Control": "no-store"})
        except PlanError as exc:
            raise HTTPException(422, str(exc)) from None
        except ValueError:
            raise HTTPException(422, "Workbook chưa hợp lệ; kiểm tra lại mô tả và các tham chiếu testcase.") from None
        finally:
            planning_slots.release()

    @router.post("/login")
    def login(req: Login):
        return service.login(req.username, req.password)

    @router.post("/logout")
    def logout(u=Depends(user), token=Depends(bearer)):
        with repo.transaction():
            repo.delete("sessions", digest(token))
            service.audit("LOGOUT", u["id"])
        return {"ok": True}

    @router.get("/me")
    def me(u=Depends(user)):
        return u

    @router.get("/users")
    def users(u=Depends(admin)):
        with repo.transaction():
            return [service.public_user(v) for v in repo.all("users")]

    @router.post("/users")
    def add_user(req: UserCreate, u=Depends(admin)):
        return service.add_user(req.username, req.password, req.role)

    @router.patch("/users/{uid}")
    def active(uid: str, req: Active, u=Depends(admin)):
        with repo.transaction():
            target = repo.get("users", uid)
            if not target:
                raise HTTPException(404, "Không tìm thấy user")
            if uid == u["id"] and not req.is_active:
                raise HTTPException(409, "Không tự khóa tài khoản đang dùng")
            target.update(is_active=req.is_active, updated_at=service.clock())
            repo.put("users", uid, target)
            service.audit("USER_ACTIVE_CHANGED", u["id"])
        return service.public_user(target)

    @router.post("/agents")
    def register(u=Depends(user)):
        return service.register_agent(u)

    @router.get("/agents")
    def agents(u=Depends(user)):
        with repo.transaction():
            return [{k: v for k, v in a.items() if k != "token_hash"}
                    for a in repo.all("agents") if a["owner"] == u["id"]]

    @router.delete("/agents/{aid}")
    def revoke(aid: str, u=Depends(user)):
        with repo.transaction():
            a = repo.get("agents", aid)
            if not a or a["owner"] != u["id"]:
                raise HTTPException(404, "Không tìm thấy agent")
            a["active"] = False
            repo.put("agents", aid, a)
            service.audit("AGENT_REVOKED", u["id"])
        return {"ok": True}

    @router.post("/runs")
    def create(req: RunCreate, u=Depends(user)):
        content = None
        if req.config_base64 is not None:
            try:
                content = base64.b64decode(req.config_base64, validate=True)
                from runner_agent.config import validate_workbook
                validate_workbook(content)
            except Exception:
                raise HTTPException(400, "Workbook không hợp lệ hoặc chứa dữ liệu không được phép")
        return service.create_run(u, req.agent_id, req.config_name, content, req.local_ref)

    @router.get("/runs")
    def runs(u=Depends(user)):
        with repo.transaction():
            return sorted([r for r in repo.all("runs") if r["owner"] == u["id"] or u["role"] == "admin"],
                          key=lambda r: r["created_at"], reverse=True)

    @router.get("/runs/{rid}")
    def run(rid: str, u=Depends(user)):
        with repo.transaction():
            return service.owned_run(rid, u)

    @router.post("/runs/{rid}/cancel")
    def cancel(rid: str, u=Depends(user)):
        with repo.transaction():
            r = service.owned_run(rid, u)
            if r["status"] != "QUEUED":
                raise HTTPException(409, "Chỉ hủy run đang chờ; run đang chạy cần dừng tại máy local")
            r.update(status="CANCELLED", finished_at=service.clock(), expires_at=service.clock()+604800)
            service.remove_temp(rid)
            repo.put("runs", rid, r)
            service.audit("RUN_CANCELLED", u["id"], rid)
        return r

    @router.get("/notifications")
    def notifications(u=Depends(user)):
        with repo.transaction():
            return [n for n in repo.all("notifications") if n["owner"] == u["id"] or u["role"] == "admin"]

    @router.get("/audit")
    def audit(u=Depends(admin)):
        with repo.transaction():
            return sorted(repo.all("audit"), key=lambda e: e["at"], reverse=True)

    @router.post("/agent/claim")
    def claim(a=Depends(agent)):
        return service.claim(a)

    @router.post("/agent/runs/{rid}/heartbeat")
    def heartbeat(rid: str, a=Depends(agent)):
        with repo.transaction():
            r = service.check_agent_run(a, rid)
            if r["status"] != "RUNNING":
                raise HTTPException(409, "Run đã kết thúc")
            r["heartbeat_at"] = service.clock()
            repo.put("runs", rid, r)
        return {"ok": True}

    @router.get("/agent/runs/{rid}/config")
    def config(rid: str, a=Depends(agent)):
        with repo.transaction():
            r = service.check_agent_run(a, rid)
            if r["status"] != "RUNNING" or r["local_ref"]:
                raise HTTPException(409, "Config không khả dụng")
            path = safe_path(service.root / "temp_uploads", rid, "testcase.xlsx")
            return FileResponse(path, filename="testcase.xlsx")

    @router.post("/agent/runs/{rid}/result")
    def result(rid: str, req: Result, a=Depends(agent)):
        r = service.finish(a, rid, req.model_dump())
        # Báo cáo cloud chỉ chứa số liệu xác định; không nhận log/DOM/Excel thô.
        with repo.transaction():
            r = service.check_agent_run(a, rid)
            folder = safe_path(service.root / "runs", rid)
            if not r["deleted_at"]:
                folder.mkdir(exist_ok=True)
                import json
                (folder / "summary.json").write_text(json.dumps({k: r[k] for k in
                    ("run_id", "status", "passed", "failed", "errors", "unverified", "duration")}), encoding="utf-8")
        return r

    @router.get("/runs/{rid}/artifacts/{name}")
    def artifact(rid: str, name: str, u=Depends(user)):
        with repo.transaction():
            r = service.owned_run(rid, u)
            if r["deleted_at"] or name != "summary.json":
                raise HTTPException(404, "Không tìm thấy artifact")
            path = safe_path(service.root / "runs", rid, name)
            if not path.is_file():
                raise HTTPException(404, "Không tìm thấy artifact")
            return FileResponse(path, filename=name)

    return router
