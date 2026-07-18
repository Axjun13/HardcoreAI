"""Resolve selected workbench components into AI/codegen context.

This is the bridge between the visual component catalogue and the firmware
agent: selected parts imply libraries, purchase/reference links, and concrete
pin roles. The functions are pure so routes, tools, and tests can reuse them.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from schemas import ComponentDefinition
from services.hardware import ensure_platformio, workspace_dir
from services.library_service import get_library, install_library, load_registry


def _component_pin_map(definition: ComponentDefinition) -> dict[str, Any]:
    return {
        pin.name: {
            "label": pin.label,
            "role": pin.role,
            "side": pin.side,
            "x": pin.x,
            "y": pin.y,
        }
        for pin in definition.pins
    }


def _component_buy_links(definition: ComponentDefinition) -> list[dict[str, Any]]:
    if definition.buy_links:
        return definition.buy_links
    query = quote_plus(definition.name)
    return [
        {"vendor": "Mouser search", "url": f"https://www.mouser.in/c/?q={query}"},
        {
            "vendor": "DigiKey search",
            "url": f"https://www.digikey.in/en/products/result?keywords={query}",
        },
    ]


def resolve_component_context(
    *,
    catalogue: dict[str, ComponentDefinition],
    workbench: dict[str, Any],
    selected_component_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Return selected components, inferred libraries, links, and net layout.

    Research selections are allowed to exist before a part is placed on the
    visual workbench.  They are merged here so Phase 3, README generation and
    Act mode all consume the same decision state.
    """
    placed = workbench.get("placed_components") or []
    wires = workbench.get("wires") or []
    by_instance = {str(item.get("id")): item for item in placed}
    placed_definition_ids = {
        str(item.get("definition_id")) for item in placed if item.get("definition_id")
    }

    components: list[dict[str, Any]] = []
    libraries: dict[str, dict[str, Any]] = {}

    for item in placed:
        slug = item.get("definition_id", "")
        definition = catalogue.get(slug)
        if not definition:
            continue

        resolved_libs = _collect_component_libraries(definition, libraries)

        components.append({
            "instance_id": str(item.get("id")),
            "definition_id": slug,
            "display_name": item.get("display_name") or definition.name,
            "component_name": definition.name,
            "category": definition.category,
            "description": definition.description,
            "aliases": definition.aliases,
            "datasheet_url": definition.datasheet_url,
            "buy_links": _component_buy_links(definition),
            "library_ids": resolved_libs,
            "pins": _component_pin_map(definition),
            "config": item.get("config") or {},
            "source": "workbench",
        })

    # A research decision is still actionable even before the user drags the
    # component onto the workbench. Add those unplaced definitions with stable
    # synthetic instance ids, while avoiding duplicates for already-placed
    # definitions.
    for slug in dict.fromkeys(selected_component_ids or []):
        if slug in placed_definition_ids:
            continue
        definition = catalogue.get(slug)
        if not definition:
            continue
        resolved_libs = _collect_component_libraries(definition, libraries)
        components.append({
            "instance_id": f"research:{slug}",
            "definition_id": slug,
            "display_name": definition.name,
            "component_name": definition.name,
            "category": definition.category,
            "description": definition.description,
            "aliases": definition.aliases,
            "datasheet_url": definition.datasheet_url,
            "buy_links": _component_buy_links(definition),
            "library_ids": resolved_libs,
            "pins": _component_pin_map(definition),
            "config": {},
            "source": "research",
        })

    resolved_wires: list[dict[str, Any]] = []
    for wire in wires:
        left = wire.get("from") or {}
        right = wire.get("to") or {}
        left_component = by_instance.get(str(left.get("componentId")))
        right_component = by_instance.get(str(right.get("componentId")))
        if not left_component or not right_component:
            continue
        resolved_wires.append({
            "id": str(wire.get("id")),
            "from": {
                "instance_id": str(left.get("componentId")),
                "component": left_component.get("display_name"),
                "definition_id": left_component.get("definition_id"),
                "pin": left.get("pinName"),
            },
            "to": {
                "instance_id": str(right.get("componentId")),
                "component": right_component.get("display_name"),
                "definition_id": right_component.get("definition_id"),
                "pin": right.get("pinName"),
            },
            "label": wire.get("label") or "",
        })

    return {
        "components": components,
        "libraries": sorted(libraries.values(), key=lambda lib: str(lib.get("name", lib.get("id", ""))).lower()),
        "wires": resolved_wires,
    }


