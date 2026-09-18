"""Chạy suite không secret, không mạng; không import ứng dụng trước khi cô lập."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Xóa environment kế thừa mà không đọc/in giá trị credential.
os.environ.clear()
os.environ.update({"SYSTEMROOT": "C:\\Windows", "WINDIR": "C:\\Windows",
                   "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHONDONTWRITEBYTECODE": "1",
                   "PYTHON_DOTENV_DISABLED": "1", "DB_PATH": ":memory:"})
os.environ["USERPROFILE"] = str(ROOT / ".test-work" / "home")
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / ".test-deps"))


def guard(event, args):
    if event == "open" and isinstance(args[0], (str, bytes)):
        path = Path(os.fsdecode(args[0]))
        name = path.name.lower()
        if (name in (".env", "runner.env", "secrets.toml", "credentials.json") or
                (name.startswith(".env.") and name != ".env.example") or
                name.endswith((".pem", ".key")) or
                "secrets" in [p.lower() for p in path.parts]):
            raise PermissionError("Test blocked a protected file access")
    if event in ("socket.connect", "socket.getaddrinfo"):
        # asyncio trên Windows dùng loopback socketpair để đánh thức event loop.
        if (event == "socket.connect" and sys._getframe(1).f_code.co_name == "_fallback_socketpair"
                and args[1][0] in ("127.0.0.1", "::1")):
            return
        raise PermissionError("Offline tests cannot access the network")


sys.addaudithook(guard)
import pytest

if __name__ == "__main__":
    import uuid
    temp = ROOT / ".test-work" / uuid.uuid4().hex
    temp.parent.mkdir(exist_ok=True)
    raise SystemExit(pytest.main([str(ROOT / "tests"), "-q", "-p", "no:cacheprovider",
                                  "--tb=short", "--basetemp", str(temp), *sys.argv[1:]]))
