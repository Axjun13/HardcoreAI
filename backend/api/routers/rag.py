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
    """List all documents in the user's RAG data directory.

    Each document entry includes:
    - ``name``   — filename as stored on disk
    - ``size``   — file size in bytes
    - ``source`` — ``"web"`` for scraped pages, ``"pdf"`` for uploaded PDFs/files
    - ``url``    — original URL (web documents only, empty string otherwise)
    """
    with db_session(user_id) as session:
        get_project_or_404(session, project_id, user_id)
    svc = RAGService(user_id=user_id, project_id=project_id)
    if not svc.config.data_dir.exists():
        return {"documents": []}

    from rag.service import WEB_PREFIX

    documents = []
    for f in svc.config.data_dir.iterdir():
        if not f.is_file():
            continue
        is_web = f.name.startswith(WEB_PREFIX)
        source_url = ""
        if is_web:
            # Read only the first line to extract the stored URL header.
            try:
                with open(f, encoding="utf-8", errors="replace") as fh:
                    first_line = fh.readline().rstrip()
                if first_line.startswith("# source: "):
                    source_url = first_line[len("# source: "):]
            except OSError:
                pass
        documents.append({
            "name": f.name,
            "size": f.stat().st_size,
            "source": "web" if is_web else "pdf",
            "url": source_url,
        })

    return {"documents": documents}


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


# ---------------------------------------------------------------------------
# Web-scraping endpoints
# ---------------------------------------------------------------------------


from pydantic import BaseModel  # noqa: E402 — after router definition for readability


class ScrapeUrlRequest(BaseModel):
    url: str


class WebSearchRequest(BaseModel):
    query: str
    num_results: int = 5


class ScrapeSearchRequest(BaseModel):
    query: str
    num_results: int = 3


@router.post("/api/projects/{project_id}/rag/scrape-url")
async def scrape_url(
    project_id: str,
    payload: ScrapeUrlRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Fetch a URL, extract its text, and ingest it into the RAG index.

    Returns immediately with the ingestion result. The operation is
    *synchronous* (not backgrounded) because the frontend polls for the
    document to appear in the list, and a fast scrape typically finishes
    in under 5 s.
    """
    with db_session(user_id) as session:
        get_project_or_404(session, project_id, user_id)

    if not payload.url.strip():
        raise HTTPException(status_code=400, detail="URL must not be empty")

    svc = RAGService(user_id=user_id, project_id=project_id)
    result = svc.ingest_url(payload.url.strip())

    if result.get("error"):
        raise HTTPException(status_code=422, detail=result["error"])

    return result


@router.post("/api/projects/{project_id}/rag/web-search")
async def web_search(
    project_id: str,
    payload: WebSearchRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Query SearXNG and return result metadata without ingesting anything.

    Useful for previewing results before deciding which pages to ingest.
    """
    with db_session(user_id) as session:
        get_project_or_404(session, project_id, user_id)

    svc = RAGService(user_id=user_id, project_id=project_id)
    results = svc.search_web(payload.query, num_results=payload.num_results)
    return {"results": results}


@router.post("/api/projects/{project_id}/rag/scrape-search")
async def scrape_search(
    project_id: str,
    payload: ScrapeSearchRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
):
    """Search SearXNG, fetch the top N result pages, and ingest them all.

    The first URL is ingested synchronously so the caller gets at least one
    result in the response. The remaining URLs are queued as a background task
    so the HTTP response is not held open for the full fetch-and-index time.
    """
    with db_session(user_id) as session:
        get_project_or_404(session, project_id, user_id)

    svc = RAGService(user_id=user_id, project_id=project_id)
    search_results = svc.search_web(payload.query, num_results=payload.num_results)

    urls = [r["url"] for r in search_results if r.get("url") and not r.get("error")]
    if not urls:
        return {"ingested": [], "search_results": search_results}

    # Ingest the first URL synchronously so the UI can refresh immediately.
    first_result = svc.ingest_url(urls[0])
    ingested = [first_result]

    # Remaining URLs are ingested in the background.
    def _ingest_remaining(remaining_urls: list[str], uid: str, pid: str) -> None:
        _svc = RAGService(user_id=uid, project_id=pid)
        for u in remaining_urls:
            _svc.ingest_url(u)

    if len(urls) > 1:
        background_tasks.add_task(_ingest_remaining, urls[1:], user_id, project_id)

    return {
        "ingested": ingested,
        "search_results": search_results,
        "background_urls": urls[1:],
    }
