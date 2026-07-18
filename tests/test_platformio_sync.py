from sqlmodel import Session, SQLModel, create_engine, select

from db.models import CodeFileRow, ProjectRow
from services.hardware import (
    configure_project_environment,
    persist_platformio_content,
    platformio_board_id,
    retarget_platformio_content,
)
from services.projects import default_files


def _project_session(tmp_path):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    project = ProjectRow(name="Board sync", path=str(tmp_path), board_id="bluepill_f103c8")
    session.add(project)
    session.commit()
    session.refresh(project)
    return session, project


def test_retargeting_platformio_preserves_libraries():
    existing = """[env:old]
board = bluepill_f103c8
lib_deps =
    adafruit/Adafruit BME280 Library
"""

    updated = retarget_platformio_content(existing, "esp32dev")

    assert platformio_board_id(updated) == "esp32dev"
    assert "platform = espressif32" in updated
    assert "framework = arduino" in updated
    assert "adafruit/Adafruit BME280 Library" in updated
    assert "stm32cube" not in updated


def test_configure_environment_updates_root_db_and_project_board(tmp_path):
    session, project = _project_session(tmp_path)
    try:
        old_main = next(item for item in default_files(project.name, project.board_id) if item[0] == "src/main.c")
        old_row = CodeFileRow(
            project_id=project.id,
            path=old_main[0],
            language=old_main[1],
            content=old_main[2],
        )
        session.add(old_row)
        (tmp_path / "src").mkdir()
        (tmp_path / old_main[0]).write_text(old_main[2], encoding="utf-8")
        (tmp_path / "platformio.ini").write_text(
            "[env:old]\nboard = bluepill_f103c8\nlib_deps =\n    bblanchon/ArduinoJson\n",
            encoding="utf-8",
        )

        device, content, path = configure_project_environment(
            str(project.id),
            "esp32dev",
            session=session,
            project=project,
        )
        session.commit()

        row = session.exec(
            select(CodeFileRow).where(
                CodeFileRow.project_id == project.id,
                CodeFileRow.path == "platformio.ini",
            )
        ).one()
        session.refresh(project)
        assert device.id == "esp32dev"
        assert project.board_id == "esp32dev"
        assert row.content == content
        assert path.read_text(encoding="utf-8") == content
        assert "bblanchon/ArduinoJson" in content
        assert not (tmp_path / "src/main.c").exists()
        assert (tmp_path / "src/main.cpp").exists()
        entry_rows = session.exec(
            select(CodeFileRow).where(CodeFileRow.project_id == project.id)
        ).all()
        assert "src/main.c" not in {row.path for row in entry_rows}
        assert "src/main.cpp" in {row.path for row in entry_rows}
    finally:
        session.close()


def test_manual_platformio_content_is_mirrored_and_selects_known_board(tmp_path):
    session, project = _project_session(tmp_path)
    try:
        content = "[env:uno]\nplatform = atmelavr\nboard = uno\nframework = arduino\n"
        path = persist_platformio_content(
            str(project.id), content, session=session, project=project
        )
        session.commit()
        session.refresh(project)

        assert project.board_id == "uno"
        assert path == tmp_path / "platformio.ini"
        assert path.read_text(encoding="utf-8") == content
    finally:
        session.close()
