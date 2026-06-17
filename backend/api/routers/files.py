"""Code file listing and upsert."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
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

        # Sync disk files to DB if Git is initialized
        try:
            from agent.git_manager import GitManager
            git_mgr = GitManager(project_id)
            if git_mgr.is_git_repo():
                git_mgr.sync_disk_to_db()
        except Exception as e:
            print(f"ERROR: Failed to sync disk to DB: {e}")

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

        # Sync files to local git repo
        try:
            from agent.git_manager import GitManager
            git_mgr = GitManager(project_id)
            rows = session.exec(
                select(CodeFileRow).where(CodeFileRow.project_id == project.id)
            ).all()
            files_dict = {r.path: {"language": r.language, "content": r.content} for r in rows}
            git_mgr.sync_db_to_disk(files_dict)
        except Exception as e:
            # Prevent Git sync errors from failing the save operation
            print(f"ERROR: Failed to sync user edit to git: {e}")

        return CodeFileRead(
            path=code_file.path, language=code_file.language,
            content=code_file.content, updated_at=code_file.updated_at,
        )


@router.delete("/api/projects/{project_id}/files/{file_path:path}")
def delete_file(project_id: str, file_path: str, user_id: str = Depends(get_current_user_id)) -> dict:
    """Delete a code file. Used when the user approves an agent's file deletion."""
    with db_session(user_id) as session:
        project = get_project_or_404(session, project_id, user_id)
        code_file = session.exec(
            select(CodeFileRow).where(
                CodeFileRow.project_id == project.id, CodeFileRow.path == file_path
            )
        ).first()
        if not code_file:
            raise HTTPException(status_code=404, detail=f"No file '{file_path}'.")
        session.delete(code_file)
        project.updated_at = now_utc()
        session.add(project)
        session.commit()

        try:
            from agent.git_manager import GitManager
            git_mgr = GitManager(project_id)
            rows = session.exec(
                select(CodeFileRow).where(CodeFileRow.project_id == project.id)
            ).all()
            files_dict = {r.path: {"language": r.language, "content": r.content} for r in rows}
            git_mgr.sync_db_to_disk(files_dict)
        except Exception as e:
            print(f"ERROR: Failed to sync deletion to git: {e}")

        return {"deleted": file_path}
