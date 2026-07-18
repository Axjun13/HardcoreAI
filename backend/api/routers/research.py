"""Research/ideation and final README endpoints."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import select

import llm
from core.config import now_utc
from core.security import get_current_user_id
from db.models import CodeFileRow
from db.session import db_session
from services.catalogue import catalogue_index
from services.component_discovery import (
    enrich_candidates_from_web,
    propose_component_candidates,
    upsert_discovered_components,
)
from services.component_resolution import (
    install_component_libraries,
    materialize_component_libraries,
    resolve_component_context,
    write_component_manifest,
)
from services.projects import get_project_or_404
from services.hardware import workspace_dir
from services.research import (
    condense_research_with_deepseek,
    load_research_state,
    new_research_context,
    normalize_research_state,
    recommend_components,
    research_goal_text,
    research_fallback_response,
    render_project_readme,
    render_plan_markdown,
    render_components_markdown,
    render_verification_markdown,
    render_final_markdown,
    save_research_state,
    selected_target_board_id,
    selected_component_ids,
    summarize_with_deepseek_or_fallback,
    stream_research_response,
)
from services.integration_verification import (
    build_pin_configuration,
    design_pin_assignments,
    persist_component_verification,
    phase3_todos,
    render_configuration,
    render_connection_diagram,
    render_phase3_verification,
    render_pin_diagram,
    set_todo_status,
    verify_component_online,
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


class AdvanceRequest(BaseModel):
    action: str = "confirm"
    message: str = ""
    selected_component_ids: list[str] = Field(default_factory=list)
    notes: str = ""
    provider: str = "deepseek"
    expected_stage: str | None = None


def _upsert_markdown(session, project, path: str, content: str, language: str = "markdown") -> None:
    row = session.exec(
        select(CodeFileRow).where(CodeFileRow.project_id == project.id, CodeFileRow.path == path)
    ).first()
    if not row:
        row = CodeFileRow(project_id=project.id, path=path, language=language)
    row.content = content
    row.language = language
    row.updated_at = now_utc()
    session.add(row)


def _apply_research_target_board(
    session,
    project,
    selected: list[dict[str, Any]],
    state: dict[str, Any],
):
    """Select from the full registry and align the project/build target."""
    from services.board_selection import select_board_for_plan

    decision = select_board_for_plan(
        plan=research_goal_text(state),
        components=selected,
        current_board_id=project.board_id,
    )
    state["board_selection"] = decision
    board_id = (
        decision.get("selected_board_id")
        or selected_target_board_id(selected)
        or project.board_id
    )
    device = registry.get(board_id)
    if not device:
        return registry.get(project.board_id) or registry.default()

    # Always reconcile the real root file, even when the selected board did
    # not change. This repairs projects created before platformio.ini became a
    # normal DB/disk-mirrored file and prevents a stale STM32 config winning.
    from services.hardware import configure_project_environment

    configured, _content, _path = configure_project_environment(
        str(project.id),
        device.id,
        session=session,
        project=project,
    )
    return configured


async def _incorporate_review_edit(plan: str, revision: str, provider: str) -> str:
    """Rewrite the plan around a review edit, with a deterministic fallback."""
    try:
        result = await llm.complete(provider or "deepseek", [
            {
                "role": "system",
                "content": (
                    "Update the existing embedded-system implementation plan to incorporate the user's review edit. "
                    "Return the complete revised Markdown plan only. Preserve valid requirements, make the requested "
                    "change concrete, and do not claim work has been executed."
                ),
            },
            {"role": "user", "content": f"EXISTING PLAN:\n{plan}\n\nREVIEW EDIT:\n{revision}"},
        ])
        clean = result.strip()
        if clean.startswith("```"):
            clean = clean.removeprefix("```markdown").removeprefix("```").removesuffix("```").strip()
        if clean:
            return clean + "\n"
    except Exception:
        pass
    return plan.rstrip() + f"\n\n## Incorporated Review Edit\n\n- {revision}\n"


def _sync_project_files(project_id: str, user_id: str) -> None:
    try:
        from agent.git_manager import GitManager
        with db_session(user_id) as session:
            rows = session.exec(select(CodeFileRow).where(CodeFileRow.project_id == int(project_id))).all()
            files = {row.path: {"language": row.language, "content": row.content} for row in rows}
        GitManager(project_id).sync_db_to_disk(files)
    except Exception:
        # The DB remains authoritative; a later project load will retry the sync.
        pass


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
        catalogue[component_id].model_dump(mode="json")
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
    elif state.get("contexts") is not None:
        state["decision_notes"] = ""


async def _discover_research_components(
    *, state: dict[str, Any], goal: str, provider: str
) -> list[str]:
    """Discover and persist exact candidate parts without making Research fail.

    Search/provider failures are recorded in state and catalogue ranking still
    falls back to the locally available rows.
    """
    try:
        with db_session() as session:
            existing_names = [item.name for item in catalogue_index(session).values()]
        candidates = await propose_component_candidates(
            goal=goal,
            provider=provider or "deepseek",
            existing_names=existing_names,
        )
        enriched = await asyncio.to_thread(enrich_candidates_from_web, candidates)
        with db_session() as session:
            slugs = upsert_discovered_components(session, enriched)
        state["component_discovery"] = {
            "status": "completed",
            "component_ids": slugs,
            "searched_at": datetime.now(timezone.utc).isoformat(),
        }
        return slugs
    except Exception as exc:
        state["component_discovery"] = {
            "status": "degraded",
            "message": str(exc)[:400],
            "searched_at": datetime.now(timezone.utc).isoformat(),
        }
        return []


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


@router.delete("/contexts/{context_id}")
def delete_research_context(
    project_id: str,
    context_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Delete one idea/chat and repair the active/project decision state."""
    with db_session(user_id) as session:
        get_project_or_404(session, project_id, user_id)
        catalogue = catalogue_index(session)
    state = load_research_state(project_id)
    contexts = state.get("contexts") or []
    if not any(context.get("id") == context_id for context in contexts):
        raise HTTPException(status_code=404, detail="Research context not found")
    state["contexts"] = [context for context in contexts if context.get("id") != context_id]
    if state.get("active_context_id") == context_id:
        state["active_context_id"] = state["contexts"][0]["id"] if state["contexts"] else None
    active = _context_or_none(state, state.get("active_context_id"))
    state["summary"] = active.get("summary", "") if active else ""
    state["recommendations"] = active.get("recommendations", []) if active else []
    if not state["contexts"]:
        state["ideas"] = []
    _sync_project_decision(state, catalogue)
    save_research_state(project_id, state)
    return {"state": normalize_research_state(state), "deleted_context_id": context_id}


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
    combined_goal = research_goal_text(state, payload.idea)
    preferred_ids: list[str] = []
    if state.get("stage") == "component_selection":
        preferred_ids = await _discover_research_components(
            state=state,
            goal=combined_goal,
            provider=payload.provider,
        )
        with db_session(user_id) as session:
            catalogue = catalogue_index(session)
    recommendations = recommend_components(
        catalogue=catalogue,
        goal=combined_goal,
        preferred_ids=preferred_ids,
    )
    summary = await summarize_with_deepseek_or_fallback(
        idea=payload.idea,
        recommendations=recommendations,
        provider=payload.provider or "deepseek",
        history=prior_messages,
        stage=state.get("stage", "ideation"),
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


def _research_sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event)}\n\n"


