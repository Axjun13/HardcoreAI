"""Board metadata endpoints — read-only surface over the Board Registry."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from boards import device_manager
from boards.registry import registry
from core.security import get_current_user_id
from db.session import db_session
from services.projects import get_project_or_404

router = APIRouter(prefix="/api/boards", tags=["Boards"])


@router.get("")
def list_boards(family: str | None = None) -> list[dict]:
    """List all known boards (curated + imported), optionally filtered by family."""
    boards = registry.list()
    if family:
        boards = [b for b in boards if b.family.lower() == family.lower()]
    return [b.model_dump() for b in boards]


@router.get("/{board_id}")
def get_board(board_id: str) -> dict:
    device = registry.get(board_id)
    if not device:
        raise HTTPException(status_code=404, detail=f"Unknown board: {board_id}")
    return device.model_dump()


@router.post("/refresh")
def refresh_boards(query: str = "STM32") -> dict:
    """Re-import board metadata from PlatformIO. Manual trigger for now —
    not run automatically on every request since it shells out to `pio`."""
    count = registry.refresh(query)
    return {"imported": count}



class SetProjectBoardRequest(BaseModel):
    board_id: str


@router.patch("/projects/{project_id}")
def set_project_board(
    project_id: str,
    payload: SetProjectBoardRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """Change which board a project targets. Validates ownership and that
    the board_id actually exists in the registry before writing."""
    with db_session(user_id) as session:
        # Reuses the same ownership check every other project route uses —
        # raises 404 if this project doesn't belong to user_id.
        get_project_or_404(session, project_id, user_id)

        try:
            device = device_manager.set_project_board(project_id, payload.board_id, session)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    return {"project_id": project_id, "board": device.model_dump()}