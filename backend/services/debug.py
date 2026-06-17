"""GDB / OpenOCD debug session manager.

Each project gets at most one DebugSession at a time.  The session:
  1. Locates the .elf firmware produced by PlatformIO.
  2. Derives the OpenOCD config files from platformio.ini (board / probe).
  3. Spawns  openocd  as a GDB server on port 3333.
  4. Spawns  arm-none-eabi-gdb --interpreter=mi2  and connects to :3333.
  5. Runs a background thread that reads GDB MI stdout and pushes parsed
     events onto an asyncio.Queue so the SSE endpoint can forward them.

Public API (all called from the FastAPI router):

    session = DebugSession(project_id, project_path)
    snapshot = await session.start()      # start OpenOCD + GDB
    await session.stop()                  # graceful shutdown
    bp = await session.set_breakpoint(file, line)
    await session.remove_breakpoint(bp_id)
    await session.continue_exec()
    await session.step_over()
    await session.step_into()
    await session.step_out()
    snap = await session.snapshot()       # read registers + stack + locals on demand
    q   = session.event_queue            # asyncio.Queue of dicts
"""

from __future__ import annotations

import asyncio
import configparser
import json
import logging
import os
import queue
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── Registry: one session per project ────────────────────────────────────────
_sessions: dict[str, "DebugSession"] = {}


def get_session(project_id: str) -> "DebugSession | None":
    return _sessions.get(project_id)


def get_or_create_session(project_id: str, project_path: str) -> "DebugSession":
    if project_id not in _sessions:
        _sessions[project_id] = DebugSession(project_id, project_path)
    return _sessions[project_id]


def remove_session(project_id: str) -> None:
    _sessions.pop(project_id, None)


