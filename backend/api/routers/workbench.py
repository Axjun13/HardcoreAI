"""Workbench read/write."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from core.security import get_current_user_id
from db.session import db_session
from schemas import WorkbenchState
from services.projects import get_project_or_404
from services.workbench import read_workbench, write_workbench

router = APIRouter()


@router.get("/api/projects/{project_id}/workbench", response_model=WorkbenchState)
def get_workbench(project_id: str, user_id: str = Depends(get_current_user_id)) -> WorkbenchState:
    with db_session(user_id) as session:
        project = get_project_or_404(session, project_id, user_id)
        return read_workbench(session, project)


@router.put("/api/projects/{project_id}/workbench", response_model=WorkbenchState)
def save_workbench(project_id: str, payload: WorkbenchState, user_id: str = Depends(get_current_user_id)) -> WorkbenchState:
    with db_session(user_id) as session:
        project = get_project_or_404(session, project_id, user_id)
        write_workbench(session, project, payload)
        session.commit()
        session.refresh(project)
        return read_workbench(session, project)
