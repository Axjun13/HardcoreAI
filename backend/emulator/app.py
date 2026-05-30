"""FastAPI emulator service — Python port of emulator-service/main.go.

Serves the :62019 HTTP contract the backend's DebuggingToolbox depends on:
build firmware via PlatformIO, run it under QEMU, and drive a GDB debugger.
The contract (status codes, body shapes, plain-text markers) is asserted by
tests/test_emulator_contract.py and must not regress.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from . import platformio
from .debugger import GDBDebugger
from .qemu import runner

# Self-contained firmware: resolve the prebuilt ELF relative to this package so
# the service works regardless of the process working directory.
PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_PROJECT = PACKAGE_DIR / "Blinky"
FIRMWARE_ELF = DEFAULT_PROJECT / ".pio/build/genericSTM32F405RG/firmware.elf"

app = FastAPI()

# Single global debugger, mirroring `var dbg` in main.go. None == disconnected.
_dbg: GDBDebugger | None = None


# ---------------------------------------------------------------------------
# CORS — applied to every response, including errors and OPTIONS preflight.
# ---------------------------------------------------------------------------
@app.middleware("http")
async def cors_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        resp: Response = Response(status_code=200)
    else:
        resp = await call_next(request)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


def _require_debugger() -> Response | None:
    """Return a 409 response when no debugger is connected, else None."""
    if _dbg is None:
        return PlainTextResponse("Debugger is not connected", status_code=409)
    return None


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "debugger_connected": _dbg is not None})


# ---------------------------------------------------------------------------
# PlatformIO build / flash
# ---------------------------------------------------------------------------
def _resolve_project_path(raw: str) -> str:
    """Map a request's projectPath onto the bundled project.

    The Go service ran from emulator-service/ so "./Blinky" resolved next to it.
    Here the project is bundled in the package, so a relative path is taken
    relative to the package dir; absolute paths are honoured as-is.
    """
    if not raw:
        return str(DEFAULT_PROJECT)
    p = Path(raw)
    if p.is_absolute():
        return str(p)
    return str((PACKAGE_DIR / p).resolve())


async def _build_or_flash(request: Request, flash: bool) -> Response:
    try:
        body = await request.body()
        req = json.loads(body)
        if not isinstance(req, dict):
            raise ValueError("expected JSON object")
    except (json.JSONDecodeError, ValueError) as exc:
        return PlainTextResponse(str(exc), status_code=400)

    project_path = _resolve_project_path(req.get("projectPath", ""))
    platformio.sync_files(project_path, req.get("files", []) or [])

    try:
        if flash:
            output, ok = platformio.flash_project(project_path)
        else:
            output, ok = platformio.build_project(project_path)
    except platformio.PlatformIOError as exc:
        return JSONResponse({"success": False, "output": "", "error": str(exc)})

    response: dict = {"success": ok, "output": output}
    if not ok:
        response["error"] = output
    return JSONResponse(response)


@app.post("/platformio/build")
async def build(request: Request) -> Response:
    return await _build_or_flash(request, flash=False)


@app.post("/platformio/flash")
async def flash(request: Request) -> Response:
    return await _build_or_flash(request, flash=True)


# ---------------------------------------------------------------------------
# QEMU
# ---------------------------------------------------------------------------
@app.get("/qemu/run")
async def qemu_run() -> PlainTextResponse:
    try:
        msg = runner.run(str(FIRMWARE_ELF))
    except OSError as exc:
        return PlainTextResponse(str(exc), status_code=200)
    return PlainTextResponse(msg)


@app.get("/qemu/stream")
async def qemu_stream() -> StreamingResponse:
    ch = runner.subscribe()

    def event_stream():
        try:
            while True:
                msg = ch.get()
                yield f"data: {msg}\n\n"
        finally:
            runner.unsubscribe(ch)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# ---------------------------------------------------------------------------
# Debugger lifecycle
# ---------------------------------------------------------------------------
@app.get("/debug/connect")
async def debug_connect() -> Response:
    global _dbg
    if _dbg is not None:
        _dbg.disconnect()
        _dbg = None
    debugger = GDBDebugger(str(FIRMWARE_ELF))
    try:
        debugger.connect()
    except Exception as exc:  # noqa: BLE001 — surface any connect failure as 500
        return PlainTextResponse(str(exc), status_code=500)
    _dbg = debugger
    return PlainTextResponse("Debugger Connected")


@app.get("/debug/registers")
async def debug_registers() -> Response:
    if (blocked := _require_debugger()) is not None:
        return blocked
    assert _dbg is not None
    try:
        regs = _dbg.read_registers()
    except Exception as exc:  # noqa: BLE001
        return PlainTextResponse(str(exc), status_code=500)
    return PlainTextResponse(_format_registers(regs))


@app.get("/debug/step")
async def debug_step() -> Response:
    if (blocked := _require_debugger()) is not None:
        return blocked
    assert _dbg is not None
    try:
        _dbg.step()
    except Exception as exc:  # noqa: BLE001
        return PlainTextResponse(str(exc), status_code=500)
    return PlainTextResponse("CPU Stepped")


@app.get("/debug/halt")
async def debug_halt() -> Response:
    if (blocked := _require_debugger()) is not None:
        return blocked
    assert _dbg is not None
    try:
        _dbg.halt()
    except Exception as exc:  # noqa: BLE001
        return PlainTextResponse(str(exc), status_code=500)
    return PlainTextResponse("CPU Halted")


@app.get("/debug/continue")
async def debug_continue() -> Response:
    if (blocked := _require_debugger()) is not None:
        return blocked
    assert _dbg is not None
    try:
        _dbg.continue_()
    except Exception as exc:  # noqa: BLE001
        return PlainTextResponse(str(exc), status_code=500)
    return PlainTextResponse("CPU Running")


def _format_registers(regs: dict[str, int]) -> str:
    """Render the labelled register block the backend reads verbatim.

    Matches RegistersHandler in main.go: PC/SP/LR/XPSR, a blank line, then
    R0..R12, each as a zero-padded 8-hex-digit value. Missing registers render
    as 0x00000000 so the labels are always present.
    """
    def hx(name: str) -> str:
        return f"0x{regs.get(name, 0):08X}"

    head = "\n".join(f"{n}: {hx(n)}" for n in ("PC", "SP", "LR", "XPSR"))
    body = "\n".join(f"R{i}: {hx(f'R{i}')}" for i in range(13))
    return f"{head}\n\n{body}"


def main() -> None:
    import uvicorn

    host = os.environ.get("EMULATOR_HOST", "127.0.0.1")
    port = int(os.environ.get("EMULATOR_PORT", "62019"))
    print(f"Server running on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
