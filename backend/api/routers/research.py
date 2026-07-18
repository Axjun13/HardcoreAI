"""Research/ideation and final README endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel import select

from core.config import now_utc
from core.security import get_current_user_id
from db.models import CodeFileRow
from db.session import db_session
from services.catalogue import catalogue_index
from services.component_resolution import (
    install_component_libraries,
    resolve_component_context,
    write_component_manifest,
)
from services.projects import get_project_or_404
from services.research import (
    load_research_state,
    recommend_components,
    render_project_readme,
    save_research_state,
    summarize_with_deepseek_or_fallback,
)
from services.workbench import read_workbench
from boards.registry import registry

router = APIRouter(prefix="/api/projects/{project_id}/research", tags=["Research"])


class IdeateRequest(BaseModel):
    idea: str = ""
    provider: str = "deepseek"


class SelectRequest(BaseModel):
    selected_component_ids: list[str] = Field(default_factory=list)
    notes: str = ""
    install_libraries: bool = False


@router.get("")
def get_research_state(project_id: str, user_id: str = Depends(get_current_user_id)) -> dict[str, Any]:
    with db_session(user_id) as session:
        get_project_or_404(session, project_id, user_id)
    return load_research_state(project_id)


@router.post("/ideate")
async def ideate(project_id: str, payload: IdeateRequest, user_id: str = Depends(get_current_user_id)) -> dict[str, Any]:
    with db_session(user_id) as session:
        get_project_or_404(session, project_id, user_id)
        catalogue = catalogue_index(session)

    recommendations = recommend_components(catalogue=catalogue, goal=payload.idea)
    summary = await summarize_with_deepseek_or_fallback(
        idea=payload.idea,
        recommendations=recommendations,
        provider=payload.provider or "deepseek",
    )
    state = load_research_state(project_id)
    state.setdefault("ideas", []).append(payload.idea)
    state["summary"] = summary
    state["recommendations"] = recommendations
    path = save_research_state(project_id, state)
    return {"state": state, "path": str(path)}


@router.post("/select")
def select_components(project_id: str, payload: SelectRequest, user_id: str = Depends(get_current_user_id)) -> dict[str, Any]:
    with db_session(user_id) as session:
        project = get_project_or_404(session, project_id, user_id)
        catalogue = catalogue_index(session)
        state = load_research_state(project_id)
        selected = [
            catalogue[cid].model_dump()
            for cid in payload.selected_component_ids
            if cid in catalogue
        ]
        state["selected_components"] = selected
        state["decision_notes"] = payload.notes

        component_context = resolve_component_context(
            catalogue=catalogue,
            workbench=read_workbench(session, project).model_dump(),
        )

    manifest = write_component_manifest(project_id, component_context)
    install_results = (
        install_component_libraries(project_id, component_context)
        if payload.install_libraries else []
    )
    path = save_research_state(project_id, state)
    return {
        "state": state,
        "research_path": str(path),
        "component_manifest": str(manifest),
        "install_results": install_results,
    }


@router.post("/phase3")
def prepare_phase3(
    project_id: str,
    install_libraries: bool = True,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    with db_session(user_id) as session:
        project = get_project_or_404(session, project_id, user_id)
        context = resolve_component_context(
            catalogue=catalogue_index(session),
            workbench=read_workbench(session, project).model_dump(),
        )
    manifest = write_component_manifest(project_id, context)
    install_results = install_component_libraries(project_id, context) if install_libraries else []
    return {"context": context, "manifest": str(manifest), "install_results": install_results}


@router.post("/readme")
def generate_readme(project_id: str, user_id: str = Depends(get_current_user_id)) -> dict[str, Any]:
    with db_session(user_id) as session:
        project = get_project_or_404(session, project_id, user_id)
        catalogue = catalogue_index(session)
        component_context = resolve_component_context(
            catalogue=catalogue,
            workbench=read_workbench(session, project).model_dump(),
        )
        board = registry.get(project.board_id) or registry.default()
        content = render_project_readme(
            project_name=project.name,
            board=board.model_dump(),
            research_state=load_research_state(project_id),
            component_context=component_context,
        )
        row = session.exec(
            select(CodeFileRow).where(
                CodeFileRow.project_id == project.id,
                CodeFileRow.path == "README.md",
            )
        ).first()
        if not row:
            row = CodeFileRow(project_id=project.id, path="README.md", language="markdown")
        row.content = content
        row.updated_at = now_utc()
        project.updated_at = now_utc()
        session.add(row)
        session.add(project)
        session.commit()

    write_component_manifest(project_id, component_context)
    try:
        from agent.git_manager import GitManager
        with db_session(user_id) as session:
            project = get_project_or_404(session, project_id, user_id)
            rows = session.exec(select(CodeFileRow).where(CodeFileRow.project_id == project.id)).all()
            files_dict = {r.path: {"language": r.language, "content": r.content} for r in rows}
        GitManager(project_id).sync_db_to_disk(files_dict)
    except Exception as exc:
        return {"path": "README.md", "content": content, "sync_warning": str(exc)}
    return {"path": "README.md", "content": content}
