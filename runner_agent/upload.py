"""Chỉ chuyển file người dùng chọn; từ chối đường dẫn credential và liên kết."""
from pathlib import Path


def local_upload_path(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Enter a local upload file in the testcase")
    path = Path(value).expanduser().absolute()
    if any(part.lower().startswith(".env") or part.lower() in {"runner.env", "secrets"}
           or any(word in part.lower() for word in ("credential", "password", "token", "secret"))
           for part in path.parts) or path.suffix.lower() in {".pem", ".key", ".p12", ".pfx", ".env"}:
        raise ValueError("Protected file cannot be uploaded")
    if any(p.is_symlink() or getattr(p, "is_junction", lambda: False)() for p in (path, *path.parents)):
        raise ValueError("Linked upload file cannot be used")
    if not path.is_file():
        raise ValueError("Upload file is unavailable")
    return str(path)
