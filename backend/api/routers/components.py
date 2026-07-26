"""Component catalogue listing."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlmodel import select

from core.security import get_current_user_id
from db.models import Component
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

_MAX_IMAGE_BYTES = 5 * 1024 * 1024
_MAX_IMAGE_REDIRECTS = 3


def _image_url_target(url: str) -> tuple[str, int]:
    """Parse an HTTP image URL into the host and effective port."""
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise HTTPException(status_code=400, detail="Invalid component image URL")

    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid component image URL") from exc
    return parsed.hostname, port


def _require_public_addresses(addresses: list[tuple]) -> None:
    """Reject DNS results that could route the image request to a local service."""
    if not addresses:
        raise HTTPException(status_code=502, detail="Component image host could not be resolved")
    for address in addresses:
        host = str(address[4][0]).split("%", 1)[0]
        try:
            is_global = ipaddress.ip_address(host).is_global
        except ValueError as exc:
            raise HTTPException(status_code=502, detail="Component image host returned an invalid address") from exc
        if not is_global:
            raise HTTPException(status_code=400, detail="Component image host is not public")


async def _require_public_image_url(url: str) -> None:
    """Reject local/private destinations before the backend fetches an image."""
    hostname, port = _image_url_target(url)
    try:
        addresses = await asyncio.to_thread(
            socket.getaddrinfo,
            hostname,
            port,
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise HTTPException(status_code=502, detail="Component image host could not be resolved") from exc
    _require_public_addresses(addresses)


async def _fetch_component_image(url: str) -> tuple[bytes, str]:
    """Fetch a bounded image while validating every redirect destination."""
    current_url = url
    timeout = httpx.Timeout(12.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        for redirect_count in range(_MAX_IMAGE_REDIRECTS + 1):
            await _require_public_image_url(current_url)
            try:
                async with client.stream(
                    "GET",
                    current_url,
                    headers={
                        "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
                        "User-Agent": "HardcoreAI/0.3 component-image-proxy",
                    },
                ) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location or redirect_count >= _MAX_IMAGE_REDIRECTS:
                            raise HTTPException(status_code=502, detail="Component image redirected too many times")
                        current_url = urljoin(current_url, location)
                        continue

                    if response.status_code != 200:
                        raise HTTPException(status_code=502, detail="Component image host rejected the request")

                    media_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    if not media_type.startswith("image/") or media_type == "image/svg+xml":
                        raise HTTPException(status_code=415, detail="Component thumbnail is not a supported image")

                    declared_size = response.headers.get("content-length")
                    if declared_size and declared_size.isdigit() and int(declared_size) > _MAX_IMAGE_BYTES:
                        raise HTTPException(status_code=413, detail="Component image is too large")

                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > _MAX_IMAGE_BYTES:
                            raise HTTPException(status_code=413, detail="Component image is too large")
                    return bytes(content), media_type
            except HTTPException:
                raise
            except httpx.HTTPError as exc:
                raise HTTPException(status_code=502, detail="Component image could not be loaded") from exc

    raise HTTPException(status_code=502, detail="Component image could not be loaded")


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


@router.get("/api/components/{component_id}/image")
async def get_component_image(component_id: str) -> Response:
    """Serve a catalogue thumbnail from this origin to avoid browser CORP failures."""
    with db_session() as session:
        component = session.exec(select(Component).where(Component.slug == component_id)).first()
    if not component or not component.thumbnail.startswith(("https://", "http://")):
        raise HTTPException(status_code=404, detail="Component image not found")

    content, media_type = await _fetch_component_image(component.thumbnail)
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Content-Type-Options": "nosniff",
        },
    )


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
