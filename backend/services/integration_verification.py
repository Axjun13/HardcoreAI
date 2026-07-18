"""Phase-3 component verification, pin planning, and review artifacts.

The online portion is deliberately best-effort: a failed search or unreadable
PDF is recorded as an unresolved warning and is never presented as verified.
Pure rendering/assignment helpers live here so the workflow and tests share
one implementation.
"""

from __future__ import annotations

import json
import re
import asyncio
from datetime import datetime, timezone
from io import BytesIO
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from sqlmodel import Session, select

import llm
from db.models import Component, PinRow
from rag.web_search import search_web


POWER_NAMES = {"VCC", "VIN", "VDD", "3V3", "3.3V", "5V", "+"}
GROUND_NAMES = {"GND", "VSS", "GROUND", "-"}


def phase3_todos(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    todos = [{
        "id": "select:board",
        "label": "Select and configure the best supported board from the approved requirements",
        "status": "pending",
        "required": True,
    }]
    todos.extend([
        {
            "id": f"verify:{item.get('id') or item.get('definition_id')}",
            "label": f"Verify {item.get('name') or item.get('display_name')} against its datasheet and catalogue record",
            "status": "pending",
            "required": True,
        }
        for item in components
    ])
    todos.extend([
        {"id": "design:pin-map", "label": "Assign conflict-free board pins for every component", "status": "pending", "required": True},
        {"id": "design:diagrams", "label": "Generate the pin diagram and connection diagram", "status": "pending", "required": True},
        {"id": "configure:pins", "label": "Write the reviewed pin and protocol configuration", "status": "pending", "required": True},
        {"id": "review:approval", "label": "Obtain final user approval; incorporate edits and ask again until approved", "status": "pending", "required": True},
        {"id": "act:dependencies", "label": "Install the approved PlatformIO dependencies", "status": "pending", "required": True},
        {"id": "act:firmware", "label": "Implement firmware from the approved plan and configuration", "status": "pending", "required": True},
        {"id": "act:build", "label": "Build and fix correctness-affecting errors and warnings", "status": "pending", "required": True},
        {"id": "act:flash", "label": "Detect hardware and flash only when a compatible device is available", "status": "pending", "required": True},
    ])
    return todos


def set_todo_status(state: dict[str, Any], todo_id: str, status: str, detail: str = "") -> None:
    for todo in state.get("todos") or []:
        if todo.get("id") == todo_id:
            todo["status"] = status
            if detail:
                todo["detail"] = detail
            return


def _json_payload(value: str) -> dict[str, Any]:
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", (value or "").strip(), flags=re.I | re.S)
    start, end = clean.find("{"), clean.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        payload = json.loads(clean[start:end + 1])
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        return {}


def _string_list(value: Any, *, limit: int, item_limit: int) -> list[str]:
    """Normalize nullable or malformed model fields without breaking the stream."""
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        values = []
    return [str(item).strip()[:item_limit] for item in values if str(item).strip()][:limit]


def _valid_results(results: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "title": str(item.get("title") or "")[:300],
            "url": str(item.get("url") or "")[:1000],
            "snippet": str(item.get("snippet") or "")[:1200],
        }
        for item in results
        if item.get("url") and not item.get("error")
    ]


def _datasheet_url(results: list[dict[str, str]], existing: str | None) -> str | None:
    if existing:
        return existing
    return next(
        (
            item["url"]
            for item in results
            if ".pdf" in item["url"].casefold()
            or "datasheet" in f"{item['title']} {item['snippet']}".casefold()
        ),
        None,
    )


def fetch_datasheet_text(url: str | None) -> str:
    """Download a reasonably-sized PDF and extract a bounded evidence sample."""
    if not url or ".pdf" not in url.casefold():
        return ""
    try:
        # pypdf is installed by llama-index-readers-file in full deployments,
        # but keep URL/source verification functional in minimal test builds.
        from pypdf import PdfReader
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            response = client.get(url, headers={"User-Agent": "HardcoreAI-ComponentVerifier/1.0"})
            response.raise_for_status()
        if len(response.content) > 15_000_000:
            return ""
        reader = PdfReader(BytesIO(response.content))
        pages = []
        for page in reader.pages[:16]:
            pages.append(page.extract_text() or "")
            if sum(len(item) for item in pages) >= 24_000:
                break
        return "\n".join(pages)[:24_000]
    except Exception:
        return ""


