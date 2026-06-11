"""Project helpers shared across routers."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlmodel import Session

from db.models import ProjectRow
from schemas import ProjectOut


def default_files(project_name: str) -> list[tuple[str, str, str]]:
    """(path, language, content) tuples for a new project."""
    main_c = f"""/* Firmware for {project_name}
 * Generate component-aware code from the Workbench tab.
 */
#include "stm32f1xx_hal.h"

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
    return [
        ("src/main.c", "c", main_c),
        ("README.md", "markdown", readme),
    ]


def project_out(project: ProjectRow) -> ProjectOut:
    return ProjectOut(
        id=str(project.id),
        name=project.name,
        description=project.description or "",
        path=project.path,
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
