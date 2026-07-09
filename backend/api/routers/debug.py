"""Debug router — GDB / OpenOCD hardware debug endpoints.

All routes are under /api/projects/{project_id}/debug/.

This router is intentionally isolated: it does not touch the agent, RAG,
workbench, or any other existing subsystem.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from core.security import get_current_user_id
from schemas import (
    DebugBreakpoint,
    DebugBreakpointRequest,
    DebugSnapshot,
    DebugStartRequest,
    DebugState,
)
from services import debug as debug_svc
from services.projects import get_project_or_404
from db.session import db_session

log = logging.getLogger(__name__)
router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sse(event: dict) -> str:
    """Format one dict as a Server-Sent Events frame."""
    return f"data: {json.dumps(event)}\n\n"


def _get_active_session(project_id: str):
    """Return the live DebugSession or raise 409."""
    session = debug_svc.get_session(project_id)
    if session is None:
        raise HTTPException(status_code=409, detail="No active debug session for this project. Call /debug/start first.")
    return session


def _get_project_path(project_id: str, user_id: str) -> str:
    """Resolve the on-disk workspace directory for a project."""
    from services.hardware import workspace_dir
    with db_session(user_id) as session:
        # Validate the project exists and belongs to this user
        get_project_or_404(session, project_id, user_id)
    return str(workspace_dir(project_id))



# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/api/projects/{project_id}/debug/start")
async def debug_start(
    project_id: str,
    payload: DebugStartRequest = DebugStartRequest(),
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Build if needed, launch OpenOCD+GDB, return initial snapshot.

    Returns a DebugSnapshot-compatible dict. If `snapshot.error` is set,
    the session could not be started and has already been cleaned up.
    """
    # Kill any existing session for this project first
    existing = debug_svc.get_session(project_id)
    if existing:
        try:
            await existing.stop()
        except Exception:
            pass

    try:
        project_path = _get_project_path(project_id, user_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not resolve project path: {e}")

    # Determine probe from project settings (default to ST-Link)
    # Determine probe from project settings (default to ST-Link)
    probe = "ST-Link V2"
    board = payload.board
    
    if board is None:
        from boards import device_manager
        with db_session(user_id) as db:
            board = device_manager.for_project(project_id, db).id
    print(f"[DEBUG STEP32] resolved board = {board}")

    try:
        session = debug_svc.get_or_create_session(project_id, project_path)
        snapshot = await session.start(board=board, probe=probe)
    except Exception as e:
        log.exception("Failed to start debug session for project %s", project_id)
        debug_svc.remove_session(project_id)
        raise HTTPException(status_code=500, detail=str(e))

    return snapshot


@router.post("/api/projects/{project_id}/debug/stop")
async def debug_stop(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, str]:
    """Kill the GDB + OpenOCD session for this project."""
    session = debug_svc.get_session(project_id)
    if session:
        try:
            await session.stop()
        except Exception as e:
            log.warning("Error stopping debug session: %s", e)
    return {"status": "stopped"}


@router.get("/api/projects/{project_id}/debug/stream")
async def debug_stream(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
) -> StreamingResponse:
    """SSE stream of GDB MI events (stopped, running, log).

    Drains the session's asyncio.Queue and forwards each event as an
    SSE frame. The client should reconnect if the stream ends.
    """
    session = _get_active_session(project_id)

    async def event_stream():
        yield _sse({"type": "connected", "project_id": project_id})
        while True:
            try:
                event = await asyncio.wait_for(session.event_queue.get(), timeout=30.0)
                yield _sse(event)
            except asyncio.TimeoutError:
                # Heartbeat to keep the connection alive
                yield _sse({"type": "heartbeat"})
            except Exception:
                break

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/projects/{project_id}/debug/snapshot")
async def debug_snapshot(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """On-demand: read current registers, call stack, locals."""
    session = _get_active_session(project_id)
    if not session.halted:
        raise HTTPException(status_code=409, detail="Target is not halted. Halt the target before reading state.")
    return await session.snapshot()


@router.post("/api/projects/{project_id}/debug/breakpoint")
async def debug_set_breakpoint(
    project_id: str,
    payload: DebugBreakpointRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Set a breakpoint at file:line. Returns {id, file, line, enabled}."""
    session = _get_active_session(project_id)
    try:
        bp = await session.set_breakpoint(payload.file, payload.line)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not set breakpoint: {e}")
    return bp


@router.delete("/api/projects/{project_id}/debug/breakpoint/{bp_id}")
async def debug_remove_breakpoint(
    project_id: str,
    bp_id: int,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, str]:
    """Remove a breakpoint by its GDB id."""
    session = _get_active_session(project_id)
    try:
        await session.remove_breakpoint(bp_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not remove breakpoint: {e}")
    return {"status": "removed", "id": str(bp_id)}


@router.post("/api/projects/{project_id}/debug/continue")
async def debug_continue(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, str]:
    """Resume target execution (exec-continue)."""
    session = _get_active_session(project_id)
    if not session.halted:
        raise HTTPException(status_code=409, detail="Target is not halted.")
    await session.continue_exec()
    return {"status": "running"}


@router.post("/api/projects/{project_id}/debug/step-over")
async def debug_step_over(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, str]:
    """Step over one source line (exec-next)."""
    session = _get_active_session(project_id)
    if not session.halted:
        raise HTTPException(status_code=409, detail="Target is not halted.")
    await session.step_over()
    return {"status": "stepping"}


@router.post("/api/projects/{project_id}/debug/step-into")
async def debug_step_into(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, str]:
    """Step into (exec-step)."""
    session = _get_active_session(project_id)
    if not session.halted:
        raise HTTPException(status_code=409, detail="Target is not halted.")
    await session.step_into()
    return {"status": "stepping"}


@router.post("/api/projects/{project_id}/debug/step-out")
async def debug_step_out(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, str]:
    """Step out of current function (exec-finish)."""
    session = _get_active_session(project_id)
    if not session.halted:
        raise HTTPException(status_code=409, detail="Target is not halted.")
    await session.step_out()
    return {"status": "stepping"}
