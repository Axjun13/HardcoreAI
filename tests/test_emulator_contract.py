"""Contract tests for the emulator service HTTP API (currently the Go server).

What the Python backend depends on (see backend/tools.py DebuggingToolbox):
  POST /platformio/build  -> JSON {"success": bool, "output": str, ["error"]}
  GET  /qemu/run          -> 200, text body (starts QEMU)
  GET  /debug/connect     -> 200, text "Debugger Connected"
  GET  /debug/registers   -> 200, text "PC: 0x... SP: 0x... R0..R12"
  GET  /debug/step        -> 200, text "CPU Stepped"

Plus the supporting contract observed from main.go:
  GET  /health            -> JSON {"status":"ok","debugger_connected":bool}
  GET  /debug/halt        -> 200 "CPU Halted"
  GET  /debug/continue    -> 200 "CPU Running"
  debug endpoints before connect -> 409 "Debugger is not connected"
  malformed build body            -> 400
  OPTIONS preflight               -> 200 with CORS headers

These tests treat the service as a black box. The Python reimplementation must
satisfy the same assertions for the port to be considered non-regressing.
"""

from __future__ import annotations

import re

import pytest

from conftest import HAS_ARM_GDB, HAS_FIRMWARE, HAS_PIO, HAS_QEMU


# ---------------------------------------------------------------------------
# Health + CORS — no external tooling required.
# ---------------------------------------------------------------------------


def test_health_shape(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert isinstance(body["debugger_connected"], bool)


def test_cors_headers_present(client):
    resp = client.get("/health")
    assert resp.headers.get("access-control-allow-origin") == "*"


def test_options_preflight_returns_200(client):
    resp = client.request("OPTIONS", "/health")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Error-path contract — needs no QEMU/GDB; debugger starts disconnected.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/debug/registers", "/debug/halt", "/debug/continue", "/debug/step"])
def test_debug_endpoints_409_before_connect(client, path):
    resp = client.get(path)
    assert resp.status_code == 409
    assert "not connected" in resp.text.lower()


def test_build_rejects_malformed_json(client):
    resp = client.post("/platformio/build", content="this is not json")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# PlatformIO build — needs pio + the STM32 toolchain.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_PIO, reason="PlatformIO (pio) not installed")
def test_build_returns_success_contract(client):
    """POST /platformio/build returns {success, output}; success is True for the
    known-good Blinky project."""
    resp = client.post(
        "/platformio/build",
        json={"projectPath": "./Blinky"},
        timeout=300.0,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "success" in body and isinstance(body["success"], bool)
    assert "output" in body and isinstance(body["output"], str)
    assert body["success"] is True, f"expected clean Blinky build, got: {body.get('error') or body['output'][:500]}"


# ---------------------------------------------------------------------------
# Full QEMU + GDB debug lifecycle — needs qemu, arm-gdb, and a prebuilt ELF.
# This is one ordered test because the endpoints are stateful (connect must
# precede registers/step) and they share the single global debugger.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (HAS_QEMU and HAS_ARM_GDB and HAS_FIRMWARE),
    reason="needs qemu-system-arm, arm-none-eabi-gdb, and a prebuilt firmware.elf",
)
def test_qemu_and_debug_lifecycle(client):
    # Start QEMU loading the prebuilt firmware.
    run = client.get("/qemu/run", timeout=15.0)
    assert run.status_code == 200
    assert "QEMU" in run.text  # observed: "QEMU Started"

    # Connect the GDB debugger to the running QEMU gdbstub.
    connect = client.get("/debug/connect", timeout=15.0)
    assert connect.status_code == 200
    assert "Connected" in connect.text  # observed: "Debugger Connected"

    # Health now reports the debugger as connected.
    assert client.get("/health").json()["debugger_connected"] is True

    # Registers come back as the labelled text block the backend reads verbatim.
    regs = client.get("/debug/registers", timeout=10.0)
    assert regs.status_code == 200
    for label in ("PC:", "SP:", "LR:", "XPSR:", "R0:", "R12:"):
        assert label in regs.text
    # PC is rendered as a 0x + 8 hex-digit value.
    assert re.search(r"PC:\s*0x[0-9A-Fa-f]{8}", regs.text)

    # Step / halt / continue are accepted and return their status strings.
    step = client.get("/debug/step", timeout=10.0)
    assert step.status_code == 200
    assert "Stepped" in step.text

    halt = client.get("/debug/halt", timeout=10.0)
    assert halt.status_code == 200
    assert "Halted" in halt.text

    cont = client.get("/debug/continue", timeout=10.0)
    assert cont.status_code == 200
    assert "Running" in cont.text
