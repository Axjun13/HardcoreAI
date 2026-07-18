"""Research/ideation state for component selection and final project context."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
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


# Catalogue controller cards and PlatformIO board ids are intentionally
# separate namespaces.  This bridge makes a confirmed Research controller
# choice authoritative for the project target instead of leaving a new project
# on its historical Blue Pill default when the user selected an ESP32.
_CONTROLLER_BOARD_IDS = {
    "esp32-devkit-v1": "esp32dev",
    "stm32-blue-pill": "bluepill_f103c8",
}


def selected_target_board_id(components: list[dict[str, Any]]) -> str | None:
    """Return one unambiguous board target represented by selected parts.

    Multiple controller boards are left unresolved so comparison/co-processor
    designs never silently pick one.  Registry ids are also accepted directly
    for dynamically discovered cards that already use the PlatformIO id.
    """
    from boards.registry import registry

    candidates: list[str] = []
    for component in components or []:
        component_id = str(component.get("id") or "").strip()
        mapped = _CONTROLLER_BOARD_IDS.get(component_id)
        if mapped:
            candidates.append(mapped)
            continue
        category = str(component.get("category") or "").casefold()
        visual_type = str(component.get("visual_type") or "").casefold()
        if ("microcontroller" in category or visual_type == "board") and registry.get(component_id):
            candidates.append(component_id)
    unique = list(dict.fromkeys(candidates))
    return unique[0] if len(unique) == 1 else None


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
    # Replace atomically so a simultaneous UI reload or background sync can
    # never observe a partially written JSON document.
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(normalize_research_state(state), indent=2), encoding="utf-8")
    temporary.replace(path)
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
    normalized.setdefault("stage", "ideation")
    normalized.setdefault("plan_markdown", "")
    normalized.setdefault("components_markdown", "")
    normalized.setdefault("verification_markdown", "")
    normalized.setdefault("final_markdown", "")
    normalized.setdefault("pin_diagram_markdown", "")
    normalized.setdefault("connection_diagram_markdown", "")
    normalized.setdefault("configuration_markdown", "")
    normalized.setdefault("pin_configuration", {})
    normalized.setdefault("component_verifications", [])
    normalized.setdefault("pin_assignments", [])
    normalized.setdefault("todos", [])
    normalized.setdefault("review_revision", 0)
    normalized.setdefault("verification_activity", {})
    normalized.setdefault("board_selection", {})
    normalized.setdefault("target_board_id", None)

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


def research_goal_text(state: dict[str, Any], latest: str = "") -> str:
    """Return the complete conversation used for ranking and web discovery.

    Assistant turns matter here: if the advisor names an exact part, the same
    part must be eligible for a selectable card instead of being lost because
    only user messages were ranked.
    """
    normalized = normalize_research_state(state)
    parts: list[str] = []
    for context in normalized.get("contexts") or []:
        parts.extend(
            str(message.get("content", "")).strip()
            for message in context.get("messages") or []
            if str(message.get("content", "")).strip()
        )
    if normalized.get("summary"):
        parts.append(str(normalized["summary"]))
    if latest.strip():
        parts.append(latest.strip())
    return "\n".join(dict.fromkeys(parts))


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
    preferred_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    words = {
        word.strip(".,;:()[]{}").casefold()
        for word in goal.split()
        if len(word.strip(".,;:()[]{}")) >= 3
    }
    lowered_goal = goal.casefold()
    mentioned_ids = []
    for component in catalogue.values():
        exact_names = [component.name, component.id, *(component.aliases or [])]
        if any(
            len(value.strip()) >= 5
            and value.casefold() in lowered_goal
            for value in exact_names
        ):
            mentioned_ids.append(component.id)
    prioritized_ids = list(dict.fromkeys([*mentioned_ids, *(preferred_ids or [])]))
    preferred = {component_id: index for index, component_id in enumerate(prioritized_ids)}
    ranked = sorted(
        catalogue.values(),
        key=lambda component: (
            0 if component.id in preferred else 1,
            preferred.get(component.id, 0),
            -_component_score(component, words),
            component.category,
            component.name,
        ),
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
            "source_url": component.source_url,
            "source_name": component.source_name,
            "image_source_url": component.image_source_url,
            "discovery_query": component.discovery_query,
            "discovered_at": component.discovered_at.isoformat() if component.discovered_at else None,
            "verified_at": component.verified_at.isoformat() if component.verified_at else None,
            "protocols": component.protocols,
            "verification_sources": component.verification_sources,
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


def render_plan_markdown(project_name: str, state: dict[str, Any]) -> str:
    """Create the durable plan produced when ideation is confirmed."""
    normalized = normalize_research_state(state)
    conversation = []
    for context in normalized.get("contexts") or []:
        conversation.extend(
            item.get("content", "").strip()
            for item in context.get("messages") or []
            if item.get("role") == "user" and item.get("content", "").strip()
        )
    requirements = "\n".join(f"- {item}" for item in dict.fromkeys(conversation)) or "- No detailed requirements recorded."
    return f"""# {project_name} Plan

