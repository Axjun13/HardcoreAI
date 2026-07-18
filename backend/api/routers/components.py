"""Component catalogue listing."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from core.security import get_current_user_id
from db.session import db_session
from schemas import ComponentDefinition
from services.catalogue import catalogue_index, load_catalogue
from services.component_resolution import (
    install_component_libraries,
    resolve_component_context,
    write_component_manifest,
)
from services.projects import get_project_or_404
from services.research import load_research_state, selected_component_ids
from services.workbench import read_workbench

router = APIRouter()


@router.get("/api/components", response_model=list[ComponentDefinition])
def list_components(q: str | None = None) -> list[ComponentDefinition]:
    with db_session() as session:
        catalogue = load_catalogue(session)
    if not q:
        return catalogue
    term = q.casefold()
    return [
        component
        for component in catalogue
        if term in component.name.casefold()
        or term in component.category.casefold()
        or term in component.description.casefold()
        or any(term in alias.casefold() for alias in component.aliases)
    ]


@router.get("/api/components/schema")
def component_schema() -> dict[str, Any]:
    """Frontend/research contract for component catalogue rows."""
    return {
        "component": {
            "id": "catalogue row id",
            "slug": "stable frontend id",
            "name": "display name",
            "category": "sensor/display/actuator/controller/etc.",
            "description": "short usage notes",
            "thumbnail": "remote product image URL or a local fallback identifier",
            "library_name": "legacy single library id/name",
            "library_ids": ["curated library ids to install"],
            "datasheet_url": "manufacturer/reference URL",
            "buy_links": [{"vendor": "Vendor", "url": "https://...", "sku": "optional"}],
            "aliases": ["searchable alternate part names"],
            "source_url": "web page used to discover/enrich this row",
            "source_name": "human-readable discovery source",
            "image_source_url": "page attributed as the remote image source",
            "discovery_query": "search query used by Research",
            "discovered_at": "timestamp for dynamically added catalogue rows",
            "verified_at": "timestamp for a later human/curation verification",
            "pins": "see pin table",
        },
        "pin": {
            "component_id": "foreign key to component",
            "name": "schematic pin name used by workbench wires",
            "label": "human pin label shown in UI",
            "role": "vcc/gnd/gpio/i2c-sda/spi-mosi/etc.",
            "voltage": "nominal voltage when known",
            "capabilities": "free-form capability tags",
        },
    }


@router.get("/api/projects/{project_id}/components/context")
def get_project_component_context(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Resolve selected components into libraries, buy links, pins, and wires."""
    with db_session(user_id) as session:
        project = get_project_or_404(session, project_id, user_id)
        context = resolve_component_context(
            catalogue=catalogue_index(session),
            workbench=read_workbench(session, project).model_dump(),
            selected_component_ids=selected_component_ids(load_research_state(project_id)),
        )
    return context


@router.post("/api/projects/{project_id}/components/resolve")
def resolve_project_components(
    project_id: str,
    install_libraries: bool = False,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Persist an isolated component snapshot and optionally install libraries."""
    with db_session(user_id) as session:
        project = get_project_or_404(session, project_id, user_id)
        context = resolve_component_context(
            catalogue=catalogue_index(session),
            workbench=read_workbench(session, project).model_dump(),
            selected_component_ids=selected_component_ids(load_research_state(project_id)),
        )

    manifest = write_component_manifest(project_id, context)
    install_results = install_component_libraries(project_id, context) if install_libraries else []
    return {
        "success": True,
        "manifest": str(manifest),
        "context": context,
        "install_results": install_results,
    }
