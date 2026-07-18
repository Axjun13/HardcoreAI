from agent.git_manager import GitManager


def test_db_to_disk_sync_never_deletes_hardcoreai_state(tmp_path, monkeypatch):
    manager = GitManager("unit-test")
    manager.workspace_dir = tmp_path
    monkeypatch.setattr(manager, "ensure_repo", lambda: None)

    internal = tmp_path / ".hardcoreai"
    internal.mkdir()
    research_state = internal / "research_state.json"
    component_context = internal / "component_context.json"
    research_state.write_text('{"stage":"component_selection"}', encoding="utf-8")
    component_context.write_text('{"components":[]}', encoding="utf-8")
    unmanaged = tmp_path / "obsolete.txt"
    unmanaged.write_text("old", encoding="utf-8")

    manager.sync_db_to_disk({
        "plan.md": {"language": "markdown", "content": "# Plan"},
    })

    assert research_state.read_text(encoding="utf-8") == '{"stage":"component_selection"}'
    assert component_context.exists()
    assert not unmanaged.exists()
    assert (tmp_path / "plan.md").exists()


def test_db_to_disk_sync_updates_root_platformio_ini(tmp_path, monkeypatch):
    manager = GitManager("unit-test")
    manager.workspace_dir = tmp_path
    monkeypatch.setattr(manager, "ensure_repo", lambda: None)
    root_ini = tmp_path / "platformio.ini"
    root_ini.write_text("[env:old]\nboard = bluepill_f103c8\n", encoding="utf-8")

    expected = "[env:esp32dev]\nplatform = espressif32\nboard = esp32dev\nframework = arduino\n"
    manager.sync_db_to_disk({
        "platformio.ini": {"language": "ini", "content": expected},
    })

    assert root_ini.read_text(encoding="utf-8") == expected
