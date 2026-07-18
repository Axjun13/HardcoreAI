"""Research/ideation and final README endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import select

from core.config import now_utc
from core.security import get_current_user_id
from db.models import CodeFileRow
from db.session import db_session
from services.catalogue import catalogue_index
from services.component_resolution import (
    install_component_libraries,
    materialize_component_libraries,
    resolve_component_context,
    write_component_manifest,
)
from services.projects import get_project_or_404
from services.research import (
    condense_research_with_deepseek,
    load_research_state,
    new_research_context,
    normalize_research_state,
    recommend_components,
    render_project_readme,
    save_research_state,
    selected_component_ids,
    summarize_with_deepseek_or_fallback,
)
from services.workbench import read_workbench
from boards.registry import registry

router = APIRouter(prefix="/api/projects/{project_id}/research", tags=["Research"])


class IdeateRequest(BaseModel):
    idea: str = ""
    provider: str = "deepseek"
    context_id: str | None = None


class ContextRequest(BaseModel):
    title: str = ""


class SelectRequest(BaseModel):
    selected_component_ids: list[str] = Field(default_factory=list)
    notes: str = ""
    install_libraries: bool = False
    context_id: str | None = None


def _context_or_none(state: dict[str, Any], context_id: str | None) -> dict[str, Any] | None:
    if not context_id:
        return None
    return next(
        (item for item in state.get("contexts") or [] if item.get("id") == context_id),
        None,
    )


def _sync_project_decision(state: dict[str, Any], catalogue: dict) -> None:
    ids = selected_component_ids(state)
    state["selected_components"] = [
        catalogue[component_id].model_dump()
        for component_id in ids
        if component_id in catalogue
    ]
    notes = [
        context.get("decision_notes", "").strip()
        for context in state.get("contexts") or []
        if context.get("decision_notes", "").strip()
    ]
    if notes:
        state["decision_notes"] = "\n".join(dict.fromkeys(notes))


@router.get("")
def get_research_state(project_id: str, user_id: str = Depends(get_current_user_id)) -> dict[str, Any]:
    with db_session(user_id) as session:
        get_project_or_404(session, project_id, user_id)
    return load_research_state(project_id)


@router.post("/contexts")
def create_research_context(
    project_id: str,
    payload: ContextRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    with db_session(user_id) as session:
        get_project_or_404(session, project_id, user_id)
    state = load_research_state(project_id)
    context = new_research_context(title=payload.title)
    state.setdefault("contexts", []).append(context)
    state["active_context_id"] = context["id"]
    save_research_state(project_id, state)
    return {"state": normalize_research_state(state), "context": context}


@router.post("/contexts/{context_id}/activate")
def activate_research_context(
    project_id: str,
    context_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    with db_session(user_id) as session:
        get_project_or_404(session, project_id, user_id)
    state = load_research_state(project_id)
    if not _context_or_none(state, context_id):
        raise HTTPException(status_code=404, detail="Research context not found")
    state["active_context_id"] = context_id
    save_research_state(project_id, state)
    return {"state": state}


@router.post("/ideate")
async def ideate(project_id: str, payload: IdeateRequest, user_id: str = Depends(get_current_user_id)) -> dict[str, Any]:
    with db_session(user_id) as session:
        get_project_or_404(session, project_id, user_id)
        catalogue = catalogue_index(session)

    state = load_research_state(project_id)
    context = _context_or_none(state, payload.context_id)
    if payload.context_id and context is None:
        raise HTTPException(status_code=404, detail="Research context not found")
    if context is None:
        context = new_research_context(title=payload.idea[:48])
        state.setdefault("contexts", []).append(context)
    state["active_context_id"] = context["id"]

    prior_messages = list(context.get("messages") or [])
    combined_goal = " ".join(
        [
            item.get("content", "")
            for item in prior_messages
            if item.get("role") == "user"
        ]
        + [payload.idea]
    )
    recommendations = recommend_components(catalogue=catalogue, goal=combined_goal)
    summary = await summarize_with_deepseek_or_fallback(
        idea=payload.idea,
        recommendations=recommendations,
        provider=payload.provider or "deepseek",
        history=prior_messages,
    )
    state.setdefault("ideas", []).append(payload.idea)
    state["summary"] = summary
    state["condensed_state"] = ""
    state["recommendations"] = recommendations
    context["messages"] = prior_messages + [
        {"role": "user", "content": payload.idea},
        {"role": "assistant", "content": summary},
    ]
    context["summary"] = summary
    context["recommendations"] = recommendations
    context["updated_at"] = datetime.now(timezone.utc).isoformat()
    path = save_research_state(project_id, state)
    return {"state": normalize_research_state(state), "context": context, "path": str(path)}


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
        context = _context_or_none(state, payload.context_id)
        if payload.context_id and context is None:
            raise HTTPException(status_code=404, detail="Research context not found")
        if context is not None:
            context["selected_component_ids"] = [item["id"] for item in selected]
            context["selected_components"] = selected
            context["decision_notes"] = payload.notes
            state["active_context_id"] = context["id"]
        else:
            state["selected_components"] = selected
            state["decision_notes"] = payload.notes
        _sync_project_decision(state, catalogue)
        state["condensed_state"] = ""

        component_context = resolve_component_context(
            catalogue=catalogue,
            workbench=read_workbench(session, project).model_dump(),
            selected_component_ids=selected_component_ids(state),
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
        state = load_research_state(project_id)
        context = resolve_component_context(
            catalogue=catalogue_index(session),
            workbench=read_workbench(session, project).model_dump(),
            selected_component_ids=selected_component_ids(state),
        )
    manifest = write_component_manifest(project_id, context)
    install_results = install_component_libraries(project_id, context) if install_libraries else []
    download_result = (
        materialize_component_libraries(project_id, context)
        if install_libraries and all(result.get("success") for result in install_results)
        else None
    )
    return {
        "context": context,
        "manifest": str(manifest),
        "install_results": install_results,
        "download_result": download_result,
    }


@router.post("/condense")
async def condense_research(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    with db_session(user_id) as session:
        get_project_or_404(session, project_id, user_id)
        catalogue = catalogue_index(session)
    state = load_research_state(project_id)
    _sync_project_decision(state, catalogue)
    condensed, used_deepseek = await condense_research_with_deepseek(state)
    state["condensed_state"] = condensed
    state["condensed_by"] = "deepseek" if used_deepseek else "fallback"
    state["summary"] = condensed
    path = save_research_state(project_id, state)
    return {
        "state": state,
        "condensed_state": condensed,
        "provider_used": state["condensed_by"],
        "path": str(path),
    }


@router.post("/readme")
def generate_readme(project_id: str, user_id: str = Depends(get_current_user_id)) -> dict[str, Any]:
    with db_session(user_id) as session:
        project = get_project_or_404(session, project_id, user_id)
        catalogue = catalogue_index(session)
        component_context = resolve_component_context(
            catalogue=catalogue,
            workbench=read_workbench(session, project).model_dump(),
            selected_component_ids=selected_component_ids(load_research_state(project_id)),
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
