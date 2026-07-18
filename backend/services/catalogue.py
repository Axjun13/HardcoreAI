"""Catalogue helpers — read components + pins from the database."""

from __future__ import annotations

from sqlmodel import Session, select

from db.models import Component, PinRow
from schemas import ComponentDefinition, Pin


def _json_list(value) -> list:
    if isinstance(value, list):
        return value
    return []


def load_catalogue(session: Session) -> list[ComponentDefinition]:
    components = session.exec(select(Component).order_by(Component.id)).all()
    pins = session.exec(select(PinRow).order_by(PinRow.id)).all()
    pins_by_component: dict[int, list[PinRow]] = {}
    for pin in pins:
        pins_by_component.setdefault(pin.component_id, []).append(pin)

    catalogue: list[ComponentDefinition] = []
    for component in components:
        catalogue.append(
            ComponentDefinition(
                id=component.slug,
                name=component.name,
                category=component.category,
                description=component.description or "",
                visual_type=component.visual_type,
                thumbnail=component.thumbnail,
                width=component.width,
                height=component.height,
                library_name=component.library_name,
                library_ids=_json_list(component.library_ids),
                buy_links=_json_list(component.buy_links),
                datasheet_url=component.datasheet_url,
                aliases=_json_list(component.aliases),
                source_url=component.source_url,
                source_name=component.source_name,
                image_source_url=component.image_source_url,
                discovery_query=component.discovery_query,
                discovered_at=component.discovered_at,
                verified_at=component.verified_at,
                protocols=_json_list(component.protocols),
                verification_sources=_json_list(component.verification_sources),
                pins=[
                    Pin(
                        name=p.name,
                        label=p.label,
                        side=p.side,
                        x=p.x,
                        y=p.y,
                        role=p.role,
                        voltage=p.voltage,
                        capabilities=p.capabilities,
                    )
                    for p in pins_by_component.get(component.id, [])
                ],
            )
        )
    return catalogue


def catalogue_index(session: Session) -> dict[str, ComponentDefinition]:
    return {definition.id: definition for definition in load_catalogue(session)}


def component_id_by_slug(session: Session) -> dict[str, int]:
    return {c.slug: c.id for c in session.exec(select(Component)).all() if c.id is not None}
