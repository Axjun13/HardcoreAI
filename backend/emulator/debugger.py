"""GDB debugger driving QEMU's gdbstub via pygdbmi.

Replaces the hand-rolled GDB/MI client + parser from the Go `debug` package:
pygdbmi owns the arm-none-eabi-gdb subprocess and parses MI responses into
dicts, so we only express the handful of commands the HTTP contract needs
(connect to the remote stub, read registers, step, halt, continue).
"""

from __future__ import annotations

from pygdbmi.gdbcontroller import GdbController

# GDB/MI register indices -> labelled fields the contract renders.
# (0..12 -> R0..R12, 13 SP, 14 LR, 15 PC, 25 XPSR — same mapping as the Go port.)
_REG_INDEX: dict[int, str] = {
    **{i: f"R{i}" for i in range(13)},
    13: "SP",
    14: "LR",
    15: "PC",
    25: "XPSR",
}


class DebuggerError(RuntimeError):
    pass


class GDBDebugger:
    def __init__(self, elf_path: str, gdb_port: int = 3333):
        self._elf_path = elf_path
        self._gdb_port = gdb_port
        self._gdb: GdbController | None = None

    def connect(self) -> None:
        gdb = GdbController(
            command=["arm-none-eabi-gdb", "--nx", "--quiet", "--interpreter=mi2"]
        )
        # Non-interactive, async-capable session; then load the ELF and attach.
        gdb.write("-gdb-set pagination off")
        gdb.write("-gdb-set confirm off")
        gdb.write("-gdb-set mi-async on")
        gdb.write(f"-file-exec-and-symbols {self._elf_path}")
        responses = gdb.write(f"-target-select remote 127.0.0.1:{self._gdb_port}")
        if not _has_success(responses, accept=("connected", "done")):
            gdb.exit()
            raise DebuggerError("failed to connect gdb target")
        self._gdb = gdb

    def disconnect(self) -> None:
        if self._gdb is not None:
            try:
                self._gdb.exit()
            except Exception:  # noqa: BLE001 — best-effort teardown
                pass
            self._gdb = None

    def step(self) -> None:
        responses = self._cmd("-exec-step-instruction")
        if any(r.get("message") == "error" for r in responses):
            raise DebuggerError("step failed")

    def halt(self) -> None:
        self._cmd("-exec-interrupt")

    def continue_(self) -> None:
        self._cmd("-exec-continue")

    def read_registers(self) -> dict[str, int]:
        responses = self._cmd("-data-list-register-values x")
        return _parse_registers(responses)

    # -- internals -----------------------------------------------------------

    def _cmd(self, mi_cmd: str) -> list[dict]:
        if self._gdb is None:
            raise DebuggerError("debugger not connected")
        return self._gdb.write(mi_cmd)


def _has_success(responses: list[dict], accept: tuple[str, ...]) -> bool:
    """True if any result record carries one of the accepted MI messages."""
    return any(
        r.get("type") == "result" and r.get("message") in accept for r in responses
    )


def _parse_registers(responses: list[dict]) -> dict[str, int]:
    """Extract labelled registers from a -data-list-register-values payload.

    pygdbmi parses the MI into:
        {"type": "result", "message": "done",
         "payload": {"register-values": [{"number": "0", "value": "0x..."}, ...]}}
    """
    regs: dict[str, int] = {}
    for r in responses:
        if r.get("type") != "result":
            continue
        payload = r.get("payload") or {}
        for entry in payload.get("register-values", []):
            try:
                num = int(entry["number"])
                val = int(entry["value"], 0)
            except (KeyError, ValueError):
                continue
            label = _REG_INDEX.get(num)
            if label is not None:
                regs[label] = val & 0xFFFFFFFF
    return regs
