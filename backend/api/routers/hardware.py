"""Real STM32 build / flash / device detection endpoints.

Builds and flashes the on-disk workspace that GitManager materializes from the
DB. Build always returns output; flash is gated on a connected ST-Link/board.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import select

from agent.git_manager import GitManager
from core.security import get_current_user_id
from db.models import CodeFileRow
from db.session import db_session
from schemas import BuildResult, DeviceStatus, FlashResult
from services import hardware
from services.projects import get_project_or_404

router = APIRouter()


def _sse(event: dict) -> str:
    """Format one dict as a Server-Sent Events frame (same shape as the agent stream)."""
    return f"data: {json.dumps(event)}\n\n"


def _offline_project_detection(project_id: str, reason: Exception) -> DeviceStatus:
    """Keep device polling alive when the project DB is temporarily unreachable."""
    try:
        status = hardware.auto_detect_board(project_id)
        prefix = "Project database unavailable; ran generic detection instead."
        status.detail = f"{prefix} {status.detail}".strip()
        return status
    except Exception:
        return DeviceStatus(
            connected=False,
            probe="Database",
            detail=f"Project database unavailable while checking device status: {reason}",
        )


def _sync_workspace(project_id: str, user_id: str) -> None:
    """Materialize the project's DB files to disk so PlatformIO can build them."""
    with db_session(user_id) as session:
        project = get_project_or_404(session, project_id, user_id)
        rows = session.exec(
            select(CodeFileRow).where(CodeFileRow.project_id == project.id)
        ).all()
        files_dict = {r.path: {"language": r.language, "content": r.content} for r in rows}
    git_mgr = GitManager(project_id)
    git_mgr.sync_db_to_disk(files_dict)


@router.get("/api/device/status")
def device_status(
    project_id: str | None = None, user_id: str = Depends(get_current_user_id)
) -> DeviceStatus:
    """Whether an ST-Link + STM32 board is currently connected. Polled by the UI.

    If project_id is given, probes against that project's actual target board
    (previously this always probed using the Blue Pill's target script
    regardless of which board the project used). If omitted, runs a generic
    chip-ID probe and suggests a matching board instead of assuming one.
    """
    if project_id:
        try:
            with db_session(user_id) as session:
                project = get_project_or_404(session, project_id, user_id)
                return hardware.detect_device(project.board_id, session=session)
        except HTTPException:
            raise
        except Exception as exc:
            return _offline_project_detection(project_id, exc)
    return hardware.probe_connected_chip()


@router.get("/api/device/detect")
def detect_board(
    project_id: str | None = None, user_id: str = Depends(get_current_user_id)
) -> DeviceStatus:
    """Infer the best STM32 board from project files and connected hardware."""
    if project_id:
        try:
            with db_session(user_id) as session:
                get_project_or_404(session, project_id, user_id)
        except HTTPException:
            raise
        except Exception:
            pass
    return hardware.auto_detect_board(project_id)

@router.post("/api/projects/{project_id}/build")
def build(project_id: str, user_id: str = Depends(get_current_user_id)) -> BuildResult:
    """Sync the project to disk and run a real PlatformIO build. Returns output."""
    _sync_workspace(project_id, user_id)
    with db_session(user_id) as session:
        return hardware.build_project(project_id, session=session)


@router.post("/api/projects/{project_id}/build/stream")
async def build_stream(project_id: str, user_id: str = Depends(get_current_user_id)):
    """Run a real PlatformIO build, streaming each output line over SSE.

    Emits `line`/`status` events as the build runs and a terminal `done` event
    carrying success, returncode, firmware_path, and the full output. Mirrors the
    agent stream: the blocking build generator runs on a worker thread and feeds
    an asyncio queue the event loop drains.
    """
    _sync_workspace(project_id, user_id)
    with db_session(user_id) as session:
        board_id = get_project_or_404(session, project_id, user_id).board_id

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def run() -> None:
        try:
            for event in hardware.build_project_stream(project_id, board_id):
                loop.call_soon_threadsafe(queue.put_nowait, event)
        except Exception as exc:  # noqa: BLE001 — surface to client
            loop.call_soon_threadsafe(queue.put_nowait, {
                "type": "done", "success": False, "returncode": 1,
                "firmware_path": None, "duration_s": 0.0, "output": str(exc),
            })
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

    async def event_stream():
        task = asyncio.create_task(asyncio.to_thread(run))
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
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/projects/{project_id}/flash")
def flash(project_id: str, user_id: str = Depends(get_current_user_id)) -> FlashResult:
    """Sync, then flash via PlatformIO upload — gated on a detected device."""
    _sync_workspace(project_id, user_id)
    with db_session(user_id) as session:
        return hardware.flash_project(project_id, session=session)
