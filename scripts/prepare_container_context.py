"""Stage source-only API/UI build context; never copy the workspace wholesale."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import uuid

ROOT = Path(__file__).resolve().parents[1]
FIXED = (
    "Dockerfile.api", "Dockerfile.ui", "requirements.txt", "requirements-auth.txt",
    "deploy/nginx-ui.conf", "deploy/start-ui.sh", "scripts/create_runner_admin.py",
    "runner_agent/__init__.py", "runner_agent/authoring.py", "runner_agent/config.py",
    "scripts/container_probe.py",
)


def excluded(name: str) -> bool:
    name = name.lower()
    return (name.startswith(".") or name == "__pycache__" or
            any(word in name for word in ("secret", "credential", "password", "token")))


def linked(path: Path) -> bool:
    return path.is_symlink() or getattr(path, "is_junction", lambda: False)()


def source_files(root: Path):
    """Only Python application sources and explicit packaging inputs are eligible."""
    def walk(folder):
        if linked(folder):
            raise ValueError("Linked source directory is not allowed")
        for path in sorted(folder.iterdir()):
            if excluded(path.name):
                continue
            if linked(path):
                raise ValueError("Linked source entry is not allowed")
            if path.is_dir():
                yield from walk(path)
            elif path.suffix == ".py":
                yield path

    for relative in FIXED:
        path = root / relative
        if any(linked(p) for p in (path, *path.parents)):
            raise ValueError("Linked packaging input is not allowed")
        if not path.is_file():
            raise ValueError("Required packaging input is missing")
        yield path
    for name in ("src", "ui"):
        yield from walk(root / name)


def prepare(root: Path) -> tuple[Path, int]:
    root = root.absolute()
    if any(linked(p) for p in (root, *root.parents)):
        raise ValueError("Linked workspace is not allowed")
    files = list(source_files(root))
    parent = root / ".test-work"
    if linked(parent):
        raise ValueError("Linked output directory is not allowed")
    parent.mkdir(exist_ok=True)
    output = parent / ("container-context-" + uuid.uuid4().hex)
    output.mkdir()
    manifest = {}
    for path in files:
        relative = path.relative_to(root)
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        # Text-only sources; normalize shell scripts for Linux builds from Windows.
        content = path.read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8")
        target.write_bytes(content)
        manifest[relative.as_posix()] = hashlib.sha256(content).hexdigest()
    (output / "BUILD_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output, len(manifest)


if __name__ == "__main__":
    path, count = prepare(ROOT)
    print(json.dumps({"context": str(path), "source_files": count}))
