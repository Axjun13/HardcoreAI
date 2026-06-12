"""AI agent — conversational STM32 copilot — plus deterministic firmware codegen.

The agent uses a C-style THINK/CALL tool-calling loop (see the agent package).
Tools mutate the database through the same helpers the REST routes use, so the
frontend just re-fetches the workbench/files when the run finishes.
"""

from __future__ import annotations

import asyncio
import copy
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

import llm
from agent import AgentTrace, run_agent_phase
from core.config import now_utc
from core.security import get_current_user_id
from db.models import CodeFileRow, ProjectRow
from db.session import db_session
from schemas import (
    AgentRequest,
    AgentRunResult,
    CodeFileRead,
    FirmwareResult,
    PhaseTrace,
)
from services.catalogue import catalogue_index
from services.firmware import generate_firmware
from services.projects import get_project_or_404
from services.workbench import read_workbench

router = APIRouter()


@router.get("/api/agent/providers")
def list_agent_providers() -> dict[str, Any]:
    """Which LLM providers the backend can reach (key present / local)."""
    return {"providers": llm.available_providers()}


def _files_as_dict(session: Session, project: ProjectRow) -> dict[str, dict[str, str]]:
    rows = session.exec(
        select(CodeFileRow).where(CodeFileRow.project_id == project.id)
    ).all()
    return {r.path: {"language": r.language, "content": r.content} for r in rows}


def _strip_duplicate_turn(history: list[dict] | None, problem: str) -> list[dict] | None:
    """Drop the trailing user message when it duplicates the current problem.

    The frontend sends the full conversation including the just-typed message as
    the last entry, but run_phase also receives `problem` as the current turn —
    sending both would show the model the same message twice.
    """
    if not history:
        return None
    hist = list(history)
    if hist and hist[-1].get("role") == "user" and hist[-1].get("content") == problem:
        return hist[:-1] if len(hist) > 1 else None
    return hist or None


