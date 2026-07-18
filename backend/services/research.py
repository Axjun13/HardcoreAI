"""Research/ideation state for component selection and final project context."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus
from uuid import uuid4

import llm
from schemas import ComponentDefinition
from services.component_resolution import context_to_markdown
from services.hardware import workspace_dir
from services.library_service import get_library, load_registry


def research_dir(project_id: str) -> Path:
    path = workspace_dir(project_id) / ".hardcoreai"
    path.mkdir(parents=True, exist_ok=True)
    return path


def research_state_path(project_id: str) -> Path:
    return research_dir(project_id) / "research_state.json"


def load_research_state(project_id: str) -> dict[str, Any]:
    path = research_state_path(project_id)
    if not path.exists():
        return normalize_research_state({
            "ideas": [],
            "summary": "",
            "recommendations": [],
            "selected_components": [],
            "decision_notes": "",
        })
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return normalize_research_state(data if isinstance(data, dict) else {})
    except Exception:
        return normalize_research_state({})


def save_research_state(project_id: str, state: dict[str, Any]) -> Path:
    path = research_state_path(project_id)
    path.write_text(json.dumps(normalize_research_state(state), indent=2), encoding="utf-8")
    return path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_research_context(*, title: str = "", idea: str = "") -> dict[str, Any]:
    """Create one isolated ideation window."""
    now = _now_iso()
    context_id = uuid4().hex
    clean_idea = idea.strip()
    return {
        "id": context_id,
        "title": title.strip() or clean_idea[:48] or "New idea",
        "messages": ([{"role": "user", "content": clean_idea}] if clean_idea else []),
        "summary": "",
        "recommendations": [],
        "selected_component_ids": [],
        "selected_components": [],
        "decision_notes": "",
        "created_at": now,
        "updated_at": now,
    }


def normalize_research_state(state: dict[str, Any]) -> dict[str, Any]:
    """Upgrade the original single-window state without breaking old projects."""
    normalized = dict(state or {})
    normalized.setdefault("ideas", [])
    normalized.setdefault("summary", "")
    normalized.setdefault("recommendations", [])
    normalized.setdefault("selected_components", [])
    normalized.setdefault("decision_notes", "")
    normalized.setdefault("condensed_state", normalized.get("summary", ""))

    contexts = normalized.get("contexts")
    if not isinstance(contexts, list):
        contexts = []
    contexts = [item for item in contexts if isinstance(item, dict) and item.get("id")]

    # Convert meaningful legacy state into the first context once.
    if not contexts and any(
        normalized.get(key)
        for key in ("ideas", "summary", "recommendations", "selected_components", "decision_notes")
    ):
        legacy = new_research_context(title="Original research")
        legacy["messages"] = [
            {"role": "user", "content": str(idea)}
            for idea in normalized.get("ideas") or []
            if str(idea).strip()
        ]
        legacy["summary"] = normalized.get("summary", "")
        legacy["recommendations"] = normalized.get("recommendations") or []
        legacy["selected_components"] = normalized.get("selected_components") or []
        legacy["selected_component_ids"] = [
            item.get("id") for item in legacy["selected_components"] if item.get("id")
        ]
        legacy["decision_notes"] = normalized.get("decision_notes", "")
        contexts.append(legacy)

    for context in contexts:
        context.setdefault("title", "Idea")
        context.setdefault("messages", [])
        context.setdefault("summary", "")
        context.setdefault("recommendations", [])
        context.setdefault("selected_component_ids", [])
        context.setdefault("selected_components", [])
        context.setdefault("decision_notes", "")
        context.setdefault("created_at", _now_iso())
        context.setdefault("updated_at", context["created_at"])

    normalized["contexts"] = contexts
    active_id = normalized.get("active_context_id")
    if not any(item["id"] == active_id for item in contexts):
        active_id = contexts[0]["id"] if contexts else None
    normalized["active_context_id"] = active_id
    return normalized


def selected_component_ids(state: dict[str, Any]) -> list[str]:
    """Return the deduplicated project decision across every idea window."""
    normalized = normalize_research_state(state)
    ids: list[str] = []
    contexts = normalized.get("contexts") or []
    for context in contexts:
        ids.extend(str(item) for item in context.get("selected_component_ids") or [] if item)
        ids.extend(
            str(item["id"])
            for item in context.get("selected_components") or []
            if item.get("id")
        )
    if not contexts:
        for item in normalized.get("selected_components") or []:
            if item.get("id"):
                ids.append(str(item["id"]))
    return list(dict.fromkeys(ids))


def _component_score(component: ComponentDefinition, terms: set[str]) -> int:
    haystack = " ".join([
        component.id,
        component.name,
        component.category,
        component.description,
        " ".join(component.aliases or []),
    ]).casefold()
    score = sum(3 for term in terms if term and term in haystack)
    if component.library_ids or component.library_name:
        score += 1
    if component.buy_links:
        score += 1
    if component.datasheet_url:
        score += 1
    return score


def recommend_components(
    *,
    catalogue: dict[str, ComponentDefinition],
    goal: str,
    limit: int = 8,
) -> list[dict[str, Any]]:
    words = {
        word.strip(".,;:()[]{}").casefold()
        for word in goal.split()
        if len(word.strip(".,;:()[]{}")) >= 3
    }
    ranked = sorted(
        catalogue.values(),
        key=lambda component: (-_component_score(component, words), component.category, component.name),
    )
    result = []
    registry = load_registry()
    for component in ranked[:limit]:
        library_references = list(component.library_ids or [])
        if component.library_name and component.library_name not in library_references:
            library_references.append(component.library_name)
        library_links = []
        for reference in library_references:
            lowered = str(reference).casefold()
            library = get_library(str(reference)) or next(
                (
                    item for item in registry
                    if lowered in {
                        str(item.get("name", "")).casefold(),
                        str(item.get("pio_name", "")).casefold(),
                    }
                ),
                None,
            )
            if library:
                library_links.append({
                    "id": library["id"],
                    "name": library["name"],
                    "url": library.get("homepage"),
                    "pio_name": library.get("pio_name"),
                })
        buy_links = component.buy_links or [
            {
                "vendor": "Mouser search",
                "url": f"https://www.mouser.in/c/?q={quote_plus(component.name)}",
            },
            {
                "vendor": "DigiKey search",
                "url": f"https://www.digikey.in/en/products/result?keywords={quote_plus(component.name)}",
            },
        ]
        result.append({
            "id": component.id,
            "name": component.name,
            "category": component.category,
            "description": component.description,
            "thumbnail": component.thumbnail,
            "visual_type": component.visual_type,
            "library_ids": component.library_ids,
            "library_name": component.library_name,
            "library_links": library_links,
            "buy_links": buy_links,
            "datasheet_url": component.datasheet_url,
            "aliases": component.aliases,
            "pins": [pin.model_dump() for pin in component.pins],
            "difference": _difference_line(component),
        })
    return result


def _difference_line(component: ComponentDefinition) -> str:
    category = component.category.lower()
    if "display" in category:
        return "Display/output component; compare interface pins, voltage, resolution, and library support."
    if "sensor" in category:
        return "Sensor/input component; compare signal type, voltage, accuracy, sampling rate, and library support."
    if "actuator" in category or "motor" in category:
        return "Actuator/driver component; compare current rating, control pins, voltage, and protection needs."
    if component.library_ids or component.library_name:
        return "Has a known firmware library path, which reduces integration time."
    return "Generic component; compare pin roles, voltage, and datasheet requirements before selecting."


async def summarize_with_deepseek_or_fallback(
    *,
    idea: str,
    recommendations: list[dict[str, Any]],
    provider: str = "deepseek",
    history: list[dict[str, str]] | None = None,
) -> str:
    names = "\n".join(
        f"- {item['name']} ({item['id']}): {item.get('difference', '')}"
        for item in recommendations[:8]
    )
    fallback = (
        f"Goal: {idea.strip() or 'No goal provided.'}\n"
        "Recommended direction:\n"
        f"{names or '- No catalogue matches yet.'}\n"
        "Next step: select the components you want, then resolve phase-3 pins/libraries."
    )
    try:
        prior = [
            {"role": item.get("role", "user"), "content": item.get("content", "")}
            for item in (history or [])[-10:]
            if item.get("role") in {"user", "assistant"} and item.get("content")
        ]
        text = await llm.complete(provider, [
            {
                "role": "system",
                "content": (
                    "You are an embedded-systems research partner. Maintain a compact decision state "
                    "for this isolated idea window. Incorporate the conversation, identify constraints, "
                    "mention component tradeoffs, and state the next decision. Keep it under 180 words."
                ),
            },
            *prior,
            {
                "role": "user",
                "content": f"User idea:\n{idea}\n\nComponent options:\n{names}",
            },
        ])
        return text.strip() or fallback
    except Exception:
        return fallback


async def condense_research_with_deepseek(state: dict[str, Any]) -> tuple[str, bool]:
    """Create the single project handoff from all isolated idea windows."""
    normalized = normalize_research_state(state)
    sections: list[str] = []
    for context in normalized.get("contexts") or []:
        chosen = ", ".join(
            item.get("name", item.get("id", ""))
            for item in context.get("selected_components") or []
        ) or "No components selected"
        sections.append(
            f"Idea: {context.get('title', 'Idea')}\n"
            f"State: {context.get('summary') or 'No summary'}\n"
            f"Chosen: {chosen}\n"
            f"Notes: {context.get('decision_notes') or 'None'}"
        )
    source = "\n\n".join(sections) or "No research contexts have been created."
    fallback = (
        "Project decision state:\n" + source +
        "\n\nNext step: verify the board, wiring, voltage levels, and library compatibility before Act mode."
    )
    try:
        text = await llm.complete("deepseek", [
            {
                "role": "system",
                "content": (
                    "Condense multiple embedded-product ideation windows into one authoritative "
                    "implementation handoff. Preserve chosen parts, constraints, unresolved risks, "
                    "and the next action. Do not invent decisions. Keep it under 240 words."
                ),
            },
            {"role": "user", "content": source},
        ])
        return (text.strip() or fallback, True)
    except Exception:
        return (fallback, False)


def render_project_readme(
    *,
    project_name: str,
    board: dict[str, Any],
    research_state: dict[str, Any],
    component_context: dict[str, Any],
) -> str:
    selected = research_state.get("selected_components") or []
    selected_lines = "\n".join(
        f"- {item.get('name', item.get('id'))} ({item.get('id')})"
        for item in selected
    ) or "- No research selections recorded."
    return f"""# {project_name}

## Target Board

- Board: {board.get('label')} (`{board.get('id')}`)
- MCU: {board.get('mcu')}
- Family: {board.get('family')}
- Frameworks: {', '.join(board.get('frameworks') or [])}

## Research Decision

{research_state.get('summary') or 'No condensed research summary recorded yet.'}

## Selected Components

{selected_lines}

## Component, Pin, And Library Context

```text
{context_to_markdown(component_context)}
```

## Notes

{research_state.get('decision_notes') or 'No extra decision notes.'}

## Act Mode Handoff

Use this README plus `.hardcoreai/research_state.json` and
`.hardcoreai/component_context.json` as the condensed state for code generation.
"""