@router.post("/ideate/stream")
async def ideate_stream(
    project_id: str,
    payload: IdeateRequest,
    user_id: str = Depends(get_current_user_id),
) -> StreamingResponse:
    """Stream a phase-aware research conversation and persist it when complete."""
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
    combined_goal = research_goal_text(state, payload.idea)
    recommendations = recommend_components(catalogue=catalogue, goal=combined_goal)
    stage = state.get("stage", "ideation")

    async def events():
        status = "Exploring your idea" if stage == "ideation" else "Comparing the component tradeoffs"
        yield _research_sse({"type": "status", "text": status})
        current_recommendations = recommendations
        if stage == "component_selection":
            preferred_ids = await _discover_research_components(
                state=state,
                goal=combined_goal,
                provider=payload.provider,
            )
            with db_session(user_id) as discovery_session:
                refreshed_catalogue = catalogue_index(discovery_session)
            current_recommendations = recommend_components(
                catalogue=refreshed_catalogue,
                goal=combined_goal,
                preferred_ids=preferred_ids,
            )
        chunks: list[str] = []
        degraded = False
        try:
            async for chunk in stream_research_response(
                idea=payload.idea,
                recommendations=current_recommendations,
                provider=payload.provider or "deepseek",
                history=prior_messages,
                stage=stage,
            ):
                chunks.append(chunk)
                yield _research_sse({"type": "delta", "text": chunk})
        except Exception:
            if chunks:
                yield _research_sse({"type": "error", "message": "The model connection was interrupted mid-response. Please retry."})
                return
            degraded = True
            fallback = research_fallback_response(
                idea=payload.idea,
                recommendations=current_recommendations,
                history=prior_messages,
                stage=stage,
            )
            chunks.append(fallback)
            yield _research_sse({
                "type": "degraded",
                "message": f"{payload.provider or 'The selected provider'} is temporarily unavailable. Showing a local continuity response.",
            })
            yield _research_sse({"type": "delta", "text": fallback})

        summary = "".join(chunks).strip()
        if not summary:
            yield _research_sse({"type": "error", "message": "The research agent returned an empty response."})
            return

        state.setdefault("ideas", []).append(payload.idea)
        state["summary"] = summary
        state["condensed_state"] = ""
        state["recommendations"] = current_recommendations
        context["messages"] = prior_messages + [
            {"role": "user", "content": payload.idea},
            {"role": "assistant", "content": summary},
        ]
        context["summary"] = summary
        context["recommendations"] = current_recommendations
        context["updated_at"] = datetime.now(timezone.utc).isoformat()
        path = save_research_state(project_id, state)
        yield _research_sse({
            "type": "done",
            "state": normalize_research_state(state),
            "context": context,
            "path": str(path),
            "degraded": degraded,
        })

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/select")
def select_components(project_id: str, payload: SelectRequest, user_id: str = Depends(get_current_user_id)) -> dict[str, Any]:
    with db_session(user_id) as session:
        project = get_project_or_404(session, project_id, user_id)
        catalogue = catalogue_index(session)
        state = load_research_state(project_id)
        selected = [
            catalogue[cid].model_dump(mode="json")
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


@router.post("/verify/stream")
async def stream_phase3_verification(
    project_id: str,
    payload: AdvanceRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
) -> StreamingResponse:
    """Verify selected components sequentially and stream the persisted TODO state."""
    state = load_research_state(project_id)
    stage = state.get("stage", "ideation")
    if stage not in {"component_selection", "verification"}:
        raise HTTPException(status_code=409, detail=f"Phase 3 cannot start from {stage}.")
    selected_ids = list(dict.fromkeys(payload.selected_component_ids or selected_component_ids(state)))

    with db_session(user_id) as session:
        project = get_project_or_404(session, project_id, user_id)
        catalogue = catalogue_index(session)
        selected = [catalogue[cid].model_dump(mode="json") for cid in selected_ids if cid in catalogue]
        if not selected:
            raise HTTPException(status_code=422, detail="Select at least one component before starting Phase 3.")
        board = _apply_research_target_board(session, project, selected, state)
        state["target_board_id"] = board.id
        session.commit()
        project_name = project.name
        workbench = read_workbench(session, project).model_dump()

    async def events():
        state["stage"] = "verification"
        state["selected_components"] = selected
        state["decision_notes"] = payload.notes.strip()
        state["component_verifications"] = []
        state["pin_assignments"] = []
        state["todos"] = phase3_todos(selected)
        board_decision = state.get("board_selection") or {}
        selected_decision = board_decision.get("selected") or {}
        selection_reasons = selected_decision.get("reasons") or []
        set_todo_status(
            state,
            "select:board",
            "completed",
            f"Selected {board.label} ({board.id}) from {board_decision.get('registry_size', 1)} registered targets"
            + (f": {selection_reasons[0]}" if selection_reasons else ""),
        )
        active = _context_or_none(state, state.get("active_context_id"))
        if active is not None:
            active["selected_component_ids"] = selected_ids
            active["selected_components"] = selected
            active["decision_notes"] = payload.notes.strip()
        state["components_markdown"] = render_components_markdown(state)
        save_research_state(project_id, state)
        yield _research_sse({"type": "state", "state": normalize_research_state(state)})

        verifications: list[dict[str, Any]] = []
        run_started_at = asyncio.get_running_loop().time()
        for index, component in enumerate(selected):
            todo_id = f"verify:{component['id']}"
            set_todo_status(state, todo_id, "in_progress", "Searching for authoritative datasheet evidence")
            state["verification_activity"] = {
                "status": "running",
                "component": component.get("name"),
                "component_id": component.get("id"),
                "index": index + 1,
                "total": len(selected),
                "phase": "starting",
                "title": f"Starting {component.get('name')} verification",
                "detail": "Preparing the sequential datasheet and catalogue cross-check.",
                "progress_percent": round(index / len(selected) * 78),
            }
            save_research_state(project_id, state)
            yield _research_sse({
                "type": "activity",
                "component": component.get("name"),
                "index": index + 1,
                "total": len(selected),
                "activity": state["verification_activity"],
                "state": normalize_research_state(state),
            })

            activity_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

            async def report_activity(activity: dict[str, Any]) -> None:
                await activity_queue.put(activity)

            verification_task = asyncio.create_task(
                verify_component_online(component, payload.provider, report_activity)
            )
            try:
                while not verification_task.done() or not activity_queue.empty():
                    try:
                        activity = await asyncio.wait_for(activity_queue.get(), timeout=1.25)
                    except asyncio.TimeoutError:
                        elapsed = int(asyncio.get_running_loop().time() - run_started_at)
                        yield _research_sse({
                            "type": "heartbeat",
                            "component": component.get("name"),
                            "index": index + 1,
                            "total": len(selected),
                            "elapsed_seconds": elapsed,
                        })
                        continue
                    step = max(1, min(int(activity.get("step") or 1), 5))
                    elapsed = int(asyncio.get_running_loop().time() - run_started_at)
                    progress_percent = round(((index + step / 6) / len(selected)) * 78)
                    enriched_activity = {
                        **activity,
                        "status": "running",
                        "component": component.get("name"),
                        "component_id": component.get("id"),
                        "index": index + 1,
                        "total": len(selected),
                        "elapsed_seconds": elapsed,
                        "progress_percent": progress_percent,
                    }
                    state["verification_activity"] = enriched_activity
                    set_todo_status(state, todo_id, "in_progress", str(activity.get("detail") or ""))
                    save_research_state(project_id, state)
                    yield _research_sse({
                        "type": "activity",
                        "activity": enriched_activity,
                        "state": normalize_research_state(state),
                    })
                verification = await verification_task
            except Exception as exc:
                fallback_pins = [
                    {
                        "name": str(pin.get("name") or pin.get("label") or ""),
                        "label": str(pin.get("label") or pin.get("name") or ""),
                        "role": str(pin.get("role") or "gpio"),
                        "voltage": pin.get("voltage") if isinstance(pin.get("voltage"), (int, float)) else None,
                        "capabilities": pin.get("capabilities"),
                    }
                    for pin in (component.get("pins") or [])
                    if isinstance(pin, dict) and (pin.get("name") or pin.get("label"))
                ]
                error_message = f"{type(exc).__name__}: {str(exc)[:240]}"
                verification = {
                    "component_id": component.get("id"),
                    "name": component.get("name"),
                    "datasheet_url": component.get("datasheet_url"),
                    "source_urls": component.get("verification_sources") or [],
                    "pins": fallback_pins,
                    "pin_count": len(fallback_pins),
                    "protocols": component.get("protocols") or [],
                    "operating_voltage": "Unresolved",
                    "configuration_notes": [],
                    "warnings": [f"Component verification failed safely and the catalogue record was retained: {error_message}"],
                    "verified": False,
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                }
                state["verification_activity"] = {
                    "status": "warning",
                    "component": component.get("name"),
                    "component_id": component.get("id"),
                    "index": index + 1,
                    "total": len(selected),
                    "phase": "component_error",
                    "title": "Component check completed with a warning",
                    "detail": error_message,
                    "progress_percent": round(((index + 1) / len(selected)) * 78),
                }
                save_research_state(project_id, state)
                yield _research_sse({
                    "type": "component_warning",
                    "message": error_message,
                    "activity": state["verification_activity"],
                    "state": normalize_research_state(state),
                })
            finally:
                if not verification_task.done():
                    verification_task.cancel()
            try:
                with db_session(user_id) as verification_session:
                    persist_component_verification(verification_session, verification)
            except Exception as exc:
                db_warning = f"Catalogue update could not be saved: {type(exc).__name__}: {str(exc)[:200]}"
                verification.setdefault("warnings", []).append(db_warning)
                state["verification_activity"] = {
                    "status": "warning",
                    "component": component.get("name"),
                    "component_id": component.get("id"),
                    "index": index + 1,
                    "total": len(selected),
                    "phase": "database_warning",
                    "title": "Continuing without a catalogue update",
                    "detail": db_warning,
                    "progress_percent": round(((index + 1) / len(selected)) * 78),
                }
                save_research_state(project_id, state)
                yield _research_sse({
                    "type": "component_warning",
                    "message": db_warning,
                    "activity": state["verification_activity"],
                    "state": normalize_research_state(state),
                })
            verifications.append(verification)
            state["component_verifications"] = verifications
            detail = (
                f"{verification['pin_count']} pins; {', '.join(verification['protocols']) or 'protocol unresolved'}"
            )
            set_todo_status(state, todo_id, "completed" if verification.get("verified") else "warning", detail)
            state["verification_activity"] = {
                "status": "component_done",
                "component": verification.get("name"),
                "component_id": verification.get("component_id"),
                "index": index + 1,
                "total": len(selected),
                "phase": "component_done",
                "title": f"{verification.get('name')} checked",
                "detail": detail,
                "progress_percent": round(((index + 1) / len(selected)) * 78),
            }
            save_research_state(project_id, state)
            yield _research_sse({
                "type": "component_done",
                "verification": verification,
                "state": normalize_research_state(state),
            })

        set_todo_status(state, "design:pin-map", "in_progress")
        state["verification_activity"] = {
            "status": "running",
            "phase": "pin_design",
            "title": "Designing the board pin map",
            "detail": "Matching component signals to board capabilities and checking for conflicts.",
            "progress_percent": 84,
        }
        save_research_state(project_id, state)
        yield _research_sse({"type": "activity", "activity": state["verification_activity"], "state": normalize_research_state(state)})
        assignments = design_pin_assignments(board.model_dump(), verifications)
        state["pin_assignments"] = assignments
        unresolved = sum(1 for item in assignments if item.get("status") != "resolved")
        set_todo_status(state, "design:pin-map", "completed" if unresolved == 0 else "warning", f"{len(assignments)} assignments; {unresolved} unresolved")

        state["verification_activity"] = {
            "status": "running",
            "phase": "diagrams",
            "title": "Generating integration diagrams",
            "detail": "Rendering the pin table and connection graph from the resolved assignments.",
            "progress_percent": 91,
        }
        save_research_state(project_id, state)
        yield _research_sse({"type": "activity", "activity": state["verification_activity"], "state": normalize_research_state(state)})
        state["pin_diagram_markdown"] = render_pin_diagram(board.model_dump(), assignments)
        state["connection_diagram_markdown"] = render_connection_diagram(board.model_dump(), assignments)
        set_todo_status(state, "design:diagrams", "completed")
        state["pin_configuration"] = build_pin_configuration(board.model_dump(), assignments, verifications)
        state["configuration_markdown"] = render_configuration(board.model_dump(), assignments, verifications)
        set_todo_status(state, "configure:pins", "completed")
        state["verification_activity"] = {
            "status": "running",
            "phase": "artifacts",
            "title": "Saving the final integration package",
            "detail": "Writing verification, diagrams, pin configuration, and final-review artifacts.",
            "progress_percent": 97,
        }
        save_research_state(project_id, state)
        yield _research_sse({"type": "activity", "activity": state["verification_activity"], "state": normalize_research_state(state)})
        set_todo_status(state, "review:approval", "in_progress", "Waiting for final review")
        state["verification_markdown"] = render_phase3_verification(project_name, board.model_dump(), verifications, assignments)
        state["final_markdown"] = render_final_markdown(project_name, state)

        with db_session(user_id) as artifact_session:
            artifact_project = get_project_or_404(artifact_session, project_id, user_id)
            refreshed_catalogue = catalogue_index(artifact_session)
            refreshed_selected = [
                refreshed_catalogue[cid].model_dump(mode="json")
                for cid in selected_ids
                if cid in refreshed_catalogue
            ]
            state["selected_components"] = refreshed_selected
            if active is not None:
                active["selected_components"] = refreshed_selected
            state["components_markdown"] = render_components_markdown(state)
            state["final_markdown"] = render_final_markdown(project_name, state)
            component_context = resolve_component_context(
                catalogue=refreshed_catalogue,
                workbench=workbench,
                selected_component_ids=selected_ids,
            )
            for path, content in {
                "components.md": state["components_markdown"],
                "verification.md": state["verification_markdown"],
                "pin-diagram.md": state["pin_diagram_markdown"],
                "connection-diagram.md": state["connection_diagram_markdown"],
                "configuration.md": state["configuration_markdown"],
                "final-review.md": state["final_markdown"],
            }.items():
                _upsert_markdown(artifact_session, artifact_project, path, content)
            _upsert_markdown(
                artifact_session,
                artifact_project,
                "pin-config.json",
                json.dumps(state["pin_configuration"], indent=2) + "\n",
                language="json",
            )
            artifact_project.updated_at = now_utc()
            artifact_session.add(artifact_project)
            artifact_session.commit()

        write_component_manifest(project_id, {**component_context, "pin_assignments": assignments, "verifications": verifications})
        state["verification_activity"] = {
            "status": "completed",
            "phase": "completed",
            "title": "Phase 3 verification complete",
            "detail": "The final plan, diagrams, and pin configuration are ready for review.",
            "progress_percent": 100,
        }
        state["stage"] = "final_review"
        save_research_state(project_id, state)
        background_tasks.add_task(_sync_project_files, project_id, user_id)
        yield _research_sse({
            "type": "done",
            "state": normalize_research_state(state),
            "artifacts": ["components.md", "verification.md", "pin-diagram.md", "connection-diagram.md", "configuration.md", "pin-config.json", "final-review.md"],
        })

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.post("/advance")
async def advance_research_workflow(
    project_id: str,
    payload: AdvanceRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Advance the confirmed idea through plan, parts, verification, and Act mode."""
    state = load_research_state(project_id)
    stage = state.get("stage", "ideation")
    action = payload.action.strip().lower()
    expected_stage = (payload.expected_stage or "").strip().lower()
    recovered_stage = False
    if expected_stage and expected_stage != stage:
        # Older builds could delete research_state.json during DB→disk sync.
        # A client visibly sitting in component selection still has the exact
        # selected ids required to recover this one transition. Do not silently
        # replay ideation and generate plan.md a second time.
        if (
            stage == "ideation"
            and expected_stage == "component_selection"
            and payload.selected_component_ids
        ):
            stage = "component_selection"
            state["stage"] = stage
            recovered_stage = True
        else:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Workflow changed from {expected_stage or 'unknown'} to {stage}. "
                    "The latest state has been reloaded; review it and confirm again."
                ),
            )
    artifacts: list[str] = []
    install_results: list[dict[str, Any]] = []
    discovered_ids: list[str] = []
    manifest_context: dict[str, Any] | None = None
    goal = research_goal_text(state)
    if stage == "ideation" and action == "confirm" and goal.strip():
        discovered_ids = await _discover_research_components(
            state=state,
            goal=goal,
            provider=payload.provider,
        )

    revised_plan: str | None = None
    if action == "revise":
        revision = payload.message.strip()
        if not revision:
            raise HTTPException(status_code=422, detail="Describe the requested edit.")
        if stage != "final_review":
            raise HTTPException(status_code=409, detail="Plan edits are accepted during Final Review.")
        revised_plan = await _incorporate_review_edit(
            state.get("plan_markdown") or "# Implementation Plan\n",
            revision,
            payload.provider,
        )

    with db_session(user_id) as session:
        project = get_project_or_404(session, project_id, user_id)
        catalogue = catalogue_index(session)
        board = registry.get(project.board_id) or registry.default()

        if action == "revise":
            state["plan_markdown"] = revised_plan or state.get("plan_markdown") or render_plan_markdown(project.name, state)
            state["review_revision"] = int(state.get("review_revision") or 0) + 1
            set_todo_status(state, "review:approval", "in_progress", f"Review round {state['review_revision'] + 1} requested")
            state["final_markdown"] = render_final_markdown(project.name, state)
            state["stage"] = "final_review"
            _upsert_markdown(session, project, "plan.md", state["plan_markdown"])
            _upsert_markdown(session, project, "final-review.md", state["final_markdown"])
            artifacts.extend(["plan.md", "final-review.md"])
        elif stage == "ideation":
            recommendations = recommend_components(
                catalogue=catalogue,
                goal=goal,
                preferred_ids=discovered_ids,
            )
            state["recommendations"] = recommendations
            active = _context_or_none(state, state.get("active_context_id"))
            if active is not None:
                active["recommendations"] = recommendations
            state["plan_markdown"] = render_plan_markdown(project.name, state)
            state["stage"] = "component_selection"
            _upsert_markdown(session, project, "plan.md", state["plan_markdown"])
            artifacts.append("plan.md")
        elif stage == "component_selection":
            if recovered_stage and not state.get("plan_markdown"):
                plan_row = session.exec(
                    select(CodeFileRow).where(
                        CodeFileRow.project_id == project.id,
                        CodeFileRow.path == "plan.md",
                    )
                ).first()
                state["plan_markdown"] = (
                    plan_row.content if plan_row else render_plan_markdown(project.name, state)
                )
            selected = [catalogue[cid].model_dump(mode="json") for cid in payload.selected_component_ids if cid in catalogue]
            if not selected:
                raise HTTPException(status_code=422, detail="Select at least one component before confirming.")
            board = _apply_research_target_board(session, project, selected, state)
            state["target_board_id"] = board.id
            state["selected_components"] = selected
            state["decision_notes"] = payload.notes.strip()
            active = _context_or_none(state, state.get("active_context_id"))
            if active is not None:
                active["selected_component_ids"] = [item["id"] for item in selected]
                active["selected_components"] = selected
                active["decision_notes"] = payload.notes.strip()
            state["components_markdown"] = render_components_markdown(state)
            component_context = resolve_component_context(
                catalogue=catalogue,
                workbench=read_workbench(session, project).model_dump(),
                selected_component_ids=[item["id"] for item in selected],
            )
            state["verification_markdown"] = render_verification_markdown(
                project_name=project.name,
                board=board.model_dump(),
                state=state,
                component_context=component_context,
            )
            state["stage"] = "verification"
            _upsert_markdown(session, project, "components.md", state["components_markdown"])
            _upsert_markdown(session, project, "verification.md", state["verification_markdown"])
            # Writing the manifest resolves the project workspace through its
            # own DB session. Do it only after this transaction closes; nested
            # connections can exhaust the Supabase transaction-pooler slot and
            # leave the confirmation request waiting forever.
            manifest_context = component_context
            artifacts.extend(["components.md", "verification.md"])
        elif stage == "verification":
            state["final_markdown"] = render_final_markdown(project.name, state)
            state["stage"] = "final_review"
            _upsert_markdown(session, project, "final-review.md", state["final_markdown"])
            artifacts.append("final-review.md")
        elif stage == "final_review":
            if not state.get("todos"):
                state["todos"] = phase3_todos(state.get("selected_components") or [])
                for item in state["todos"]:
                    if str(item.get("id", "")).startswith(("select:", "verify:", "design:", "configure:")):
                        item["status"] = "completed"
                set_todo_status(state, "review:approval", "in_progress", "Waiting for final review")
            component_context = resolve_component_context(
                catalogue=catalogue,
                workbench=read_workbench(session, project).model_dump(),
                selected_component_ids=selected_component_ids(state),
            )
            install_results = install_component_libraries(project_id, component_context)
            ini_path = workspace_dir(project_id) / "platformio.ini"
            if ini_path.exists():
                ini_row = session.exec(
                    select(CodeFileRow).where(
                        CodeFileRow.project_id == project.id,
                        CodeFileRow.path == "platformio.ini",
                    )
                ).first()
                if not ini_row:
                    ini_row = CodeFileRow(project_id=project.id, path="platformio.ini", language="ini")
                ini_row.content = ini_path.read_text(encoding="utf-8")
                ini_row.updated_at = now_utc()
                session.add(ini_row)
            state["stage"] = "act"
            set_todo_status(state, "review:approval", "completed", "User approved the final review")
            set_todo_status(state, "act:dependencies", "completed", "Dependencies added to platformio.ini")
            state["final_markdown"] = render_final_markdown(project.name, state)
            _upsert_markdown(session, project, "final-review.md", state["final_markdown"])
            state["condensed_state"] = state["final_markdown"]
        else:
            return {"state": state, "stage": "act", "artifacts": [], "install_results": []}

        project.updated_at = now_utc()
        session.add(project)
        session.commit()

    save_research_state(project_id, state)
    if manifest_context is not None:
        write_component_manifest(project_id, manifest_context)
    # Disk/git materialisation is useful but is not part of the authoritative
    # stage transition. Let the HTTP response reach the UI before walking a
    # potentially large project tree.
    background_tasks.add_task(_sync_project_files, project_id, user_id)
    return {
        "state": normalize_research_state(state),
        "stage": state["stage"],
        "artifacts": artifacts,
        "install_results": install_results,
        "act_mode": state["stage"] == "act",
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
