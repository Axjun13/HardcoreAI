"""Git repository status, commit, history, and checkout endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.security import get_current_user_id
from db.session import db_session
from services.projects import get_project_or_404
from agent.git_manager import GitManager

router = APIRouter()


# ------------------------------------------------------------------ #
#  Helpers                                                            #
# ------------------------------------------------------------------ #

def _git_manager(project_id: str, user_id: str) -> GitManager:
    """Resolve the project and build a GitManager pointing at the real path."""
    with db_session(user_id) as session:
        project = get_project_or_404(session, project_id, user_id)
        real_path = project.path  # may be None
    return GitManager(project_id, real_path=real_path)


# ------------------------------------------------------------------ #
#  Payloads                                                           #
# ------------------------------------------------------------------ #

class GitCommitPayload(BaseModel):
    message: str


class GitCheckoutPayload(BaseModel):
    ref: str


# ------------------------------------------------------------------ #
#  Endpoints                                                          #
# ------------------------------------------------------------------ #

@router.get("/api/projects/{project_id}/git/info")
def get_git_info(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """Return basic repo metadata: whether a git repo exists, current branch, HEAD hash."""
    try:
        mgr = _git_manager(project_id, user_id)
        is_repo = mgr.is_git_repo()
        if not is_repo:
            return {"is_repo": False, "branch": None, "detached": False, "head_hash": None, "short_hash": None}
        head = mgr.get_current_head()
        return {
            "is_repo": True,
            "branch": head["branch"],
            "detached": head["detached"],
            "head_hash": head["hash"],
            "short_hash": head["short_hash"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/projects/{project_id}/git/status")
def get_git_status(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
) -> list[dict]:
    """Return a list of {path, status} for all changed files (porcelain format)."""
    try:
        mgr = _git_manager(project_id, user_id)
        return mgr.get_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/projects/{project_id}/git/log")
def get_git_log(
    project_id: str,
    n: int = 50,
    user_id: str = Depends(get_current_user_id),
) -> list[dict]:
    """Return a structured commit log for rendering the git graph."""
    try:
        mgr = _git_manager(project_id, user_id)
        return mgr.get_log_graph(n=n)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/projects/{project_id}/git/commit")
def commit_git_changes(
    project_id: str,
    payload: GitCommitPayload,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """Stage all changes and create a commit with the given message."""
    try:
        mgr = _git_manager(project_id, user_id)
        committed = mgr.commit_changes(payload.message)
        return {"success": True, "committed": committed}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/projects/{project_id}/git/checkout")
def checkout_commit(
    project_id: str,
    payload: GitCheckoutPayload,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """Checkout a specific commit ref (puts repo in detached HEAD state for bare hashes)."""
    try:
        mgr = _git_manager(project_id, user_id)
        result = mgr.checkout_commit(payload.ref)
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["error"] or "Checkout failed")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/projects/{project_id}/git/checkout-head")
def checkout_head(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """Return from detached HEAD to the default branch (main/master)."""
    try:
        mgr = _git_manager(project_id, user_id)
        result = mgr.checkout_head()
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["error"] or "Checkout HEAD failed")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class GitBranchPayload(BaseModel):
    name: str

@router.get("/api/projects/{project_id}/git/branches")
def get_branches(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
) -> list[str]:
    """Get a list of local branches."""
    try:
        mgr = _git_manager(project_id, user_id)
        return mgr.get_branches()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/projects/{project_id}/git/branches")
def create_branch(
    project_id: str,
    payload: GitBranchPayload,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """Create a new branch and check it out."""
    try:
        mgr = _git_manager(project_id, user_id)
        result = mgr.create_branch(payload.name)
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["error"] or "Create branch failed")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