## Goal

{normalized.get('summary') or 'Build the embedded-system idea discussed in Research.'}

## Confirmed Requirements

{requirements}

## Implementation Approach

1. Select compatible board-level components and interfaces.
2. Verify voltage levels, pin availability, library support, and integration risks.
3. Configure the target, pins, and PlatformIO dependencies.
4. Implement firmware in small testable modules.
5. Build and resolve all compiler/linker errors.
6. Flash when a compatible device is connected; otherwise stop after a successful build.

## Open Decisions

- Exact component variants, pin mapping, and purchasing cost are finalized in the component review.
"""


def render_components_markdown(state: dict[str, Any]) -> str:
    """Create the selected component contract used by the verification context."""
    selected = normalize_research_state(state).get("selected_components") or []
    blocks = []
    for item in selected:
        pins = ", ".join(pin.get("label") or pin.get("name", "") for pin in item.get("pins") or []) or "See datasheet"
        libraries = ", ".join([*(item.get("library_ids") or []), *([item["library_name"]] if item.get("library_name") else [])]) or "Framework/bare driver"
        blocks.append(
            f"## {item.get('name', item.get('id'))}\n\n"
            f"- Catalogue ID: `{item.get('id')}`\n"
            f"- Role: {item.get('description') or item.get('category', 'Component')}\n"
            f"- Pins: {pins}\n"
            f"- Libraries: {libraries}\n"
            f"- Datasheet: {item.get('datasheet_url') or 'Not catalogued'}\n"
            f"- Price: To be confirmed from the linked supplier at purchase time\n"
        )
    return "# Selected Components\n\n" + ("\n".join(blocks) if blocks else "No components selected.\n")


def render_verification_markdown(
    *, project_name: str, board: dict[str, Any], state: dict[str, Any], component_context: dict[str, Any]
) -> str:
    """Verify the selected set without inventing electrical or pricing facts."""
    components = component_context.get("components") or []
    libraries = component_context.get("libraries") or []
    rows = []
    for component in components:
        pin_count = len(component.get("pins") or {})
        rows.append(
            f"| {component.get('display_name')} | {component.get('category')} | {pin_count} catalogue pins | "
            f"{', '.join(component.get('library_ids') or []) or 'No external library'} | Needs board-pin assignment |"
        )
    component_table = "\n".join(rows) or "| None | - | - | - | Select components first |"
    library_lines = "\n".join(
        f"- {lib.get('name', lib.get('id'))}: `{lib.get('pio_name') or 'bundled/framework'}`"
        for lib in libraries
    ) or "- No third-party libraries inferred."
    return f"""# {project_name} Component Verification

## Target

- Board: {board.get('label')} (`{board.get('id')}`)
- MCU/family: {board.get('mcu')} / {board.get('family')}

