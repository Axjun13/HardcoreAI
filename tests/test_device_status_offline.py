from contextlib import contextmanager

from api.routers import hardware as hardware_router
from schemas import DeviceStatus


def test_device_status_falls_back_when_project_db_is_unavailable(monkeypatch):
    @contextmanager
    def broken_session(user_id):
        raise RuntimeError("db offline")
        yield

    def fake_auto_detect(project_id):
        return DeviceStatus(
            connected=False,
            probe="ST-Link V2",
            detail="No board signal found.",
        )

    monkeypatch.setattr(hardware_router, "db_session", broken_session)
    monkeypatch.setattr(hardware_router.hardware, "auto_detect_board", fake_auto_detect)

    status = hardware_router.device_status(project_id="168", user_id="test-user")

    assert status.connected is False
    assert "Project database unavailable" in status.detail
    assert "generic detection" in status.detail
