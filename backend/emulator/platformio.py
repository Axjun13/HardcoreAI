"""PlatformIO build/flash invocation.

Python port of emulator-service/PlatformIO/platformio.go. Locates the `pio`
executable, optionally syncs incoming files into the project, and runs the
build, returning combined stdout+stderr alongside a success flag.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


class PlatformIOError(RuntimeError):
    pass


def _platformio_candidates() -> list[str]:
    candidates: list[str] = []
    configured = os.environ.get("PLATFORMIO_CMD")
    if configured:
        candidates.append(configured)
    candidates += ["pio", "platformio"]
    home = Path.home()
    candidates += [
        str(home / ".platformio/penv/bin/pio"),
        str(home / ".platformio/penv/bin/platformio"),
        str(home / ".platformio/penv/Scripts/pio.exe"),
        str(home / ".platformio/penv/Scripts/platformio.exe"),
    ]
    return candidates


def platformio_executable() -> str:
    for candidate in _platformio_candidates():
        if not candidate:
            continue
        # A bare name -> resolve on PATH; a path -> must exist as a file.
        if os.path.basename(candidate) == candidate:
            resolved = shutil.which(candidate)
            if resolved:
                return resolved
            continue
        if os.path.isfile(candidate):
            return candidate
    raise PlatformIOError(
        "PlatformIO executable not found. Install PlatformIO Core, add "
        "~/.platformio/penv/bin to PATH, or set PLATFORMIO_CMD to the full "
        "pio executable path."
    )


def _run_pio(project_path: str, *args: str) -> tuple[str, bool]:
    """Run a pio subcommand in `project_path`. Returns (combined_output, ok)."""
    pio = platformio_executable()
    result = subprocess.run(
        [pio, *args],
        cwd=project_path,
        capture_output=True,
        text=True,
    )
    output = (result.stdout or "") + (result.stderr or "")
    return output, result.returncode == 0


def sync_files(project_path: str, files: list[dict]) -> None:
    """Write incoming {path, content} files into the project tree."""
    for f in files:
        rel = f.get("path")
        if not rel:
            continue
        full = Path(project_path) / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(f.get("content", ""))


def build_project(project_path: str) -> tuple[str, bool]:
    return _run_pio(project_path, "run")


def flash_project(project_path: str) -> tuple[str, bool]:
    return _run_pio(project_path, "run", "-t", "upload")