## Compatibility Matrix

| Component | Role | Pin demand | Library | Verification |
|---|---|---:|---|---|
{component_table}

## Required Libraries

{library_lines}

## Wiring And Power Checks

- Confirm every component's operating voltage and logic level from its datasheet before wiring.
- Assign concrete MCU pins without conflicts, reserving required bus pins and debugger pins.
- Add pull-ups, level shifting, current limiting, flyback protection, or a separate supply where required.
- The current catalogue does not contain stable regional prices, so total pricing remains pending supplier quotes; purchase links are retained in the component cards.

## Result

The selected parts have a viable software integration path. Electrical compatibility is conditional on the final pin/voltage assignment above; unresolved items must be closed before flashing hardware.
"""


def render_final_markdown(project_name: str, state: dict[str, Any]) -> str:
    normalized = normalize_research_state(state)
    decision = normalized.get("board_selection") or {}
    selected_board = (decision.get("selected") or {}).get("board") or {}
    reasons = (decision.get("selected") or {}).get("reasons") or []
    warnings = (decision.get("selected") or {}).get("warnings") or []
    alternatives = [
        item for item in (decision.get("candidates") or [])[1:4]
        if (item.get("board") or {}).get("id")
    ]
    board_review = (
        f"- Selected: **{selected_board.get('label')}** (`{selected_board.get('id')}`)\n"
        f"- MCU/family: {selected_board.get('mcu')} / {selected_board.get('family')}\n"
        f"- Frameworks: {', '.join(selected_board.get('frameworks') or []) or 'Unresolved'}\n"
        f"- Selection confidence: {decision.get('confidence', 'unresolved')}\n"
        f"- Registry targets considered: {decision.get('registry_size', 0)}\n"
        + ("- Reasons:\n" + "\n".join(f"  - {item}" for item in reasons) + "\n" if reasons else "")
        + ("- Warnings:\n" + "\n".join(f"  - {item}" for item in warnings) + "\n" if warnings else "")
        + ("- Other ranked candidates:\n" + "\n".join(
            f"  - {(item.get('board') or {}).get('label')} (`{(item.get('board') or {}).get('id')}`)"
            for item in alternatives
        ) if alternatives else "")
        if selected_board else "Board selection has not run."
    )
    return f"""# {project_name} Final Review

## Plan

{normalized.get('plan_markdown') or 'Plan not generated.'}

## Board Selection

{board_review}

## Components

{normalized.get('components_markdown') or 'Components not confirmed.'}

## Verification

{normalized.get('verification_markdown') or 'Verification not complete.'}

## Pin Diagram

{normalized.get('pin_diagram_markdown') or 'Pin diagram not generated.'}

## Connection Diagram

{normalized.get('connection_diagram_markdown') or 'Connection diagram not generated.'}

## Applied Configuration

{normalized.get('configuration_markdown') or 'Configuration not generated.'}

## TODO

