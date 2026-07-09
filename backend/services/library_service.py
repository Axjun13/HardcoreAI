"""Library service — install, uninstall, and list embedded libraries for a project.

Libraries are registered as lib_deps in platformio.ini.  PlatformIO resolves
and downloads them automatically on the next `pio run` / build.  We do NOT run
`pio pkg install` here because that command requires a fully-configured [env:]
section and fails with ProjectEnvsNotAvailableError on fresh or partially-set-up
projects.  Writing to lib_deps is idempotent and always safe.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from services.hardware import workspace_dir, ensure_platformio_ini, DEFAULT_BOARD

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
            data = json.load(f)
        _registry_cache = data if isinstance(data, list) else []
    return _registry_cache


def get_library(library_id: str) -> dict[str, Any] | None:
    """Find a library in the registry by its id."""
    return next((lib for lib in load_registry() if lib["id"] == library_id), None)


def search_registry(query: str = "", category: str = "") -> list[dict[str, Any]]:
    """Filter the registry by an optional search query and/or category."""
    libs = load_registry()
    if category:
        libs = [lib for lib in libs if lib.get("category", "").lower() == category.lower()]
    q = query.lower().strip()
    if q:
        libs = [
            lib for lib in libs
            if q in lib["name"].lower()
            or q in lib.get("description", "").lower()
            or q in lib.get("category", "").lower()
            or q in lib.get("author", "").lower()
        ]
    return sorted(
        libs,
        key=lambda lib: (
            not lib["name"].lower().startswith(q) if q else False,
            lib["name"].lower(),
        ),
    )


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
    entries = re.split(r"[,\n]", raw)
    return [e.strip() for e in entries if e.strip()]


def _set_lib_deps(ini_content: str, deps: list[str]) -> str:
    """Write (or replace) lib_deps in platformio.ini content."""
    dep_block = "\n    ".join(deps) if deps else ""
    new_line = f"lib_deps =\n    {dep_block}" if deps else "lib_deps ="

    if re.search(r"lib_deps\s*=", ini_content):
        updated = re.sub(
            r"lib_deps\s*=\s*(.*?)(?=\n\[|\Z)",
            new_line + "\n",
            ini_content,
            flags=re.DOTALL,
        )
        return updated
    else:
        return ini_content.rstrip() + f"\n{new_line}\n"


# ---------------------------------------------------------------------------
# Install / uninstall
# ---------------------------------------------------------------------------


def install_library(
    project_id: str,
    library_id: str | None = None,
    git_url: str | None = None,
) -> dict[str, Any]:
    """Register a library in the project's platformio.ini lib_deps.

    Does NOT run `pio pkg install` — PlatformIO resolves lib_deps automatically
    on the next build, which avoids ProjectEnvsNotAvailableError on projects
    that haven't been built yet.
    """
    workspace = workspace_dir(project_id)
    if not workspace.exists():
        return {"success": False, "message": "Workspace not found — open the project first."}

    # Resolve dep identifier
    dep_name: str | None = None
    if library_id:
        lib = get_library(library_id)
        if not lib:
            return {"success": False, "message": f"Library '{library_id}' not found in registry."}
        if lib.get("pio_name") is None:
            # Bundled with the framework — nothing to add to lib_deps
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

    # Ensure platformio.ini exists with at least a minimal board env
    ensure_platformio_ini(workspace, DEFAULT_BOARD)

    ini_path = workspace / "platformio.ini"
    ini_content = _read_ini(ini_path)
    current_deps = _get_lib_deps(ini_content)

    if dep_name in current_deps:
        return {"success": True, "message": "Library is already installed.", "dep_name": dep_name}

    # Write dep into lib_deps — PIO will download it on next build
    updated_deps = current_deps + [dep_name]
    new_ini = _set_lib_deps(ini_content, updated_deps)
    ini_path.write_text(new_ini, encoding="utf-8")

    return {
        "success": True,
        "message": f"Added '{dep_name}' to lib_deps. It will be downloaded on the next build.",
        "dep_name": dep_name,
    }


def uninstall_library(project_id: str, library_id: str) -> dict[str, Any]:
    """Remove a library from the project's platformio.ini lib_deps."""
    workspace = workspace_dir(project_id)
    if not workspace.exists():
        return {"success": False, "message": "Workspace not found — open the project first."}

    lib = get_library(library_id)
    if not lib:
        return {"success": False, "message": f"Library '{library_id}' not found in registry."}

    dep_name = lib.get("pio_name")
    if not dep_name:
        return {"success": False, "message": "This library cannot be removed (bundled with the framework)."}

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

    return {"success": True, "message": f"Removed '{dep_name}' from lib_deps.", "dep_name": dep_name}


def list_installed(project_id: str) -> list[dict[str, Any]]:
    """Return libraries registered in this project's platformio.ini lib_deps."""
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