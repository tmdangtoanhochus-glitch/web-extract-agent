from pathlib import Path

import pytest

from scripts.prepare_container_context import FIXED, prepare


def fixture_source(root):
    for relative in (*FIXED, "src/__init__.py", "ui/app.py"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"# synthetic source\r\n")


def test_context_only_reads_allowed_sources_and_normalizes_shell(tmp_path, monkeypatch):
    fixture_source(tmp_path)
    # Trap unapproved reads without creating any credential file.
    original = Path.read_text
    allowed = {tmp_path / p for p in (*FIXED, "src/__init__.py", "ui/app.py")}
    def guarded(path, *args, **kwargs):
        assert path in allowed
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", guarded)
    (tmp_path / "src" / "state.json").write_text("synthetic")
    (tmp_path / "src" / ".private").mkdir()
    (tmp_path / "src" / ".private" / "hidden.py").write_text("synthetic")
    context, count = prepare(tmp_path)
    assert count == len(allowed)
    assert not (context / "src/state.json").exists()
    assert not (context / "src/.private").exists()
    assert (context / "deploy/start-ui.sh").read_bytes() == b"# synthetic source\n"
    assert len(list(context.rglob("*.*"))) == count + 1
    second, _ = prepare(tmp_path)
    assert second != context


def test_context_rejects_link_before_read(tmp_path, monkeypatch):
    fixture_source(tmp_path)
    from scripts import prepare_container_context as module
    monkeypatch.setattr(module, "linked", lambda path: path == tmp_path / "src")
    monkeypatch.setattr(Path, "read_text", lambda *args, **kwargs: pytest.fail("unexpected read"))
    with pytest.raises(ValueError, match="Linked"):
        prepare(tmp_path)
    assert not (tmp_path / ".test-work").exists()


def test_context_rejects_linked_output(tmp_path, monkeypatch):
    fixture_source(tmp_path)
    from scripts import prepare_container_context as module
    monkeypatch.setattr(module, "linked", lambda path: path == tmp_path / ".test-work")
    with pytest.raises(ValueError, match="Linked output"):
        prepare(tmp_path)
