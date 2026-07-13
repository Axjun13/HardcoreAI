"""Device Manager — resolves which Device (board) a given project targets.

This is the one function every router/service should call instead of reading
projects.board_id directly or defaulting to a hardcoded board string.
"""

from __future__ import annotations

from sqlmodel import Session

from boards.device import Device
from boards.registry import registry
from db.models import ProjectRow


def for_project(project_id: str, session: Session) -> Device:
    """Resolve the Device for a project. Never raises — falls back to the
    registry default if the project doesn't exist, has no board_id, or the
    stored board_id isn't in the registry (e.g. cache was cleared)."""
    device = _lookup(project_id, session)
    return device or registry.default()


def _lookup(project_id: str, session: Session) -> Device | None:
    if not str(project_id).isdigit():
        return None
    project = session.get(ProjectRow, int(project_id))
    if not project or not project.board_id:
        return None
    return registry.get(project.board_id)


def set_project_board(project_id: str, board_id: str, session: Session) -> Device:
    """Validates board_id exists in the registry, persists it to the project.
    Raises ValueError if board_id is unknown — callers (routers) should turn
    that into an HTTP 400/404 rather than silently accepting a bad id."""
    device = registry.get(board_id)
    if not device:
        raise ValueError(f"Unknown board_id: {board_id}")

    project = session.get(ProjectRow, int(project_id))
    if not project:
        raise ValueError(f"Unknown project_id: {project_id}")

    project.board_id = board_id
    session.add(project)
    session.commit()
    return device