from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.routers.files import _resolve_work_dir
from services.workspace_search import WorkspaceSearch

router = APIRouter(tags=["Workspace"])


class SearchRequest(BaseModel):
    query: str
    include: str = "*.c,*.h"


@router.post("/api/projects/{project_id}/search")
def workspace_search(project_id: str, req: SearchRequest):

    workspace = _resolve_work_dir(project_id)

    if workspace is None:
        raise HTTPException(
            status_code=404,
            detail="Project has no working directory",
        )

    service = WorkspaceSearch(str(workspace))

    return service.search(
        query=req.query,
        include=req.include,
    )