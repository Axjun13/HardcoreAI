"""RAG document management — upload, list, search, delete reference manuals."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
)

from core.security import get_current_user_id
from db.session import db_session
from rag import RAGService
from schemas import RagQueryRequest
from services.projects import get_project_or_404

router = APIRouter()


def _ingest_in_background(user_id: str, project_id: str, temp_dir: str):
    svc = RAGService(user_id=user_id, project_id=project_id)
    # Stage and ingest
    staged = svc.stage_documents(Path(temp_dir).iterdir())
    if staged:
        svc.ingest()
    # Cleanup temp dir after
    shutil.rmtree(temp_dir, ignore_errors=True)


@router.post("/api/projects/{project_id}/rag/upload")
async def upload_documents(
    project_id: str,
    background_tasks: BackgroundTasks,
    documents: list[UploadFile] = File(...),
    user_id: str = Depends(get_current_user_id),
):
    if not documents:
        raise HTTPException(status_code=400, detail="No files uploaded")

    # Verify project exists for user
    with db_session(user_id) as session:
        get_project_or_404(session, project_id, user_id)

    # Save immediately to a temp dir so we don't block the request long
    tmpdir = tempfile.mkdtemp()
    tmp_path = Path(tmpdir)
    for doc in documents:
        if doc.filename:
            file_path = tmp_path / doc.filename
            with open(file_path, "wb") as f:
                shutil.copyfileobj(doc.file, f)

    background_tasks.add_task(_ingest_in_background, user_id, project_id, tmpdir)
    return {"message": "Files uploaded successfully and are being ingested."}


@router.get("/api/projects/{project_id}/rag/documents")
async def list_documents(project_id: str, user_id: str = Depends(get_current_user_id)):
    with db_session(user_id) as session:
        get_project_or_404(session, project_id, user_id)
    svc = RAGService(user_id=user_id, project_id=project_id)
    if not svc.config.data_dir.exists():
        return {"documents": []}
    files = [{"name": f.name, "size": f.stat().st_size} for f in svc.config.data_dir.iterdir() if f.is_file()]
    return {"documents": files}


@router.post("/api/projects/{project_id}/rag/search")
async def search_documents(project_id: str, payload: RagQueryRequest, user_id: str = Depends(get_current_user_id)):
    with db_session(user_id) as session:
        get_project_or_404(session, project_id, user_id)
    svc = RAGService(user_id=user_id, project_id=project_id)
    if not svc.config.db_path.exists():
        return {"context": [], "message": "Knowledge base not initialized"}

    res = svc.query(payload.query, k=payload.k)
    return res


def _rebuild_in_background(user_id: str, project_id: str):
    svc = RAGService(user_id=user_id, project_id=project_id)
    if svc.config.db_path.exists():
        svc.config.db_path.unlink()
    if svc.config.data_dir.exists() and any(svc.config.data_dir.iterdir()):
        svc.ingest()


@router.delete("/api/projects/{project_id}/rag/documents/{filename}")
async def delete_document(
    project_id: str,
    filename: str,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
):
    with db_session(user_id) as session:
        get_project_or_404(session, project_id, user_id)
    svc = RAGService(user_id=user_id, project_id=project_id)
    file_path = svc.config.data_dir / filename
    if not file_path.exists() or not file_path.is_file() or ".." in filename or "/" in filename:
        raise HTTPException(status_code=404, detail="File not found")

    file_path.unlink()
    background_tasks.add_task(_rebuild_in_background, user_id, project_id)
    return {"message": "Document deleted and database rebuild queued"}
