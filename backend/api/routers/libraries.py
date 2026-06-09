"""Library Manager API — search the registry and manage per-project library installs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.security import get_current_user_id
from services import library_service
from services.projects import get_project_or_404
from db.session import db_session

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class LibraryInstallRequest(BaseModel):
    library_id: str | None = None
    git_url: str | None = None


# ---------------------------------------------------------------------------
# Registry endpoints (no project needed)
# ---------------------------------------------------------------------------


@router.get("/api/libraries")
def list_libraries(
    search: str = "",
    category: str = "",
    _: str = Depends(get_current_user_id),
) -> list[dict[str, Any]]:
    """Return available libraries from the curated registry, with optional filtering."""
    return library_service.search_registry(query=search, category=category)


@router.get("/api/libraries/categories")
def list_categories(_: str = Depends(get_current_user_id)) -> list[str]:
    """Return the distinct categories present in the registry."""
    registry = library_service.load_registry()
    categories = sorted({lib.get("category", "") for lib in registry if lib.get("category")})
    return categories


# ---------------------------------------------------------------------------
# Per-project endpoints
# ---------------------------------------------------------------------------


@router.get("/api/projects/{project_id}/libraries")
def get_installed_libraries(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
) -> list[dict[str, Any]]:
    """Return the libraries currently installed in a project (from platformio.ini)."""
    with db_session(user_id) as session:
        get_project_or_404(session, project_id, user_id)  # auth check
    return library_service.list_installed(project_id)


@router.post("/api/projects/{project_id}/libraries/install")
def install_library(
    project_id: str,
    payload: LibraryInstallRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Install a library into the project. Pass library_id (registry) or git_url (custom)."""
    with db_session(user_id) as session:
        get_project_or_404(session, project_id, user_id)

    if not payload.library_id and not payload.git_url:
        raise HTTPException(status_code=422, detail="Provide library_id or git_url.")

    result = library_service.install_library(
        project_id=project_id,
        library_id=payload.library_id,
        git_url=payload.git_url,
    )
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    return result


@router.delete("/api/projects/{project_id}/libraries/{library_id}")
def uninstall_library(
    project_id: str,
    library_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Uninstall a library from the project."""
    with db_session(user_id) as session:
        get_project_or_404(session, project_id, user_id)

    result = library_service.uninstall_library(project_id=project_id, library_id=library_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result
