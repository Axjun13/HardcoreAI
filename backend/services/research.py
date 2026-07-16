"""Research/ideation state for component selection and final project context."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import llm
from schemas import ComponentDefinition
from services.component_resolution import context_to_markdown
from services.hardware import workspace_dir


def research_dir(project_id: str) -> Path:
    path = workspace_dir(project_id) / ".hardcoreai"
    path.mkdir(parents=True, exist_ok=True)
    return path


def research_state_path(project_id: str) -> Path:
    return research_dir(project_id) / "research_state.json"


def load_research_state(project_id: str) -> dict[str, Any]:
    path = research_state_path(project_id)
    if not path.exists():
        return {
            "ideas": [],
            "summary": "",
            "recommendations": [],
            "selected_components": [],
            "decision_notes": "",
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_research_state(project_id: str, state: dict[str, Any]) -> Path:
    path = research_state_path(project_id)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return path


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
    for component in ranked[:limit]:
        result.append({
            "id": component.id,
            "name": component.name,
            "category": component.category,
            "description": component.description,
            "thumbnail": component.thumbnail,
            "visual_type": component.visual_type,
            "library_ids": component.library_ids,
            "library_name": component.library_name,
            "buy_links": component.buy_links,
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
        text = await llm.complete(provider, [
            {
                "role": "system",
                "content": (
                    "Summarize embedded project research into a compact decision state. "
                    "Mention tradeoffs and ask the user to choose components. Keep it under 180 words."
                ),
            },
            {
                "role": "user",
                "content": f"User idea:\n{idea}\n\nComponent options:\n{names}",
            },
        ])
        return text.strip() or fallback
    except Exception:
        return fallback


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