# ── ARM core register metadata ────────────────────────────────────────────────
_ARM_REGISTER_NAMES = {
    0: "r0",  1: "r1",  2: "r2",  3: "r3",
    4: "r4",  5: "r5",  6: "r6",  7: "r7",
    8: "r8",  9: "r9",  10: "r10", 11: "r11",
    12: "r12", 13: "sp", 14: "lr", 15: "pc",
    16: "xpsr",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_elf(project_path: str) -> Path | None:
    """Return the first .elf under .pio/build/, or None if not built yet."""
    pio_build = Path(project_path) / ".pio" / "build"
    if not pio_build.exists():
        return None
    for elf in pio_build.rglob("firmware.elf"):
        return elf
    for elf in pio_build.rglob("*.elf"):
        return elf
    return None


def _board_to_openocd_target(board: str) -> str:
    """Map a PlatformIO board id to an OpenOCD target config filename."""
    mapping: dict[str, str] = {
        # STM32F1
        "bluepill_f103c8": "target/stm32f1x.cfg",
        "genericSTM32F103C8": "target/stm32f1x.cfg",
        "genericSTM32F103CB": "target/stm32f1x.cfg",
        # STM32F4
        "disco_f407vg": "target/stm32f4x.cfg",
        "nucleo_f401re": "target/stm32f4x.cfg",
        "nucleo_f411re": "target/stm32f4x.cfg",
        "nucleo_f446re": "target/stm32f4x.cfg",
        "black_f407ve": "target/stm32f4x.cfg",
        # STM32L4
        "nucleo_l476rg": "target/stm32l4x.cfg",
        # RP2040
        "rpipico": "target/rp2040.cfg",
        # ESP32 (not well supported via openocd, fallback)
        "esp32dev": "target/esp32.cfg",
    }
    board_lower = board.lower()
    for key, val in mapping.items():
        if key.lower() in board_lower or board_lower in key.lower():
            return val
    # Default to STM32F1 if unknown
    return "target/stm32f1x.cfg"


def _probe_to_openocd_interface(probe: str) -> str:
    """Map probe name to OpenOCD interface cfg."""
    if "jlink" in probe.lower() or "j-link" in probe.lower():
        return "interface/jlink.cfg"
    if "cmsis" in probe.lower():
        return "interface/cmsis-dap.cfg"
    # default: ST-Link
    return "interface/stlink.cfg"


def _find_gdb() -> str:
    """Locate arm-none-eabi-gdb, preferring the PlatformIO toolchain."""
    # Try PlatformIO toolchain locations
    home = Path.home()
    pio_toolchains = home / ".platformio" / "packages"
    if pio_toolchains.exists():
        for gdb in sorted(pio_toolchains.rglob("arm-none-eabi-gdb*")):
            if gdb.is_file() and os.access(gdb, os.X_OK):
                return str(gdb)
    # Fall back to system PATH
    return "arm-none-eabi-gdb"


def _find_openocd() -> str:
    """Locate openocd, preferring the PlatformIO-bundled version."""
    home = Path.home()
    pio_tool = home / ".platformio" / "packages" / "tool-openocd" / "bin" / "openocd"
    if pio_tool.exists():
        return str(pio_tool)
    # Check vendor dir in project root
    for vendor_ocd in Path(".").rglob("openocd"):
        if vendor_ocd.is_file():
            return str(vendor_ocd)
    return "openocd"


def _find_openocd_scripts() -> str | None:
    """Return OpenOCD scripts dir (for -s flag)."""
    home = Path.home()
    scripts = home / ".platformio" / "packages" / "tool-openocd" / "openocd" / "scripts"
    if scripts.exists():
        return str(scripts)
    return None


# ── GDB MI parser ─────────────────────────────────────────────────────────────

def _parse_mi_value(s: str) -> Any:
    """Very small GDB MI value parser (handles strings, tuples, lists)."""
    s = s.strip()
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if s.startswith("{") and s.endswith("}"):
        return _parse_mi_tuple(s[1:-1])
    if s.startswith("[") and s.endswith("]"):
        return _parse_mi_list(s[1:-1])
    return s


def _parse_mi_tuple(s: str) -> dict:
    """Parse GDB MI tuple {key=val, key=val, ...}."""
    result: dict = {}
    depth = 0
    key_buf = ""
    val_buf = ""
    in_val = False
    i = 0
    while i < len(s):
        c = s[i]
        if c in ("{", "[", '"') and in_val:
            if c == '"':
                # find closing quote
                j = i + 1
                while j < len(s) and (s[j] != '"' or s[j-1] == '\\'):
                    j += 1
                val_buf += s[i:j+1]
                i = j + 1
                continue
            depth += 1
        elif c in ("}", "]") and in_val and depth > 0:
            depth -= 1
        elif c == "=" and not in_val and depth == 0:
            in_val = True
            i += 1
            continue
        elif c == "," and depth == 0 and in_val:
            result[key_buf.strip()] = _parse_mi_value(val_buf.strip())
            key_buf = ""
            val_buf = ""
            in_val = False
            i += 1
            continue

        if in_val:
            val_buf += c
        else:
            key_buf += c
        i += 1

    if key_buf.strip() and in_val:
        result[key_buf.strip()] = _parse_mi_value(val_buf.strip())
    return result


def _parse_mi_list(s: str) -> list:
    """Parse GDB MI list [val, val, ...] or [{...},{...}]."""
    if not s.strip():
        return []
    items = []
    depth = 0
    buf = ""
    i = 0
    while i < len(s):
        c = s[i]
        if c in ("{", "[", '"'):
            if c == '"':
                j = i + 1
                while j < len(s) and (s[j] != '"' or s[j-1] == '\\'):
                    j += 1
                buf += s[i:j+1]
                i = j + 1
                continue
            depth += 1
        elif c in ("}", "]"):
            depth -= 1
        elif c == "," and depth == 0:
            items.append(_parse_mi_value(buf.strip()))
            buf = ""
            i += 1
            continue
        buf += c
        i += 1
    if buf.strip():
        items.append(_parse_mi_value(buf.strip()))
    return items


def _parse_mi_line(line: str) -> dict | None:
    """Parse one GDB MI output line into a dict."""
    line = line.strip()
    if not line:
        return None

    # Token prefix (optional numeric token)
    token = None
    m = re.match(r'^(\d+)', line)
    if m:
        token = int(m.group(1))
        line = line[m.end():]

    if not line:
        return None

    prefix = line[0]
    rest = line[1:]

    msg: dict[str, Any] = {"token": token}

    if prefix == "^":  # result record
        m2 = re.match(r'^(\w+)(,(.*))?$', rest, re.DOTALL)
        if m2:
            msg["type"] = "result"
            msg["class"] = m2.group(1)
            if m2.group(3):
                try:
                    msg["data"] = _parse_mi_tuple(m2.group(3))
                except Exception:
                    msg["data"] = {}
    elif prefix == "*":  # async exec record
        m2 = re.match(r'^(\w+)(,(.*))?$', rest, re.DOTALL)
        if m2:
            msg["type"] = "exec"
            msg["class"] = m2.group(1)
            if m2.group(3):
                try:
                    msg["data"] = _parse_mi_tuple(m2.group(3))
                except Exception:
                    msg["data"] = {}
    elif prefix == "~":  # console stream
        msg["type"] = "console"
        msg["text"] = rest.strip('"').replace("\\n", "\n").replace('\\"', '"')
    elif prefix == "&":  # log stream
        msg["type"] = "log"
        msg["text"] = rest.strip('"')
    elif prefix == "=":  # notify record
        m2 = re.match(r'^(\w+)(,(.*))?$', rest, re.DOTALL)
        if m2:
            msg["type"] = "notify"
            msg["class"] = m2.group(1)
    else:
        msg["type"] = "raw"
        msg["text"] = line

    return msg


# ── DebugSession ──────────────────────────────────────────────────────────────

class DebugSession:
    """Manages one OpenOCD + GDB MI subprocess pair for a project.

    Thread model:
      - The session object is created/used from the asyncio event loop.
      - GDB stdout is read in a daemon thread (_reader_thread).
      - Parsed MI events go into _raw_q (threading.Queue) and are bridged
        to self.event_queue (asyncio.Queue) via _bridge_task.
    """

    def __init__(self, project_id: str, project_path: str) -> None:
        self.project_id = project_id
        self.project_path = project_path

        self._openocd: subprocess.Popen | None = None
        self._gdb: subprocess.Popen | None = None
        self._reader_thread: threading.Thread | None = None
        self._bridge_task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

        self._raw_q: queue.Queue[dict | None] = queue.Queue()
        self.event_queue: asyncio.Queue[dict] = asyncio.Queue()

        # Token counter for GDB MI commands
        self._token = 1
        self._pending: dict[int, asyncio.Future] = {}

        # Known breakpoints
        self._breakpoints: dict[int, dict] = {}
        self._bp_counter = 0

        # Current state
        self.halted = False
        self.running = False
        self.stopped_file: str | None = None
        self.stopped_line: int | None = None
        self.stopped_reason: str | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self, board: str = "bluepill_f103c8", probe: str = "ST-Link V2") -> dict:
        """Start OpenOCD and GDB, connect to target, return initial snapshot."""
        from schemas import DebugSnapshot, DebugState

        elf = _find_elf(self.project_path)
        if not elf:
            return self._error_snapshot("No firmware .elf found. Please build the project first.")

        openocd_bin = _find_openocd()
        gdb_bin = _find_gdb()
        interface_cfg = _probe_to_openocd_interface(probe)
        target_cfg = _board_to_openocd_target(board)
        scripts_dir = _find_openocd_scripts()

        # Build OpenOCD command
        ocd_cmd = [openocd_bin]
        if scripts_dir:
            ocd_cmd += ["-s", scripts_dir]
        ocd_cmd += [
            "-f", interface_cfg,
            "-f", target_cfg,
            "-c", "gdb_port 3333",
            "-c", "tcl_port disabled",
            "-c", "telnet_port disabled",
        ]

        log.info("Starting OpenOCD: %s", " ".join(ocd_cmd))
        try:
            self._openocd = subprocess.Popen(
                ocd_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except FileNotFoundError:
            return self._error_snapshot(
                f"openocd not found at '{openocd_bin}'. "
                "Install it via PlatformIO: `pio pkg install --global tool-openocd`"
            )

        # Wait a moment for OpenOCD to start listening
        await asyncio.sleep(1.5)

        # Check if OpenOCD is still running
        if self._openocd.poll() is not None:
            out = self._openocd.stdout.read() if self._openocd.stdout else ""
            return self._error_snapshot(
                f"OpenOCD exited early (code {self._openocd.returncode}). "
                f"Is the board connected and probe configured?\n\nOutput:\n{out[:500]}"
            )

        # Spawn GDB
        gdb_cmd = [
            gdb_bin,
            "--interpreter=mi2",
            "--quiet",
            str(elf),
        ]
        log.info("Starting GDB: %s", " ".join(gdb_cmd))
        try:
            self._gdb = subprocess.Popen(
                gdb_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError:
            await self._kill_openocd()
            return self._error_snapshot(
                f"GDB not found at '{gdb_bin}'. "
                "Ensure arm-none-eabi-gdb is installed or build the project to install the toolchain."
            )

        self._loop = asyncio.get_event_loop()

        # Start reader thread
        self._reader_thread = threading.Thread(
            target=self._reader, daemon=True, name=f"gdb-reader-{self.project_id}"
        )
        self._reader_thread.start()

        # Start asyncio bridge
        self._bridge_task = asyncio.create_task(self._bridge())

        # Connect GDB to OpenOCD
        try:
            await self._cmd("target extended-remote :3333", timeout=8.0)
            await self._cmd("monitor reset halt", timeout=5.0)
        except asyncio.TimeoutError:
            await self.stop()
            return self._error_snapshot(
                "Timed out connecting to OpenOCD. "
                "Check that the board is connected and the probe is detected."
            )
        except Exception as e:
            await self.stop()
            return self._error_snapshot(f"GDB connection error: {e}")

        self.halted = True
        self.running = False

        return await self._build_snapshot()

    async def stop(self) -> None:
        """Gracefully shut down GDB and OpenOCD."""
        if self._gdb and self._gdb.poll() is None:
            try:
                self._gdb.stdin.write("-gdb-exit\n")
                self._gdb.stdin.flush()
                await asyncio.sleep(0.5)
            except Exception:
                pass
            try:
                self._gdb.terminate()
                self._gdb.wait(timeout=3)
            except Exception:
                self._gdb.kill()

        self._raw_q.put(None)  # sentinel to stop reader
        if self._bridge_task and not self._bridge_task.done():
            self._bridge_task.cancel()

        await self._kill_openocd()
        remove_session(self.project_id)
        log.info("Debug session stopped for project %s", self.project_id)

    # ── Breakpoints ───────────────────────────────────────────────────────────

    async def set_breakpoint(self, file: str, line: int) -> dict:
        """Insert a breakpoint and return its id/file/line."""
        resp = await self._cmd(f'-break-insert {file}:{line}')
        bp_data = resp.get("data", {}).get("bkpt", {})
        bp_id = int(bp_data.get("number", self._bp_counter + 1))
        self._bp_counter = max(self._bp_counter, bp_id)
        bp = {"id": bp_id, "file": file, "line": line, "enabled": True}
        self._breakpoints[bp_id] = bp
        return bp

    async def remove_breakpoint(self, bp_id: int) -> None:
        """Remove a breakpoint by id."""
        await self._cmd(f"-break-delete {bp_id}")
        self._breakpoints.pop(bp_id, None)

    # ── Execution control ─────────────────────────────────────────────────────

    async def continue_exec(self) -> None:
        self.halted = False
        self.running = True
        self._write("-exec-continue\n")

    async def step_over(self) -> None:
        self._write("-exec-next\n")

    async def step_into(self) -> None:
        self._write("-exec-step\n")

    async def step_out(self) -> None:
        self._write("-exec-finish\n")

    # ── Snapshot ──────────────────────────────────────────────────────────────

    async def snapshot(self) -> dict:
        """Read registers, call stack, and locals and return a snapshot dict."""
        return await self._build_snapshot()

    async def _build_snapshot(self) -> dict:
        registers = await self._read_registers()
        frames = await self._read_stack()
        locals_ = await self._read_locals()
        bps = [{"id": v["id"], "file": v["file"], "line": v["line"], "enabled": v["enabled"]}
               for v in self._breakpoints.values()]
        return {
            "state": {
                "running": self.running,
                "halted": self.halted,
                "file": self.stopped_file,
                "line": self.stopped_line,
                "reason": self.stopped_reason,
            },
            "registers": registers,
            "call_stack": frames,
            "locals": locals_,
            "breakpoints": bps,
            "error": None,
        }

    def _error_snapshot(self, msg: str) -> dict:
        return {
            "state": {"running": False, "halted": False, "file": None, "line": None, "reason": None},
            "registers": [],
            "call_stack": [],
            "locals": [],
            "breakpoints": [],
            "error": msg,
        }

    # ── GDB register / stack / locals readers ─────────────────────────────────

    async def _read_registers(self) -> list[dict]:
        numbers = list(_ARM_REGISTER_NAMES.keys())
        num_list = " ".join(str(n) for n in numbers)
        try:
            resp = await self._cmd(f"-data-list-register-values x {num_list}", timeout=3.0)
            vals = resp.get("data", {}).get("register-values", [])
            if not isinstance(vals, list):
                return []
            regs = []
            for v in vals:
                if not isinstance(v, dict):
                    continue
                try:
                    number = int(v.get("number", -1))
                    name = _ARM_REGISTER_NAMES.get(number, f"r{number}")
                    value = str(v.get("value", "0x0"))
                    regs.append({"name": name, "number": number, "value": value})
                except Exception:
                    continue
            return regs
        except Exception:
            return []

    async def _read_stack(self) -> list[dict]:
        try:
            resp = await self._cmd("-stack-list-frames 0 10", timeout=3.0)
            stack_data = resp.get("data", {}).get("stack", [])
            if not isinstance(stack_data, list):
                return []
            frames = []
            for item in stack_data:
                if isinstance(item, dict):
                    frame = item.get("frame", item)
                elif isinstance(item, str):
                    continue
                else:
                    frame = item
                try:
                    frames.append({
                        "level": int(frame.get("level", 0)),
                        "function": frame.get("func", frame.get("function", "?")),
                        "file": frame.get("file"),
                        "line": int(frame.get("line", 0)) if frame.get("line") else None,
                        "address": frame.get("addr"),
                    })
                except Exception:
                    continue
            return frames
        except Exception:
            return []

    async def _read_locals(self) -> list[dict]:
        try:
            resp = await self._cmd("-stack-list-locals --simple-values", timeout=3.0)
            local_data = resp.get("data", {}).get("locals", [])
            if not isinstance(local_data, list):
                return []
            locals_ = []
            for item in local_data:
                if not isinstance(item, dict):
                    continue
                locals_.append({
                    "name": item.get("name", "?"),
                    "value": item.get("value", "?"),
                    "type": item.get("type", ""),
                })
            return locals_
        except Exception:
            return []

    # ── Internal GDB MI communication ─────────────────────────────────────────

    def _write(self, text: str) -> None:
        if self._gdb and self._gdb.poll() is None and self._gdb.stdin:
            try:
                self._gdb.stdin.write(text)
                self._gdb.stdin.flush()
            except Exception as e:
                log.warning("GDB write error: %s", e)

    async def _cmd(self, mi_cmd: str, timeout: float = 5.0) -> dict:
        """Send a MI command with a token, await its ^done response."""
        tok = self._token
        self._token += 1
        fut: asyncio.Future = self._loop.create_future()
        self._pending[tok] = fut
        self._write(f"{tok}{mi_cmd}\n")
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(tok, None)
            raise
        except Exception:
            self._pending.pop(tok, None)
            raise

    def _reader(self) -> None:
        """Read GDB MI stdout line-by-line in a background thread."""
        assert self._gdb is not None
        try:
            for line in self._gdb.stdout:
                parsed = _parse_mi_line(line.rstrip())
                if parsed:
                    self._raw_q.put(parsed)
        except Exception as e:
            log.warning("GDB reader exited: %s", e)
        finally:
            self._raw_q.put(None)  # EOF sentinel

    async def _bridge(self) -> None:
        """Bridge raw_q → asyncio event_queue; resolve pending futures."""
        loop = asyncio.get_event_loop()
        while True:
            msg = await loop.run_in_executor(None, self._raw_q.get)
            if msg is None:
                break
            await self._dispatch(msg)

    async def _dispatch(self, msg: dict) -> None:
        """Handle one parsed GDB MI message."""
        t = msg.get("type")
        tok = msg.get("token")

        # Resolve a pending command future
        if tok is not None and tok in self._pending:
            fut = self._pending.pop(tok)
            if not fut.done():
                fut.set_result(msg)

        # Target stopped
        if t == "exec" and msg.get("class") == "stopped":
            data = msg.get("data", {})
            self.halted = True
            self.running = False
            self.stopped_reason = data.get("reason")

            frame = data.get("frame", {})
            if isinstance(frame, dict):
                self.stopped_file = frame.get("fullname") or frame.get("file")
                line_str = frame.get("line")
                self.stopped_line = int(line_str) if line_str else None

            # Build and push a snapshot event
            try:
                snap = await self._build_snapshot()
                await self.event_queue.put({"type": "stopped", "snapshot": snap})
            except Exception:
                await self.event_queue.put({"type": "stopped", "snapshot": {}})

        # Target running
        elif t == "exec" and msg.get("class") == "running":
            self.halted = False
            self.running = True
            await self.event_queue.put({"type": "running"})

        # Console / log text → surface as debug_log event
        elif t in ("console", "log"):
            await self.event_queue.put({"type": "log", "text": msg.get("text", "")})

    async def _kill_openocd(self) -> None:
        if self._openocd and self._openocd.poll() is None:
            try:
                self._openocd.terminate()
                await asyncio.sleep(0.3)
                if self._openocd.poll() is None:
                    self._openocd.kill()
            except Exception:
                pass
