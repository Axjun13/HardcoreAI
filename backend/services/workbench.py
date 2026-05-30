"""Workbench (de)serialisation.

On the wire the frontend uses string ids ("part-<uuid>", "wire-<uuid>").
In Postgres we use integer primary keys. We expose the integer id as a string
so the frontend code is unchanged, and resolve them back on save.
"""

from __future__ import annotations

from sqlmodel import Session, select

from core.config import now_utc
from db.models import (
    Component,
    ProjectComponentRow,
    ProjectConnectionRow,
    ProjectRow,
)
from schemas import WorkbenchState
from services.catalogue import component_id_by_slug


def read_workbench(session: Session, project: ProjectRow) -> WorkbenchState:
    placements = session.exec(
        select(ProjectComponentRow)
        .where(ProjectComponentRow.project_id == project.id)
        .order_by(ProjectComponentRow.id)
    ).all()
    connections = session.exec(
        select(ProjectConnectionRow)
        .where(ProjectConnectionRow.project_id == project.id)
        .order_by(ProjectConnectionRow.id)
    ).all()

    slug_by_id = {c.id: c.slug for c in session.exec(select(Component)).all()}

    placed = [
        {
            "id": str(p.id),
            "definition_id": slug_by_id.get(p.component_id, ""),
            "display_name": p.instance_name,
            "x": p.x,
            "y": p.y,
            "rotation": p.rotation,
            "config": p.config or {},
        }
        for p in placements
    ]
    wires = [
        {
            "id": str(c.id),
            "from": {"componentId": str(c.from_instance_id), "pinName": c.from_pin_label},
            "to": {"componentId": str(c.to_instance_id), "pinName": c.to_pin_label},
            "label": c.label or "",
            "color": c.color or "",
        }
        for c in connections
    ]
    return WorkbenchState(
        placed_components=placed,
        wires=wires,
        viewport=project.viewport or {"x": 0, "y": 0, "zoom": 1},
    )


def write_workbench(session: Session, project: ProjectRow, state: WorkbenchState) -> None:
    """Replace the project's placed components and connections with `state`.

    The frontend may send brand-new instances (ids generated client-side) or
    existing ones (numeric ids from a previous load). We rebuild the rows and
    map client ids -> database ids so connections resolve correctly.
    """
    slug_to_component = component_id_by_slug(session)

    # Drop existing placement + connection rows for this project.
    for row in session.exec(
        select(ProjectConnectionRow).where(ProjectConnectionRow.project_id == project.id)
    ).all():
        session.delete(row)
    for row in session.exec(
        select(ProjectComponentRow).where(ProjectComponentRow.project_id == project.id)
    ).all():
        session.delete(row)
    session.flush()

    # Re-insert placements, remembering the client id -> new db id mapping.
    id_map: dict[str, int] = {}
    used_names: set[str] = set()
    for item in state.placed_components:
        component_id = slug_to_component.get(item.get("definition_id", ""))
        if component_id is None:
            continue  # unknown component slug — skip rather than crash

        base_name = item.get("display_name") or "Component"
        instance_name = base_name
        counter = 1
        while instance_name in used_names:
            instance_name = f"{base_name}_{counter}"
            counter += 1
        used_names.add(instance_name)

        placement = ProjectComponentRow(
            project_id=project.id,
            component_id=component_id,
            instance_name=instance_name,
            x=float(item.get("x", 480)),
            y=float(item.get("y", 280)),
            rotation=int(item.get("rotation", 0) or 0),
            config=item.get("config", {}) or {},
        )
        session.add(placement)
        session.flush()  # assigns placement.id
        id_map[str(item.get("id"))] = placement.id

    # Re-insert connections, translating endpoint ids through the map.
    for wire in state.wires:
        src = id_map.get(str(wire.get("from", {}).get("componentId")))
        dst = id_map.get(str(wire.get("to", {}).get("componentId")))
        if src is None or dst is None:
            continue  # endpoint references a component that was not placed
        session.add(
            ProjectConnectionRow(
                project_id=project.id,
                from_instance_id=src,
                from_pin_label=wire.get("from", {}).get("pinName", ""),
                to_instance_id=dst,
                to_pin_label=wire.get("to", {}).get("pinName", ""),
                label=wire.get("label") or "",
                color=wire.get("color") or "",
            )
        )

    project.viewport = state.viewport or {"x": 0, "y": 0, "zoom": 1}
    project.updated_at = now_utc()
    session.add(project)
