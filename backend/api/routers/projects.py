"""Project CRUD."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlmodel import select

from core.config import now_utc
from core.security import get_current_user_id
from db.models import CodeFileRow, ProjectRow
from db.session import db_session
from schemas import ProjectCreate, ProjectOut, ProjectUpdate
from services.projects import default_files, get_project_or_404, project_out

router = APIRouter()


@router.get("/api/projects", response_model=list[ProjectOut])
def list_projects(user_id: str = Depends(get_current_user_id)) -> list[ProjectOut]:
    with db_session(user_id) as session:
        projects = session.exec(
            select(ProjectRow).where(ProjectRow.user_id == UUID(user_id)).order_by(ProjectRow.updated_at.desc())
        ).all()
        return [project_out(p) for p in projects]


@router.post("/api/projects", response_model=ProjectOut)
def create_project(payload: ProjectCreate, user_id: str = Depends(get_current_user_id)) -> ProjectOut:
    with db_session(user_id) as session:
        project = ProjectRow(
            name=payload.name.strip(),
            description=payload.description.strip(),
            user_id=UUID(user_id),
        )
        session.add(project)
        session.commit()
        session.refresh(project)

        for path, language, content in default_files(project.name):
            session.add(
                CodeFileRow(project_id=project.id, path=path, language=language, content=content)
            )
        session.commit()
        session.refresh(project)
        return project_out(project)


@router.get("/api/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, user_id: str = Depends(get_current_user_id)) -> ProjectOut:
    with db_session(user_id) as session:
        return project_out(get_project_or_404(session, project_id, user_id))


@router.patch("/api/projects/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, payload: ProjectUpdate, user_id: str = Depends(get_current_user_id)) -> ProjectOut:
    with db_session(user_id) as session:
        project = get_project_or_404(session, project_id, user_id)
        if payload.name is not None:
            project.name = payload.name.strip()
        if payload.description is not None:
            project.description = payload.description.strip()
        project.updated_at = now_utc()
        session.add(project)
        session.commit()
        session.refresh(project)
        return project_out(project)


@router.delete("/api/projects/{project_id}")
def delete_project(project_id: str, user_id: str = Depends(get_current_user_id)) -> dict[str, bool]:
    with db_session(user_id) as session:
        project = get_project_or_404(session, project_id, user_id)
        # ON DELETE CASCADE handles code_files / project_components /
        # project_connections, but we delete explicitly for clarity.
        for row in session.exec(
            select(CodeFileRow).where(CodeFileRow.project_id == project.id)
        ).all():
            session.delete(row)
        session.delete(project)
        session.commit()
        return {"deleted": True}