def infer_protocols(pins: list[dict[str, Any]]) -> list[str]:
    text = " ".join(
        f"{pin.get('name', '')} {pin.get('label', '')} {pin.get('role', '')} {pin.get('capabilities', '')}"
        for pin in pins
    ).upper()
    protocols = []
    checks = {
        "I2C": ("SDA", "SCL"),
        "SPI": ("MOSI", "SCK"),
        "UART": ("TX", "RX"),
        "CAN": ("CANH", "CANL"),
        "USB": ("D+", "D-"),
        "I2S": ("I2S",),
        "1-Wire": ("1-WIRE",),
        "Analog": ("ANALOG", " ADC", " AO"),
        "PWM": ("PWM",),
    }
    for protocol, signals in checks.items():
        if all(signal in text for signal in signals):
            protocols.append(protocol)
    if not protocols and pins:
        protocols.append("GPIO")
    return protocols


ProgressReporter = Callable[[dict[str, Any]], Awaitable[None]]


async def _report(
    progress: ProgressReporter | None,
    phase: str,
    title: str,
    detail: str,
    step: int,
    **extra: Any,
) -> None:
    if progress is not None:
        await progress({
            "phase": phase,
            "title": title,
            "detail": detail,
            "step": step,
            **extra,
        })


async def verify_component_online(
    component: dict[str, Any],
    provider: str,
    progress: ProgressReporter | None = None,
) -> dict[str, Any]:
    """Fetch sources and use the selected model to extract only evidenced facts."""
    name = str(component.get("name") or component.get("display_name") or component.get("id"))
    query = f"{name} official datasheet pinout supported interface protocol voltage"
    await _report(
        progress,
        "web_search",
        "Searching authoritative sources",
        f"Looking for the official {name} datasheet, pinout, voltage, and supported protocols.",
        1,
        query=query,
    )
    results = _valid_results(await asyncio.to_thread(search_web, query, 8))
    await _report(
        progress,
        "source_review",
        "Reviewing source candidates",
        f"Found {len(results)} usable source result{'s' if len(results) != 1 else ''}; selecting datasheet evidence.",
        2,
        source_count=len(results),
    )
    datasheet_url = _datasheet_url(results, component.get("datasheet_url"))
    await _report(
        progress,
        "datasheet",
        "Reading the datasheet",
        "Downloading and extracting a bounded datasheet sample." if datasheet_url else "No datasheet URL was found; retaining the catalogue record and recording a warning.",
        3,
        datasheet_url=datasheet_url,
    )
    datasheet_text = await asyncio.to_thread(fetch_datasheet_text, datasheet_url)
    existing_pins = component.get("pins") or []
    if isinstance(existing_pins, dict):
        existing_pins = [dict(meta, name=pin_name) for pin_name, meta in existing_pins.items()]

    prompt = {
        "name": name,
        "existing": {
            "datasheet_url": component.get("datasheet_url"),
            "pins": existing_pins,
            "protocols": component.get("protocols") or [],
        },
        "candidate_datasheet_url": datasheet_url,
        "search_results": results,
        "datasheet_extract": datasheet_text,
    }
    extracted: dict[str, Any] = {}
    await _report(
        progress,
        "analysis",
        "Cross-checking catalogue facts",
        f"Comparing {len(existing_pins)} catalogue pins with the fetched evidence and extracting protocols and voltage constraints.",
        4,
        existing_pin_count=len(existing_pins),
        datasheet_characters=len(datasheet_text),
    )
    try:
        response = await llm.complete(provider or "deepseek", [
            {
                "role": "system",
                "content": (
                    "Cross-check one electronic component against the supplied web results and datasheet text. "
                    "Return JSON only with: datasheet_url, pins (name,label,role,voltage,capabilities), "
                    "protocols, operating_voltage, configuration_notes, warnings. Never infer a factual pinout "
                    "from general knowledge when it is absent from the evidence. Preserve correct existing data. "
                    "Use warnings for conflicts or missing evidence."
                ),
            },
            {"role": "user", "content": json.dumps(prompt)[:45_000]},
        ])
        extracted = _json_payload(response)
    except Exception as exc:
        extracted = {"warnings": [f"Structured datasheet extraction unavailable: {str(exc)[:180]}"]}

    await _report(
        progress,
        "validation",
        "Validating pins and protocols",
        "Rejecting unsupported URLs, checking the online pin list against the database, and preparing safe catalogue updates.",
        5,
    )

    extracted_pins = extracted.get("pins") if isinstance(extracted.get("pins"), list) else []
    # The catalogue remains authoritative when populated. Online extraction
    # fills gaps; disagreements become warnings for human review.
    pins = existing_pins or extracted_pins
    normalized_pins = []
    for index, pin in enumerate(pins[:128]):
        if not isinstance(pin, dict) or not str(pin.get("name") or pin.get("label") or "").strip():
            continue
        pin_name = str(pin.get("name") or pin.get("label")).strip()[:80]
        normalized_pins.append({
            "name": pin_name,
            "label": str(pin.get("label") or pin_name).strip()[:80],
            "role": str(pin.get("role") or "gpio").strip()[:80],
            "voltage": pin.get("voltage") if isinstance(pin.get("voltage"), (int, float)) else None,
            "capabilities": str(pin.get("capabilities") or "").strip()[:300] or None,
        })
    claimed_datasheet = str(extracted.get("datasheet_url") or "").strip()
    allowed_urls = {str(component.get("datasheet_url") or ""), str(datasheet_url or ""), *(item["url"] for item in results)}
    final_datasheet_url = claimed_datasheet if claimed_datasheet in allowed_urls else datasheet_url
    extracted_protocols = _string_list(extracted.get("protocols"), limit=20, item_limit=40)
    protocols = list(dict.fromkeys([
        *(component.get("protocols") or []),
        *extracted_protocols,
        *infer_protocols(normalized_pins),
    ]))
    warnings = _string_list(extracted.get("warnings"), limit=30, item_limit=400)
    existing_names = {str(item.get("name") or item.get("label") or "").casefold() for item in existing_pins}
    extracted_names = {str(item.get("name") or item.get("label") or "").casefold() for item in extracted_pins}
    if existing_names and extracted_names and existing_names != extracted_names:
        warnings.append("The online pin list conflicts with the populated catalogue; catalogue pins were retained for review.")
    if claimed_datasheet and claimed_datasheet not in allowed_urls:
        warnings.append("The model returned a datasheet URL absent from the fetched evidence; it was rejected.")
    if not final_datasheet_url:
        warnings.append("No authoritative datasheet URL was found; component remains unverified.")
    if not normalized_pins:
        warnings.append("No evidenced pin list was available; pin assignment remains unresolved.")
    online_evidence = bool(
        datasheet_text
        or any(
            item["url"] == final_datasheet_url
            or "datasheet" in f"{item['title']} {item['snippet']}".casefold()
            for item in results
        )
    )
    if not online_evidence:
        warnings.append("Online cross-verification returned no usable evidence; existing catalogue facts were retained.")
    return {
        "component_id": component.get("id") or component.get("definition_id"),
        "name": name,
        "datasheet_url": final_datasheet_url,
        "source_urls": [item["url"] for item in results],
        "pins": normalized_pins,
        "pin_count": len(normalized_pins),
        "protocols": protocols,
        "operating_voltage": str(extracted.get("operating_voltage") or "Unresolved")[:120],
        "configuration_notes": _string_list(extracted.get("configuration_notes"), limit=30, item_limit=400),
        "warnings": list(dict.fromkeys(warnings)),
        "verified": bool(final_datasheet_url and normalized_pins and online_evidence),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def persist_component_verification(session: Session, verification: dict[str, Any]) -> None:
    component = session.exec(
        select(Component).where(Component.slug == verification.get("component_id"))
    ).first()
    if component is None:
        return
    component.datasheet_url = component.datasheet_url or verification.get("datasheet_url")
    component.protocols = list(dict.fromkeys([*(component.protocols or []), *(verification.get("protocols") or [])]))
    component.verification_sources = list(dict.fromkeys([*(component.verification_sources or []), *(verification.get("source_urls") or [])]))[:20]
    if verification.get("verified"):
        component.verified_at = datetime.now(timezone.utc)
    component.updated_at = datetime.now(timezone.utc)
    session.add(component)
    existing = session.exec(select(PinRow).where(PinRow.component_id == component.id)).all()
    if not existing:
        for index, pin in enumerate(verification.get("pins") or []):
            session.add(PinRow(
                component_id=component.id,
                name=pin["name"],
                label=pin.get("label") or pin["name"],
                role=pin.get("role") or "gpio",
                voltage=pin.get("voltage"),
                capabilities=pin.get("capabilities"),
                side="left" if index < len(verification.get("pins") or []) / 2 else "right",
                x=0 if index < len(verification.get("pins") or []) / 2 else 1,
                y=float(index),
            ))
    session.commit()


_CURATED_BOARD_SIGNALS: dict[str, dict[str, str]] = {
    "esp32dev": {
        "I2C_SDA": "GPIO21", "I2C_SCL": "GPIO22", "SPI_MOSI": "GPIO23",
        "SPI_MISO": "GPIO19", "SPI_SCK": "GPIO18", "UART_TX": "GPIO17", "UART_RX": "GPIO16",
    },
    "uno": {
        "I2C_SDA": "A4", "I2C_SCL": "A5", "SPI_MOSI": "D11",
        "SPI_MISO": "D12", "SPI_SCK": "D13", "UART_TX": "D1", "UART_RX": "D0",
    },
    "nanoatmega328": {
        "I2C_SDA": "A4", "I2C_SCL": "A5", "SPI_MOSI": "D11",
        "SPI_MISO": "D12", "SPI_SCK": "D13", "UART_TX": "D1", "UART_RX": "D0",
    },
    "megaatmega2560": {
        "I2C_SDA": "D20", "I2C_SCL": "D21", "SPI_MOSI": "D51",
        "SPI_MISO": "D50", "SPI_SCK": "D52", "UART_TX": "D18", "UART_RX": "D19",
    },
    "leonardo": {
        "I2C_SDA": "D2", "I2C_SCL": "D3", "SPI_MOSI": "MOSI",
        "SPI_MISO": "MISO", "SPI_SCK": "SCK", "UART_TX": "D1", "UART_RX": "D0",
    },
    "micro": {
        "I2C_SDA": "D2", "I2C_SCL": "D3", "SPI_MOSI": "MOSI",
        "SPI_MISO": "MISO", "SPI_SCK": "SCK", "UART_TX": "D1", "UART_RX": "D0",
    },
}


def _canonical_signal(signal_name: str) -> str | None:
    name = signal_name.upper()
    checks = {
        "I2C_SDA": ("I2C", "SDA"),
        "I2C_SCL": ("I2C", "SCL"),
        "SPI_MOSI": ("SPI", "MOSI"),
        "SPI_MISO": ("SPI", "MISO"),
        "SPI_SCK": ("SPI", "SCK"),
        "UART_TX": ("UART", "TX"),
        "UART_RX": ("UART", "RX"),
    }
    return next((key for key, tokens in checks.items() if all(token in name for token in tokens)), None)


def _board_signal_candidates(board: dict[str, Any]) -> tuple[dict[str, str], str, str]:
    candidates: dict[str, str] = {}
    for pin in board.get("pin_metadata") or []:
        pin_name = str(pin.get("name") or "")
        for signal in pin.get("signals") or []:
            signal_name = str(signal.get("name") or "").upper()
            if signal_name and signal_name not in candidates:
                candidates[signal_name] = pin_name
            canonical = _canonical_signal(signal_name)
            if canonical and canonical not in candidates:
                candidates[canonical] = pin_name
    if candidates:
        return candidates, "verified_signal_metadata", "Peripheral alternate functions came from the selected MCU metadata."
    board_id = str(board.get("id") or "")
    if board_id in _CURATED_BOARD_SIGNALS:
        return _CURATED_BOARD_SIGNALS[board_id], "curated_board_map", "Pins came from the curated board mapping."
    if board.get("arduino_pinout"):
        return {
            "I2C_SDA": "SDA", "I2C_SCL": "SCL", "SPI_MOSI": "MOSI",
            "SPI_MISO": "MISO", "SPI_SCK": "SCK", "UART_TX": "TX", "UART_RX": "RX",
        }, "framework_api", "Framework pin constants compile, but physical header positions require the board variant documentation."
    return {}, "unavailable", "No verified signal-to-pin mapping is available for this registry target."


def _arduino_gpio_pool(board: dict[str, Any]) -> list[str]:
    header = board.get("arduino_pinout") or {}
    values = header.get("digital") or [*header.get("left", []), *header.get("right", [])]
    pins = []
    for value in values:
        label = str(value)
        match = re.search(r"(?:GPIO|D)\d+", label, re.I)
        if match:
            pins.append(match.group(0).upper())
    family = str(board.get("family") or "").upper()
    if "ESP32" in family:
        # Avoid flash pins and the most common strapping/input-only traps in a
        # generic pool. Exact protocol mappings still come from curated data.
        unsafe = {"GPIO0", "GPIO2", "GPIO6", "GPIO7", "GPIO8", "GPIO9", "GPIO10", "GPIO11", "GPIO34", "GPIO35", "GPIO36", "GPIO37", "GPIO38", "GPIO39"}
        pins = [pin for pin in pins if pin not in unsafe]
    return list(dict.fromkeys(pins))


def design_pin_assignments(board: dict[str, Any], verifications: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates, mapping_source, mapping_note = _board_signal_candidates(board)
    assignments: list[dict[str, Any]] = []
    gpio_pool = [
        str(pin.get("name")) for pin in board.get("pin_metadata") or []
        if str(pin.get("type") or "").casefold() not in {"power", "reset", "boot"}
    ] or _arduino_gpio_pool(board)
    used_gpio: set[str] = set()
    signal_aliases = {
        "SDA": "I2C_SDA", "SCL": "I2C_SCL", "MOSI": "SPI_MOSI", "MISO": "SPI_MISO",
        "SCK": "SPI_SCK", "CLK": "SPI_SCK", "TX": "UART_TX", "RX": "UART_RX",
    }
    for verification in verifications:
        for pin in verification.get("pins") or []:
            name = str(pin.get("label") or pin.get("name") or "").upper()
            role = str(pin.get("role") or "").upper()
            tokens = set(re.findall(r"[A-Z0-9+.-]+", f"{name} {role}"))
            if tokens & POWER_NAMES:
                board_pin, signal, status, source = "3V3", "POWER", "resolved", "power_rail"
            elif tokens & GROUND_NAMES:
                board_pin, signal, status, source = "GND", "GROUND", "resolved", "power_rail"
            else:
                signal = next((mapped for alias, mapped in signal_aliases.items() if alias in tokens), "GPIO")
                board_pin = candidates.get(signal, "")
                if not board_pin:
                    board_pin = next((item for item in gpio_pool if item not in used_gpio), "UNRESOLVED")
                    if board_pin != "UNRESOLVED":
                        used_gpio.add(board_pin)
                source = mapping_source
                if board_pin == "UNRESOLVED":
                    status = "unresolved"
                elif mapping_source in {"verified_signal_metadata", "curated_board_map"}:
                    status = "resolved"
                else:
                    status = "provisional"
            assignments.append({
                "component_id": verification.get("component_id"),
                "component": verification.get("name"),
                "component_pin": pin.get("label") or pin.get("name"),
                "board_pin": board_pin,
                "signal": signal,
                "protocol": next((item for item in verification.get("protocols") or [] if item.upper() in signal), signal),
                "status": status,
                "source": source,
                "note": mapping_note if status == "provisional" else "",
            })
    return assignments


def render_pin_diagram(board: dict[str, Any], assignments: list[dict[str, Any]]) -> str:
    rows = "\n".join(
        f"| `{item['board_pin']}` | {item['signal']} | {item['component']}.{item['component_pin']} | {item['status']} | {item.get('source', '')} |"
        for item in assignments
    ) or "| Unresolved | - | - | unresolved | unavailable |"
    provisional = [item for item in assignments if item.get("status") == "provisional"]
    note = (
        "\n> Provisional mappings use framework pin constants. Confirm their physical header positions in the selected board variant documentation before wiring.\n"
        if provisional else ""
    )
    return f"""# Pin Diagram\n\nBoard: **{board.get('label')}** (`{board.get('id')}`)\n\n| Board pin | Signal | Connected component pin | Status | Source |\n|---|---|---|---|---|\n{rows}\n{note}"""


def render_connection_diagram(board: dict[str, Any], assignments: list[dict[str, Any]]) -> str:
    node_ids: dict[str, str] = {}
    lines = ["# Connection Diagram", "", "```mermaid", "flowchart LR", f"    BOARD[\"{board.get('label')}\"]"]
    for item in assignments:
        cid = str(item["component_id"])
        node = node_ids.setdefault(cid, f"C{len(node_ids) + 1}")
        if sum(1 for value in node_ids.values() if value == node) == 1 and not any(line.startswith(f"    {node}[") for line in lines):
            lines.append(f"    {node}[\"{item['component']}\"]")
        label = f"{item['board_pin']} ↔ {item['component_pin']} ({item['signal']})".replace('"', "'")
        lines.append(f"    BOARD -- \"{label}\" --> {node}")
    lines.extend(["```", "", "All power and protection requirements still marked unresolved in verification warnings must be closed before physical wiring."])
    return "\n".join(lines) + "\n"


def build_pin_configuration(board: dict[str, Any], assignments: list[dict[str, Any]], verifications: list[dict[str, Any]]) -> dict[str, Any]:
    protocols = sorted({protocol for item in verifications for protocol in item.get("protocols") or []})
    statuses = {str(item.get("status") or "unresolved") for item in assignments}
    mapping_quality = "unresolved" if "unresolved" in statuses else "provisional" if "provisional" in statuses else "verified"
    return {
        "board": {"id": board.get("id"), "label": board.get("label"), "mcu": board.get("mcu")},
        "protocols": protocols,
        "pin_mapping_quality": mapping_quality,
        "pin_assignments": assignments,
    }


def render_configuration(board: dict[str, Any], assignments: list[dict[str, Any]], verifications: list[dict[str, Any]]) -> str:
    return "# Pin And Protocol Configuration\n\n```json\n" + json.dumps(
        build_pin_configuration(board, assignments, verifications), indent=2
    ) + "\n```\n"


def render_phase3_verification(project_name: str, board: dict[str, Any], verifications: list[dict[str, Any]], assignments: list[dict[str, Any]]) -> str:
    blocks = []
    for item in verifications:
        warnings = "\n".join(f"  - {warning}" for warning in item.get("warnings") or []) or "  - None recorded."
        blocks.append(
            f"## {item['name']}\n\n"
            f"- Datasheet: {item.get('datasheet_url') or 'Not found'}\n"
            f"- Catalogue cross-check: {'verified' if item.get('verified') else 'unresolved'}\n"
            f"- Pin count: {item.get('pin_count', 0)}\n"
            f"- Protocols: {', '.join(item.get('protocols') or []) or 'Unresolved'}\n"
            f"- Operating voltage: {item.get('operating_voltage') or 'Unresolved'}\n"
            f"- Warnings:\n{warnings}"
        )
    unresolved = sum(1 for item in assignments if item.get("status") == "unresolved")
    provisional = sum(1 for item in assignments if item.get("status") == "provisional")
    return f"# {project_name} Integration Verification\n\n## Target\n\n- Board: {board.get('label')} (`{board.get('id')}`)\n- MCU: {board.get('mcu')}\n\n" + "\n\n".join(blocks) + f"\n\n## Pin Assignment Result\n\n- Connections planned: {len(assignments)}\n- Provisional assignments: {provisional}\n- Unresolved assignments: {unresolved}\n"
