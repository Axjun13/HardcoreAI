"""Best-effort web discovery and durable catalogue enrichment for Research."""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import llm
from sqlmodel import Session, select

from db.models import Component
from rag.web_search import search_images, search_web

_VENDOR_NAMES = {
    "adafruit.com": "Adafruit",
    "digikey.com": "DigiKey",
    "digikey.in": "DigiKey",
    "mouser.com": "Mouser",
    "mouser.in": "Mouser",
    "seeedstudio.com": "Seeed Studio",
    "sparkfun.com": "SparkFun",
    "pololu.com": "Pololu",
    "waveshare.com": "Waveshare",
}


def _slug(value: str) -> str:
    return re.sub(r"(^-|-$)", "", re.sub(r"[^a-z0-9]+", "-", value.casefold()))[:80] or "component"


def _json_payload(text: str) -> Any:
    clean = (text or "").strip()
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", clean, flags=re.I | re.S)
    start = min((index for index in (clean.find("["), clean.find("{")) if index >= 0), default=-1)
    if start < 0:
        return []
    try:
        return json.loads(clean[start:])
    except json.JSONDecodeError:
        end = max(clean.rfind("]"), clean.rfind("}"))
        if end < start:
            return []
        try:
            return json.loads(clean[start:end + 1])
        except json.JSONDecodeError:
            return []


def parse_component_candidates(text: str) -> list[dict[str, Any]]:
    """Validate the deliberately small structured output expected from the LLM."""
    payload = _json_payload(text)
    items = payload.get("components", []) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []
    result: list[dict[str, Any]] = []
    for item in items[:10]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if len(name) < 2 or len(name) > 100:
            continue
        result.append({
            "name": name,
            "category": str(item.get("category") or "Component").strip()[:60],
            "description": str(item.get("description") or "Web-discovered component candidate.").strip()[:500],
            "aliases": [str(value).strip() for value in item.get("aliases", []) if str(value).strip()][:10],
            "library_ids": [str(value).strip() for value in item.get("library_ids", []) if str(value).strip()][:8],
            "search_query": str(item.get("search_query") or f"{name} embedded electronics module datasheet").strip()[:240],
        })
    return result


async def propose_component_candidates(
    *, goal: str, provider: str, existing_names: list[str]
) -> list[dict[str, Any]]:
    """Ask the selected model for exact parts before it writes user-facing prose."""
    response = await llm.complete(provider, [
        {
            "role": "system",
            "content": (
                "Choose the concrete, purchasable electronic modules/ICs needed for this embedded product. "
                "Return JSON only as {\"components\":[...]}. Each component needs name, category, a factual "
                "one-sentence description, aliases, known PlatformIO/Arduino library ids (or []), and a "
                "search_query. Prefer exact part numbers. Include required power, charging, sensing, display, "
                "storage, and interface parts—not generic concepts. Do not invent URLs, prices, or pinouts. "
                "Return 3-8 items. Existing catalogue names may be reused when suitable."
            ),
        },
        {
            "role": "user",
            "content": f"Product research:\n{goal[-6000:]}\n\nExisting catalogue:\n" + "\n".join(existing_names[:120]),
        },
    ])
    return parse_component_candidates(response)


def _vendor(url: str) -> str | None:
    host = urlparse(url).netloc.casefold().removeprefix("www.")
    return next((label for domain, label in _VENDOR_NAMES.items() if host == domain or host.endswith(f".{domain}")), None)


def _enrich_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    item = dict(candidate)
    try:
        query = item["search_query"]
        web_results = [result for result in search_web(query, num_results=6) if result.get("url")]
        image_results = [
            result for result in search_images(f"{item['name']} electronics module product", num_results=4)
            if str(result.get("image", "")).startswith(("https://", "http://"))
        ]
        source = web_results[0] if web_results else {}
        datasheet = next(
            (result["url"] for result in web_results if ".pdf" in result["url"].casefold() or "datasheet" in (result.get("title", "") + result.get("snippet", "")).casefold()),
            None,
        )
        buy_links = []
        for result in web_results:
            vendor = _vendor(result["url"])
            if vendor and not any(link["vendor"] == vendor for link in buy_links):
                buy_links.append({"vendor": vendor, "url": result["url"]})
        item.update({
            "thumbnail": image_results[0]["image"] if image_results else "generic",
            "image_source_url": image_results[0].get("url") if image_results else None,
            "datasheet_url": datasheet,
            "buy_links": buy_links,
            "source_url": source.get("url") or (image_results[0].get("url") if image_results else None),
            "source_name": source.get("title") or (image_results[0].get("title") if image_results else None),
        })
    except Exception as exc:
        item.update({
            "thumbnail": "generic",
            "datasheet_url": None,
            "buy_links": [],
            "source_url": None,
            "source_name": None,
            "discovery_warning": str(exc)[:300],
        })
    return item


def enrich_candidates_from_web(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach source, datasheet, purchase, and product-image URLs from live search."""
    if not candidates:
        return []
    with ThreadPoolExecutor(max_workers=min(6, len(candidates))) as executor:
        return list(executor.map(_enrich_candidate, candidates))


def upsert_discovered_components(session: Session, candidates: list[dict[str, Any]]) -> list[str]:
    """Persist discoveries globally; preserve richer curated metadata when present."""
    existing = session.exec(select(Component)).all()
    by_slug = {component.slug: component for component in existing}
    by_name = {component.name.casefold(): component for component in existing}
    slugs: list[str] = []
    now = datetime.now(timezone.utc)
    for candidate in candidates:
        slug = _slug(candidate["name"])
        component = by_slug.get(slug) or by_name.get(candidate["name"].casefold())
        if component is None:
            component = Component(
                slug=slug,
                name=candidate["name"],
                category=candidate.get("category") or "Component",
                description=candidate.get("description") or "Web-discovered component candidate.",
                visual_type="generic",
                thumbnail=candidate.get("thumbnail") or "generic",
                width=140,
                height=100,
                aliases=candidate.get("aliases") or [],
                library_ids=candidate.get("library_ids") or [],
                buy_links=candidate.get("buy_links") or [],
                datasheet_url=candidate.get("datasheet_url"),
                source_url=candidate.get("source_url"),
                source_name=candidate.get("source_name"),
                image_source_url=candidate.get("image_source_url"),
                discovery_query=candidate.get("search_query"),
                discovered_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add(component)
            by_slug[slug] = component
            by_name[component.name.casefold()] = component
        else:
            if component.thumbnail in {"", "generic", "sensor", "module", "board"} and candidate.get("thumbnail") not in {None, "", "generic"}:
                component.thumbnail = candidate["thumbnail"]
            if not component.datasheet_url and candidate.get("datasheet_url"):
                component.datasheet_url = candidate["datasheet_url"]
            if not component.buy_links and candidate.get("buy_links"):
                component.buy_links = candidate["buy_links"]
            component.aliases = list(dict.fromkeys([*(component.aliases or []), *(candidate.get("aliases") or [])]))
            component.source_url = component.source_url or candidate.get("source_url")
            component.source_name = component.source_name or candidate.get("source_name")
            component.image_source_url = component.image_source_url or candidate.get("image_source_url")
            component.discovery_query = candidate.get("search_query") or component.discovery_query
            component.discovered_at = component.discovered_at or now
            component.updated_at = now
            session.add(component)
            slug = component.slug
        slugs.append(slug)
    session.commit()
    return list(dict.fromkeys(slugs))