def _collect_component_libraries(
    definition: ComponentDefinition,
    libraries: dict[str, dict[str, Any]],
) -> list[str]:
    """Resolve known library references without treating labels as git URLs."""
    references = list(definition.library_ids or [])
    if definition.library_name and definition.library_name not in references:
        references.append(definition.library_name)

    resolved: list[str] = []
    registry = load_registry()
    for reference in references:
        ref = str(reference).strip()
        if not ref:
            continue
        lowered = ref.casefold()
        lib = get_library(ref) or next(
            (
                item for item in registry
                if lowered in {
                    str(item.get("name", "")).casefold(),
                    str(item.get("pio_name", "")).casefold(),
                }
            ),
            None,
        )
        if lib:
            libraries[str(lib["id"])] = lib
            resolved.append(str(lib["id"]))
            continue

        # Preserve legacy catalogue metadata for the README/UI, but explicitly
        # mark it non-installable. A label such as "Arduino" or "Motor" is not
        # necessarily a valid PlatformIO dependency.
        libraries[ref] = {
            "id": ref,
            "name": ref,
            "description": "Legacy component library label; choose a registry package before installation.",
            "pio_name": None,
            "source": "component",
            "installable": False,
        }
        resolved.append(ref)
    return resolved


def context_to_markdown(context: dict[str, Any]) -> str:
    """Compact human/model-readable summary for agent prompts and README seed."""
    components = context.get("components") or []
    libraries = context.get("libraries") or []
    wires = context.get("wires") or []

    lines = ["SELECTED COMPONENTS:"]
    if components:
        for component in components:
            lines.append(
                f"- {component['display_name']} ({component['definition_id']}): "
                f"{component.get('description') or 'no description'}"
            )
            if component.get("library_ids"):
                lines.append(f"  Libraries: {', '.join(component['library_ids'])}")
            if component.get("datasheet_url"):
                lines.append(f"  Datasheet: {component['datasheet_url']}")
            if component.get("buy_links"):
                links = ", ".join(
                    f"{link.get('vendor', link.get('label', 'buy'))}: {link.get('url', '')}"
                    for link in component["buy_links"]
                    if link.get("url")
                )
                if links:
                    lines.append(f"  Buy links: {links}")
            pin_desc = ", ".join(
                f"{name}={meta.get('role', 'pin')}"
                for name, meta in component.get("pins", {}).items()
            )
            if pin_desc:
                lines.append(f"  Pins: {pin_desc}")
    else:
        lines.append("- No workbench components selected yet.")

    lines.append("WIRES:")
    if wires:
        for wire in wires:
            lines.append(
                f"- {wire['from']['component']}.{wire['from']['pin']} -> "
                f"{wire['to']['component']}.{wire['to']['pin']}"
            )
    else:
        lines.append("- No wires placed yet.")

    lines.append("REQUIRED LIBRARIES:")
    if libraries:
        for lib in libraries:
            dep = lib.get("pio_name") or "bundled/framework"
            lines.append(f"- {lib.get('name', lib.get('id'))}: {dep}")
            if lib.get("homepage"):
                lines.append(f"  Documentation: {lib['homepage']}")
    else:
        lines.append("- None inferred.")
    return "\n".join(lines)


def write_component_manifest(project_id: str, context: dict[str, Any]) -> Path:
    """Persist resolved selections so phase-3/codegen has an isolated snapshot."""
    workspace = workspace_dir(project_id)
    workspace.mkdir(parents=True, exist_ok=True)
    out_dir = workspace / ".hardcoreai"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "component_context.json"
    path.write_text(json.dumps(context, indent=2), encoding="utf-8")
    return path


def install_component_libraries(project_id: str, context: dict[str, Any]) -> list[dict[str, Any]]:
    """Add every inferred PlatformIO library to the project's lib_deps."""
    results: list[dict[str, Any]] = []
    for lib in context.get("libraries") or []:
        library_id = lib.get("id")
        pio_name = lib.get("pio_name")
        if library_id and get_library(str(library_id)):
            results.append(install_library(project_id, library_id=str(library_id)))
        elif pio_name:
            results.append(install_library(project_id, git_url=str(pio_name)))
    return results


def materialize_component_libraries(project_id: str, context: dict[str, Any]) -> dict[str, Any]:
    """Download resolved ``lib_deps`` into the project's isolated PIO cache."""
    installable = [
        lib for lib in context.get("libraries") or []
        if lib.get("pio_name") and lib.get("installable", True)
    ]
    workspace = workspace_dir(project_id)
    target = workspace / ".pio" / "libdeps"
    if not installable:
        return {
            "success": True,
            "downloaded": False,
            "directory": str(target),
            "message": "No installable third-party libraries were selected.",
        }
    try:
        pio = ensure_platformio()
        result = subprocess.run(
            [pio, "pkg", "install", "--project-dir", str(workspace)],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        return {
            "success": False,
            "downloaded": False,
            "directory": str(target),
            "message": f"Library download could not complete: {exc}",
        }
    output = (result.stdout + "\n" + result.stderr).strip()
    return {
        "success": result.returncode == 0,
        "downloaded": result.returncode == 0,
        "directory": str(target),
        "message": (
            "Libraries downloaded into the project cache."
            if result.returncode == 0
            else "PlatformIO could not resolve one or more selected libraries."
        ),
        "output": output[-4000:],
    }