{chr(10).join(f"- [{'x' if item.get('status') == 'completed' else ' '}] {item.get('label')}" for item in normalized.get('todos') or []) or '- [ ] No execution TODO was generated.'}
"""


def research_fallback_response(
    *,
    idea: str,
    recommendations: list[dict[str, Any]],
    history: list[dict[str, str]] | None = None,
    stage: str = "ideation",
) -> str:
    if stage == "ideation":
        prior_user_turns = [
            item.get("content", "").strip()
            for item in (history or [])
            if item.get("role") == "user" and item.get("content", "").strip()
        ]
        lowered = idea.casefold()
        frustrated = any(
            phrase in lowered
            for phrase in ("wdym", "what do you mean", "i was clear", "already told", "i just said")
        )
        if frustrated:
            return (
                "You’re right—you were clear, and I shouldn’t have asked you to repeat it. I’ve kept "
                "the requirements from your earlier messages. We can move on to component selection now, "
                "unless there’s one detail you specifically want to explore first."
            )
        if prior_user_turns or len(idea.split()) >= 16:
            return (
                "That makes the direction clear. I’ve captured the details you added, and I won’t make "
                "you restate them. The useful next step is to turn those product requirements into concrete "
                "hardware tradeoffs. If the direction feels right, confirm the idea and we’ll choose parts; "
                "otherwise, tell me which detail you want to explore further."
            )
        return (
            "I’m with you. Before we choose hardware, what would make this idea feel successful to you in "
            "day-to-day use? One concrete behavior or must-have is enough to start shaping it."
        )
    names = ", ".join(item["name"] for item in recommendations[:5])
    return (
        f"For the current requirements, I’d compare {names or 'the available parts'} next. "
        "Let’s choose based on electrical compatibility, pin usage, power, and library support."
    )


def research_chat_messages(
    *,
    idea: str,
    recommendations: list[dict[str, Any]],
    history: list[dict[str, str]] | None = None,
    stage: str = "ideation",
) -> list[dict[str, str]]:
    """Build phase-aware chat messages without leaking catalogue mechanics into ideation."""
    names = "\n".join(
        f"- {item['name']} ({item['id']}): {item.get('difference', '')}"
        for item in recommendations[:8]
    )
    prior = [
        {"role": item.get("role", "user"), "content": item.get("content", "")}
        for item in (history or [])[-10:]
        if item.get("role") in {"user", "assistant"} and item.get("content")
    ]
    if stage == "ideation":
        system = (
            "You are a warm, curious embedded-product design partner in the IDEATION phase. "
            "Have a natural conversation about what the person wants to make and why. Explore the "
            "experience, use case, must-haves, and meaningful constraints before choosing hardware. "
            "Ask at most one high-value question per turn when something important is unknown. If the "
            "idea is already clear, reflect it back and offer one or two possible directions in plain "
            "prose. Do not output a decision state, requirements report, or component inventory. Do not "
            "use headings such as Goal, Constraints, Capabilities, Tradeoffs, or Recommended direction. "
            "The catalogue matches below are private background only: do not enumerate or recommend them "
            "unless the user explicitly asks about parts. Keep the reply conversational and under 160 words."
        )
    else:
        system = (
            "You are an exact embedded-systems component advisor. The idea has moved past open ideation. "
            "Help make a firm component decision: compare relevant parts, voltage and current needs, bus "
            "and pin usage, physical/power tradeoffs, and firmware library support. Be direct, call out bad "
            "fits, and end with the next concrete selection decision. Keep it under 200 words."
        )
    return [
        {"role": "system", "content": system},
        *prior,
        {
            "role": "user",
            "content": (
                f"Latest message:\n{idea}\n\nPrivate catalogue matches (use only as allowed above):\n"
                f"{names or '- No close catalogue matches yet.'}"
            ),
        },
    ]


async def stream_research_response(
    *,
    idea: str,
    recommendations: list[dict[str, Any]],
    provider: str = "deepseek",
    history: list[dict[str, str]] | None = None,
    stage: str = "ideation",
) -> AsyncIterator[str]:
    """Yield the research reply directly from the provider."""
    async for chunk in llm.stream(
        provider,
        research_chat_messages(
            idea=idea,
            recommendations=recommendations,
            history=history,
            stage=stage,
        ),
    ):
        yield chunk


async def summarize_with_deepseek_or_fallback(
    *,
    idea: str,
    recommendations: list[dict[str, Any]],
    provider: str = "deepseek",
    history: list[dict[str, str]] | None = None,
    stage: str = "ideation",
) -> str:
    fallback = research_fallback_response(
        idea=idea,
        recommendations=recommendations,
        history=history,
        stage=stage,
    )
    try:
        text = await llm.complete(provider, research_chat_messages(
            idea=idea,
            recommendations=recommendations,
            history=history,
            stage=stage,
        ))
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
