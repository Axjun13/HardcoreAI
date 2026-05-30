"""Agent chat history persistence — one JSON blob per project.

The frontend mirrors its in-memory ``aiMessages`` list here so the conversation
survives reloads and is shared across devices. GET returns the raw history
array (the shape the frontend already consumes); POST replaces it wholesale.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlmodel import select

from core.config import now_utc
from core.security import get_current_user_id
from db.models import ConversationRow
from db.session import db_session
from schemas import ConversationSave
from services.projects import get_project_or_404

router = APIRouter()


@router.get("/api/projects/{project_id}/conversations")
def get_conversation(project_id: str, user_id: str = Depends(get_current_user_id)) -> list[Any]:
    """Return the saved chat history for a project (empty list if none yet)."""
    with db_session(user_id) as session:
        project = get_project_or_404(session, project_id, user_id)
        row = session.exec(
            select(ConversationRow).where(ConversationRow.project_id == project.id)
        ).first()
        return row.history if row else []


@router.post("/api/projects/{project_id}/conversations")
def save_conversation(
    project_id: str,
    payload: ConversationSave,
    user_id: str = Depends(get_current_user_id),
) -> list[Any]:
    """Replace the project's chat history with the supplied list."""
    with db_session(user_id) as session:
        project = get_project_or_404(session, project_id, user_id)
        row = session.exec(
            select(ConversationRow).where(ConversationRow.project_id == project.id)
        ).first()
        if not row:
            row = ConversationRow(project_id=project.id)
        row.history = payload.history
        row.updated_at = now_utc()
        session.add(row)
        session.commit()
        return payload.history


@router.delete("/api/projects/{project_id}/conversations")
def delete_conversation(project_id: str, user_id: str = Depends(get_current_user_id)) -> dict[str, bool]:
    """Clear the project's saved chat history."""
    with db_session(user_id) as session:
        project = get_project_or_404(session, project_id, user_id)
        row = session.exec(
            select(ConversationRow).where(ConversationRow.project_id == project.id)
        ).first()
        if row:
            session.delete(row)
            session.commit()
        return {"ok": True}
