"""Project CRUD."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlmodel import select
import threading
from fastapi import HTTPException
from core.config import now_utc
from core.security import get_current_user_id
from db.models import CodeFileRow, ProjectRow
from db.session import db_session
from schemas import ProjectCreate, ProjectOut, ProjectUpdate
from services.projects import default_files, get_project_or_404, project_out
from agent.git_manager import GitManager

router = APIRouter()


@router.post("/api/pick-folder")
def pick_folder(user_id: str = Depends(get_current_user_id)) -> dict[str, str | None]:
    """Open a native OS folder picker on the server machine and return the chosen path."""
    result: dict[str, str | None] = {"path": None}

    def _show_dialog():
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        result["path"] = filedialog.askdirectory(title="Choose project location") or None
        root.destroy()

    t = threading.Thread(target=_show_dialog)
    t.start()
    t.join()
    return result

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
            path=payload.path,
        )
        session.add(project)
        session.commit()
        session.refresh(project)

        files = default_files(project.name)
        for path, language, content in files:
            session.add(
                CodeFileRow(project_id=project.id, path=path, language=language, content=content)
            )

        # Create backend workspace for Build/Flash
        files_dict = {
            path: {
                "language": language,
                "content": content,
            }
            for path, language, content in files
        }

        git_mgr = GitManager(str(project.id))
        git_mgr.sync_db_to_disk(files_dict)

        if project.path:
            import os
            import subprocess
            for rel_path, _language, content in files:
                full_path = os.path.join(project.path, rel_path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)

            # Auto-initialize git and make the first commit
            try:
                subprocess.run(["git", "init"], cwd=project.path, check=True, capture_output=True)
                subprocess.run(["git", "config", "user.name", "HardcoreAI Copilot"], cwd=project.path, capture_output=True)
                subprocess.run(["git", "config", "user.email", "copilot@hardcore-ai.local"], cwd=project.path, capture_output=True)
                subprocess.run(["git", "add", "."], cwd=project.path, capture_output=True)
                subprocess.run(["git", "commit", "-m", "Initial commit from HardcoreAI template"], cwd=project.path, capture_output=True)
                
                # Fetch the commit hash and save to version_number
                hash_res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=project.path, capture_output=True, text=True)
                if hash_res.returncode == 0:
                    project.version_number = hash_res.stdout.strip()
                    
            except Exception as e:
                print(f"Failed to auto-init git in {project.path}: {e}")

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
