"""Library Manager API — search the registry and manage per-project library installs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import services.library_service as library_service

# from core.security import get_current_user_id
# from services import library_service
# from services.projects import get_project_or_404
# from db.session import db_session

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
) -> list[dict[str, Any]]:
    """Return available libraries from the curated registry, with optional filtering."""
    try:
        return library_service.search_registry(query=search, category=category)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Registry error: {exc}") from exc



@router.get("/api/libraries/categories")
def list_categories() -> list[str]:
    """Return the distinct categories present in the registry."""
    try:
        registry = library_service.load_registry()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Registry error: {exc}") from exc
    categories = sorted({lib.get("category", "") for lib in registry if lib.get("category")})
    return categories


# ---------------------------------------------------------------------------
# Per-project endpoints
# ---------------------------------------------------------------------------


@router.get("/api/projects/{project_id}/libraries")
def get_installed_libraries(project_id: str):
    return library_service.list_installed(project_id)


@router.post("/api/projects/{project_id}/libraries/install")
def install_library(
    project_id: str,
    payload: LibraryInstallRequest,
) -> dict[str, Any]:
    """Install a library into the project. Pass library_id (registry) or git_url (custom)."""


    if not payload.library_id and not payload.git_url:
        raise HTTPException(status_code=422, detail="Provide library_id or git_url.")

    try:
        result = library_service.install_library(
            project_id=project_id,
            library_id=payload.library_id,
            git_url=payload.git_url,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not result["success"]:
        # Client errors (workspace missing, not in registry, pio failed) → 400
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.delete("/api/projects/{project_id}/libraries/{library_id}")
def uninstall_library(
    project_id: str,
    library_id: str,
) -> dict[str, Any]:


    try:
        result = library_service.uninstall_library(project_id=project_id, library_id=library_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result