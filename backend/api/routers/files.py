"""Code file listing and upsert."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import select

from core.config import now_utc
from core.security import get_current_user_id
from db.models import CodeFileRow
from db.session import db_session
from schemas import CodeFileRead, CodeFileUpsert
from services.projects import get_project_or_404

router = APIRouter()


@router.get("/api/projects/{project_id}/files", response_model=list[CodeFileRead])
def list_files(project_id: str, user_id: str = Depends(get_current_user_id)) -> list[CodeFileRead]:
    with db_session(user_id) as session:
        project = get_project_or_404(session, project_id, user_id)
        files = session.exec(
            select(CodeFileRow)
            .where(CodeFileRow.project_id == project.id)
            .order_by(CodeFileRow.path)
        ).all()
        return [
            CodeFileRead(path=f.path, language=f.language, content=f.content, updated_at=f.updated_at)
            for f in files
        ]


@router.put("/api/projects/{project_id}/files/{file_path:path}", response_model=CodeFileRead)
def upsert_file(project_id: str, file_path: str, payload: CodeFileUpsert, user_id: str = Depends(get_current_user_id)) -> CodeFileRead:
    with db_session(user_id) as session:
        project = get_project_or_404(session, project_id, user_id)
        code_file = session.exec(
            select(CodeFileRow).where(
                CodeFileRow.project_id == project.id, CodeFileRow.path == file_path
            )
        ).first()
        if not code_file:
            code_file = CodeFileRow(project_id=project.id, path=file_path)
        code_file.language = payload.language
        code_file.content = payload.content
        code_file.updated_at = now_utc()
        project.updated_at = now_utc()
        session.add(code_file)
        session.add(project)
        session.commit()
        session.refresh(code_file)
        return CodeFileRead(
            path=code_file.path, language=code_file.language,
            content=code_file.content, updated_at=code_file.updated_at,
        )
