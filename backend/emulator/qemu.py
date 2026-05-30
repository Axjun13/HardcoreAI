"""QEMU lifecycle + serial SSE fan-out.

Python port of emulator-service/QEMU/qemu.go. Spawns a single STM32 QEMU
instance with a gdbstub on :3333 and USART2 streamed over TCP :4444, and
broadcasts that serial output to any number of SSE subscribers.
"""

from __future__ import annotations

import queue
import socket
import subprocess
import threading
import time

# QEMU's USART2 is exposed as a TCP server on this port; we connect to it and
# fan the bytes out to /qemu/stream subscribers.
_SERIAL_HOST = "127.0.0.1"
_SERIAL_PORT = 4444
_GDB_PORT = 3333


class QemuRunner:
    """Owns the QEMU process and the subscriber set (module-level singleton)."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._clients: set[queue.Queue[str]] = set()
        self._lock = threading.Lock()

    def subscribe(self) -> "queue.Queue[str]":
        ch: queue.Queue[str] = queue.Queue(maxsize=100)
        with self._lock:
            self._clients.add(ch)
        return ch

    def unsubscribe(self, ch: "queue.Queue[str]") -> None:
        with self._lock:
            self._clients.discard(ch)

    def _broadcast(self, msg: str) -> None:
        with self._lock:
            clients = list(self._clients)
        for ch in clients:
            try:
                ch.put_nowait(msg)
            except queue.Full:
                pass  # drop for slow consumers, matching the Go default-case

    def run(self, firmware_path: str) -> str:
        """(Re)start QEMU loading `firmware_path`. Returns the status marker."""
        if self._proc is not None and self._proc.poll() is None:
            self._proc.kill()
            self._proc.wait()

        self._proc = subprocess.Popen(
            [
                "qemu-system-arm",
                "-M", "olimex-stm32-h405",
                "-kernel", firmware_path,
                "-gdb", f"tcp::{_GDB_PORT}",
                "-display", "none",
                "-serial", "null",  # USART1 -> null
                "-serial", f"tcp:{_SERIAL_HOST}:{_SERIAL_PORT},server,nowait",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        threading.Thread(target=self._pump_serial, daemon=True).start()
        return "QEMU Started"

    def _pump_serial(self) -> None:
        """Connect to QEMU's serial TCP server and broadcast each line."""
        conn: socket.socket | None = None
        for _ in range(50):  # retry for ~5s while QEMU opens the port
            try:
                conn = socket.create_connection((_SERIAL_HOST, _SERIAL_PORT), timeout=1.0)
                break
            except OSError:
                time.sleep(0.1)
        if conn is None:
            return
        try:
            buf = b""
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    self._broadcast(line.decode("utf-8", "replace").rstrip("\r"))
        except OSError:
            pass
        finally:
            conn.close()


# Single shared instance, mirroring the Go package-level globals.
runner = QemuRunner()