def _compute_proposals(
    files_dict: dict[str, dict[str, str]],
    new_files: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    """Diff the agent's in-memory files against the saved baseline.

    Returns one proposal per changed/created/deleted file. Nothing is written to
    the DB here — the frontend renders these as diff cards and only persists the
    ones the user approves (via the files PUT endpoint).
    """
    proposals: list[dict[str, Any]] = []
    for path in sorted(set(files_dict) | set(new_files)):
        old = files_dict.get(path)
        new = new_files.get(path)
        old_content = old.get("content") if old else None
        new_content = new.get("content") if new else None
        if old_content == new_content:
            continue
        proposals.append({
            "path": path,
            "language": (new or old or {}).get("language", "c"),
            "old": old_content or "",
            "code": new_content or "",
            "deleted": new is None,
            "created": old is None,
        })
    return proposals


def _persist_files(
    user_id: str,
    project_id: str,
    files_dict: dict[str, dict[str, str]],
    new_files: dict[str, dict[str, str]],
):
    """Write any changed files back, then return (final_state, final_files)."""
    with db_session(user_id) as session:
        project = get_project_or_404(session, project_id, user_id)
        for path, meta in new_files.items():
            if files_dict.get(path) == meta:
                continue  # unchanged — skip the write
            code_file = session.exec(
                select(CodeFileRow).where(
                    CodeFileRow.project_id == project.id, CodeFileRow.path == path
                )
            ).first()
            if not code_file:
                code_file = CodeFileRow(project_id=project.id, path=path)
            code_file.language = meta.get("language", "c")
            code_file.content = meta.get("content", "")
            code_file.updated_at = now_utc()
            session.add(code_file)
        project.updated_at = now_utc()
        session.add(project)
        session.commit()

        project = get_project_or_404(session, project_id, user_id)
        final_state = read_workbench(session, project)
        final_files = session.exec(
            select(CodeFileRow)
            .where(CodeFileRow.project_id == project.id)
            .order_by(CodeFileRow.path)
        ).all()
    return final_state, final_files


@router.post("/api/projects/{project_id}/agent/solve", response_model=AgentRunResult)
async def agent_solve(project_id: str, payload: AgentRequest, user_id: str = Depends(get_current_user_id)) -> AgentRunResult:
    """Run the conversational STM32 copilot agent.

    A single unified agent phase replaces the old two-phase wiring→coding model.
    The agent asks clarifying questions when board/pin are unspecified, answers
    technical questions in plain text, and generates compilable STM32 HAL firmware.
    """
    if payload.provider not in llm.PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider '{payload.provider}'.")

    with db_session(user_id) as session:
        project = get_project_or_404(session, project_id, user_id)
        catalogue = catalogue_index(session)
        saved_state = read_workbench(session, project)
        files_dict = _files_as_dict(session, project)
        
        from agent.git_manager import GitManager
        git_mgr = GitManager(project_id)
        git_mgr.sync_db_to_disk(files_dict)
        git_mgr.commit_changes("Initial workspace sync")

    prior_history = _strip_duplicate_turn(payload.conversation_history, payload.problem)

    try:
        agent_trace, new_files = await run_agent_phase(
            provider=payload.provider,
            project_id=project_id,
            project_name=project.name,
            problem=payload.problem,
            catalogue=catalogue,
            workbench=saved_state.model_dump(),
            files=copy.deepcopy(files_dict),
            user_id=user_id,
            messages=prior_history,
            build_output=payload.build_output,
        )
    except llm.LLMError as exc:
        raise HTTPException(status_code=502, detail=f"LLM error: {exc}")

    final_state, final_files = _persist_files(user_id, project_id, files_dict, new_files)
    git_mgr.sync_db_to_disk(new_files)
    git_mgr.commit_changes(f"Agent solve: {payload.problem[:60]}")

    empty_wiring = AgentTrace(phase="wiring", final="")

    def _phase_trace(t: AgentTrace) -> PhaseTrace:
        return PhaseTrace(
            phase=t.phase,
            steps=t.steps,
            final=t.final,
            status=getattr(t, "status", "completed"),
            question=getattr(t, "question", ""),
            options=getattr(t, "options", []),
            messages=getattr(t, "messages", []),
        )

    return AgentRunResult(
        provider=payload.provider,
        wiring=_phase_trace(empty_wiring),
        coding=_phase_trace(agent_trace),
        workbench=final_state,
        files=[
            CodeFileRead(path=f.path, language=f.language, content=f.content, updated_at=f.updated_at)
            for f in final_files
        ],
    )


def _sse(event: dict) -> str:
    """Format one dict as a Server-Sent Events frame."""
    return f"data: {json.dumps(event)}\n\n"


@router.post("/api/projects/{project_id}/agent/stream")
async def agent_stream(project_id: str, payload: AgentRequest, user_id: str = Depends(get_current_user_id)):
    """Run the agent and stream each step to the client over SSE.

    Same work as /agent/solve, but instead of blocking until the whole trace is
    ready it pushes one event per agent step (think / call / code / question /
    plan / result / final) so the panel can render live. The terminal `done`
    event carries the persisted files + final status so the frontend can refresh.
    """
    if payload.provider not in llm.PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider '{payload.provider}'.")

    with db_session(user_id) as session:
        project = get_project_or_404(session, project_id, user_id)
        catalogue = catalogue_index(session)
        saved_state = read_workbench(session, project)
        files_dict = _files_as_dict(session, project)
        project_name = project.name
        
    from agent.git_manager import GitManager
    git_mgr = GitManager(project_id)
    git_mgr.sync_db_to_disk(files_dict)
    git_mgr.commit_changes("Initial workspace sync")

    prior_history = _strip_duplicate_turn(payload.conversation_history, payload.problem)

    queue: asyncio.Queue = asyncio.Queue()

    async def on_event(event: dict) -> None:
        await queue.put(event)

    async def run() -> None:
        """Drive the agent, then enqueue the terminal `done` event with proposals.

        Nothing is persisted here: the agent's file changes are staged as
        proposals the user approves in the chat (via the files PUT endpoint)."""
        try:
            agent_trace, new_files = await run_agent_phase(
                provider=payload.provider,
                project_id=project_id,
                project_name=project_name,
                problem=payload.problem,
                catalogue=catalogue,
                workbench=saved_state.model_dump(),
                files=copy.deepcopy(files_dict),
                user_id=user_id,
                messages=prior_history,
                build_output=payload.build_output,
                on_event=on_event,
            )
            # Stage, don't commit: the agent's file changes are surfaced as
            # proposals for the user to Allow/Reject in the chat. We persist
            # nothing here — approval goes through the files PUT endpoint, and the
            # workbench is read back unchanged for the panel to refresh against.
            proposals = _compute_proposals(files_dict, new_files)
            await queue.put({
                "type": "done",
                "status": getattr(agent_trace, "status", "completed"),
                "final": agent_trace.final,
                "question": getattr(agent_trace, "question", ""),
                "options": getattr(agent_trace, "options", []),
                "proposals": proposals,
            })
        except llm.LLMError as exc:
            await queue.put({"type": "error", "fatal": True, "message": f"LLM error: {exc}"})
        except Exception as exc:  # noqa: BLE001 — surface any failure to the client
            await queue.put({"type": "error", "fatal": True, "message": str(exc)})
        finally:
            await queue.put(None)  # sentinel: stream complete

    async def event_stream():
        task = asyncio.create_task(run())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield _sse(event)
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable proxy buffering so events flush live
        },
    )


@router.post("/api/projects/{project_id}/generate", response_model=FirmwareResult)
def generate_project_firmware(project_id: str, user_id: str = Depends(get_current_user_id)) -> FirmwareResult:
    """Generate firmware from the saved workbench netlist and persist it."""
    with db_session(user_id) as session:
        project = get_project_or_404(session, project_id, user_id)
        state = read_workbench(session, project)
        catalogue = catalogue_index(session)

        result = generate_firmware(state, project.name, catalogue)

        code_file = session.exec(
            select(CodeFileRow).where(
                CodeFileRow.project_id == project.id, CodeFileRow.path == result.path
            )
        ).first()
        if not code_file:
            code_file = CodeFileRow(project_id=project.id, path=result.path)
        code_file.language = result.language
        code_file.content = result.content
        code_file.updated_at = now_utc()
        project.updated_at = now_utc()
        session.add(code_file)
        session.add(project)
        session.commit()
        return result
