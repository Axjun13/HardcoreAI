"""Git repository status and committing."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.security import get_current_user_id
from db.session import db_session
from services.projects import get_project_or_404
from agent.git_manager import GitManager

router = APIRouter()

class GitCommitPayload(BaseModel):
    message: str

@router.get("/api/projects/{project_id}/git/status")
def get_git_status(
    project_id: str, 
    user_id: str = Depends(get_current_user_id)
) -> list[dict]:
    with db_session(user_id) as session:
        # Validate that project exists and user owns it
        get_project_or_404(session, project_id, user_id)
        
    try:
        git_mgr = GitManager(project_id)
        return git_mgr.get_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/projects/{project_id}/git/commit")
def commit_git_changes(
    project_id: str,
    payload: GitCommitPayload,
    user_id: str = Depends(get_current_user_id)
) -> dict:
    with db_session(user_id) as session:
        # Validate that project exists and user owns it
        get_project_or_404(session, project_id, user_id)
        
    try:
        git_mgr = GitManager(project_id)
        committed = git_mgr.commit_changes(payload.message)
        return {"success": True, "committed": committed}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
