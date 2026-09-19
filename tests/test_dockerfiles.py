"""Dockerfile gốc (skill AgentBase) phải trùng Dockerfile.api, tránh 2 bản lệch nhau."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _body(name: str) -> str:
    lines = (ROOT / name).read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
    return "\n".join(line for line in lines if not line.startswith("#")).strip()


def test_root_dockerfile_matches_api_dockerfile_and_uses_port_8080():
    assert _body("Dockerfile") == _body("Dockerfile.api")
    assert "8080" in _body("Dockerfile") and "8000" not in _body("Dockerfile")
