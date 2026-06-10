"""Library service — install, uninstall, and list embedded libraries for a project.

Libraries are installed by:
  1. Running `pio pkg install --library "<pio_name>"` in the project workspace.
  2. Adding the library to the [env] `lib_deps` section of platformio.ini.

For custom Git URLs, step 1 uses the URL directly and step 2 records the URL.
This makes the install idempotent: re-running `pio run` always resolves deps.

The service is intentionally structured so that install() can be wrapped in a
background thread + SSE stream later without any changes to this module.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from services.hardware import ensure_platformio, workspace_dir, ensure_platformio_ini, DEFAULT_BOARD

# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_REGISTRY_PATH = _DATA_DIR / "libraries.json"

_registry_cache: list[dict[str, Any]] | None = None


def load_registry() -> list[dict[str, Any]]:
    """Load the curated library catalogue from libraries.json (cached)."""
    global _registry_cache
    if _registry_cache is None:
        with open(_REGISTRY_PATH, encoding="utf-8") as f:
            _registry_cache = json.load(f)
    return _registry_cache


def get_library(library_id: str) -> dict[str, Any] | None:
    """Find a library in the registry by its id."""
    return next((lib for lib in load_registry() if lib["id"] == library_id), None)


def search_registry(query: str = "", category: str = "") -> list[dict[str, Any]]:
    """Filter the registry by an optional search query and/or category."""
    libs = load_registry()
    if category:
        libs = [lib for lib in libs if lib.get("category", "").lower() == category.lower()]
    if query:
        q = query.lower()
        libs = [
            lib for lib in libs
            if q in lib["name"].lower()
            or q in lib.get("description", "").lower()
            or q in lib.get("category", "").lower()
            or q in lib.get("author", "").lower()
        ]
    return libs


# ---------------------------------------------------------------------------
# platformio.ini helpers
# ---------------------------------------------------------------------------


def _read_ini(ini_path: Path) -> str:
    return ini_path.read_text(encoding="utf-8") if ini_path.exists() else ""


def _get_lib_deps(ini_content: str) -> list[str]:
    """Extract the current lib_deps entries from platformio.ini content."""
    match = re.search(r"lib_deps\s*=\s*(.*?)(?=\n\[|\Z)", ini_content, re.DOTALL)
    if not match:
        return []
    raw = match.group(1)
    # Each dep is either on the same line (comma-separated) or on indented continuation lines
    entries = re.split(r"[,\n]", raw)
    return [e.strip() for e in entries if e.strip()]


def _set_lib_deps(ini_content: str, deps: list[str]) -> str:
    """Write (or replace) lib_deps in platformio.ini content."""
    dep_block = "\n    ".join(deps) if deps else ""
    new_line = f"lib_deps =\n    {dep_block}" if deps else "lib_deps ="

    if re.search(r"lib_deps\s*=", ini_content):
        # Replace the existing lib_deps block
        updated = re.sub(
            r"lib_deps\s*=\s*(.*?)(?=\n\[|\Z)",
            new_line + "\n",
            ini_content,
            flags=re.DOTALL,
        )
        return updated
    else:
        # Append to the last [env:...] block
        return ini_content.rstrip() + f"\n{new_line}\n"


# ---------------------------------------------------------------------------
# Install / uninstall
# ---------------------------------------------------------------------------


def install_library(
    project_id: str,
    library_id: str | None = None,
    git_url: str | None = None,
) -> dict[str, Any]:
    """Install a library into the project workspace.

    Pass either a `library_id` (from the registry) or a `git_url` for custom
    libraries. Returns a dict with keys: success, message, dep_name.

    Structured so this function can be run in a thread for SSE streaming later.
    """
    workspace = workspace_dir(project_id)
    if not workspace.exists():
        return {"success": False, "message": "Workspace not found — open the project first."}

    # Resolve what we're installing
    dep_name: str | None = None
    if library_id:
        lib = get_library(library_id)
        if not lib:
            return {"success": False, "message": f"Library '{library_id}' not found in registry."}
        if lib.get("pio_name") is None:
            # e.g. STM32 HAL is bundled with the framework — nothing to install
            return {
                "success": True,
                "message": lib.get("note", "Library is included with the framework automatically."),
                "dep_name": None,
            }
        dep_name = lib["pio_name"]
    elif git_url:
        dep_name = git_url
    else:
        return {"success": False, "message": "Provide either library_id or git_url."}

    # Ensure platformio.ini exists
    ensure_platformio_ini(workspace, DEFAULT_BOARD)

    # Check if already installed
    ini_path = workspace / "platformio.ini"
    ini_content = _read_ini(ini_path)
    current_deps = _get_lib_deps(ini_content)
    if dep_name in current_deps:
        return {"success": True, "message": "Library is already installed.", "dep_name": dep_name}

    # Run pio pkg install
    try:
        pio = ensure_platformio()
    except RuntimeError as exc:
        return {"success": False, "message": f"PlatformIO unavailable: {exc}"}

    result = subprocess.run(
        [pio, "pkg", "install", "--library", dep_name, "-d", str(workspace)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        err = (result.stdout + result.stderr).strip()[-1000:]
        return {"success": False, "message": f"Install failed:\n{err}"}

    # Update platformio.ini lib_deps
    updated_deps = current_deps + [dep_name]
    new_ini = _set_lib_deps(ini_content, updated_deps)
    ini_path.write_text(new_ini, encoding="utf-8")

    return {"success": True, "message": f"Installed '{dep_name}' successfully.", "dep_name": dep_name}


def uninstall_library(project_id: str, library_id: str) -> dict[str, Any]:
    """Remove a library from the project's platformio.ini lib_deps."""
    workspace = workspace_dir(project_id)
    lib = get_library(library_id)
    if not lib:
        return {"success": False, "message": f"Library '{library_id}' not found in registry."}

    dep_name = lib.get("pio_name")
    if not dep_name:
        return {"success": False, "message": "This library cannot be uninstalled (bundled with framework)."}

    ini_path = workspace / "platformio.ini"
    if not ini_path.exists():
        return {"success": False, "message": "platformio.ini not found in workspace."}

    ini_content = _read_ini(ini_path)
    current_deps = _get_lib_deps(ini_content)
    if dep_name not in current_deps:
        return {"success": False, "message": "Library is not installed in this project."}

    updated_deps = [d for d in current_deps if d != dep_name]
    new_ini = _set_lib_deps(ini_content, updated_deps)
    ini_path.write_text(new_ini, encoding="utf-8")

    # Best-effort pio pkg uninstall (don't fail if it errors)
    try:
        pio = ensure_platformio()
        subprocess.run(
            [pio, "pkg", "uninstall", "--library", dep_name, "-d", str(workspace)],
            capture_output=True, text=True, timeout=60,
        )
    except Exception:
        pass

    return {"success": True, "message": f"Uninstalled '{dep_name}'.", "dep_name": dep_name}


def list_installed(project_id: str) -> list[dict[str, Any]]:
    """Return the libraries installed in this project (from platformio.ini lib_deps).

    Enriches each dep_name with registry metadata when available.
    """
    workspace = workspace_dir(project_id)
    ini_path = workspace / "platformio.ini"
    if not ini_path.exists():
        return []

    ini_content = _read_ini(ini_path)
    dep_names = _get_lib_deps(ini_content)

    registry = load_registry()
    pio_name_to_lib = {lib["pio_name"]: lib for lib in registry if lib.get("pio_name")}

    result: list[dict[str, Any]] = []
    for dep in dep_names:
        if dep in pio_name_to_lib:
            result.append({**pio_name_to_lib[dep], "installed": True})
        else:
            # Custom Git URL or unknown library — return minimal metadata
            result.append({
                "id": dep,
                "name": dep.split("/")[-1] if "/" in dep else dep,
                "description": "Custom library",
                "version": "custom",
                "author": "Unknown",
                "category": "Custom",
                "targets": [],
                "pio_name": dep,
                "installed": True,
            })
    return result
