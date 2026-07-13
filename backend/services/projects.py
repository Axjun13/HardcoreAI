"""Project helpers shared across routers."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException
from sqlmodel import Session

from db.models import ProjectRow
from schemas import ProjectOut

# Directories we never surface in the working-directory file tree.
# Only .git is hidden — everything else (incl. .pio build artifacts) is shown so
# the IDE reflects the real local working directory.
_TREE_SKIP_DIRS = {".git"}

# Extensions treated as binary (non-openable as text). Content for these is not
# fetched on click; the editor shows a placeholder instead.
_BINARY_EXTS = {
    ".o", ".a", ".so", ".elf", ".bin", ".hex", ".map", ".d", ".obj", ".lib",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".pdf", ".zip", ".gz",
    ".tar", ".7z", ".exe", ".dll", ".dylib", ".pyc", ".woff", ".woff2", ".ttf",
}


def _is_binary_path(name: str) -> bool:
    return Path(name).suffix.lower() in _BINARY_EXTS


def build_disk_tree(root: Path) -> list[dict]:
    """Walk the real working directory and return a nested file tree.

    Includes generated/untracked files (e.g. .pio) and binaries. Binaries are
    marked ``isBinary`` so the frontend can avoid fetching their content. Only
    ``.git`` is skipped. Returns folders-first, alphabetically sorted nodes.
    """
    if not root.exists() or not root.is_dir():
        return []

    def walk(dir_path: Path, rel_prefix: str) -> list[dict]:
        nodes: list[dict] = []
        try:
            entries = sorted(
                os.scandir(dir_path),
                key=lambda e: (not e.is_dir(), e.name.lower()),
            )
        except OSError:
            return nodes
        for entry in entries:
            rel = f"{rel_prefix}/{entry.name}"
            if entry.is_dir(follow_symlinks=False):
                if entry.name in _TREE_SKIP_DIRS:
                    continue
                nodes.append({
                    "name": entry.name,
                    "path": rel,
                    "isFolder": True,
                    "children": walk(Path(entry.path), rel),
                })
            elif entry.is_file(follow_symlinks=False):
                nodes.append({
                    "name": entry.name,
                    "path": rel,
                    "isFolder": False,
                    "isBinary": _is_binary_path(entry.name),
                })
        return nodes

    return walk(root, "")


def default_files(project_name: str, board_id: str | None = None) -> list[tuple[str, str, str]]:
    """(path, language, content) tuples for a new project."""
    from boards.registry import registry
    device = registry.get(board_id) if board_id else None
    device = device or registry.default()

    main_c = f"""/* Firmware for {project_name}
 * Generate component-aware code from the Workbench tab.
 */
 #include "{device.hal_header}"


int main(void) {{
    HAL_Init();

    while (1) {{
        /* Wire components, then press "Generate firmware". */
    }}
}}
"""
    readme = (
        f"# {project_name}\n\n"
        "Hardware notes and firmware plan.\n\n"
        "## Workflow\n\n"
        "1. Place components on the **Workbench**.\n"
        "2. Click two pins to wire them together.\n"
        "3. Use **Generate firmware** to turn the netlist into STM32 HAL code.\n"
    )
    gitignore = (
        "# Build artifacts\n"
        ".pio/\n"
        ".pioenvs/\n"
        ".piolibdeps/\n"
        ".platformio/\n"
        "build/\n"
        "*.o\n"
        "*.elf\n"
        "*.bin\n"
        "*.hex\n"
        "\n"
        "# Secrets / local config\n"
        ".env\n"
        ".env.*\n"
        "!.env.example\n"
        "\n"
        "# Editor / OS\n"
        ".vscode/\n"
        ".DS_Store\n"
    )
    platformio_ini = f"""[env:{device.id}]
platform = ststm32
board = {device.id}
framework = stm32cube
"""

    return [
    ("src/main.c", "c", main_c),
    ("README.md", "markdown", readme),
    (".gitignore", "ignore", gitignore),
    ("platformio.ini", "ini", platformio_ini),
]


def project_out(project: ProjectRow) -> ProjectOut:
    return ProjectOut(
        id=str(project.id),
        name=project.name,
        description=project.description or "",
        path=project.path,
        board_id=project.board_id,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def get_project_or_404(session: Session, project_id: str, user_id: str) -> ProjectRow:
    try:
        pid = int(project_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=404, detail="Project not found")
    project = session.get(ProjectRow, pid)
    if not project or project.user_id != UUID(user_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return project
