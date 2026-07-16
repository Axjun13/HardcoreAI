from pathlib import Path

from services.hardware import _usable_project_path


def test_usable_project_path_rejects_missing_or_stale_paths(tmp_path):
    stale_path = tmp_path / "old-user" / "missing-project"

    assert _usable_project_path(str(stale_path)) is None


def test_usable_project_path_accepts_existing_directory(tmp_path):
    assert _usable_project_path(str(tmp_path)) == Path(tmp_path)
