"""Data-driven curated board catalog.

This module intentionally contains no board-specific conditionals.  Adding a
board is a JSON edit; unknown technical fields remain absent/null rather than
being guessed.  PlatformIO mappings are only present when the catalog source
explicitly identifies a PlatformIO board id.
"""

from __future__ import annotations

import json
from pathlib import Path

from boards.device import Device

CATALOG_PATH = Path(__file__).resolve().parent / "catalog" / "priority.json"


def load_catalog() -> dict[str, Device]:
    """Load curated entries, rejecting malformed/duplicate records loudly.

    The registry remains available even when this file is unavailable, so a
    packaging error never removes the pre-existing seed/imported boards.
    """
    if not CATALOG_PATH.exists():
        return {}
    raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    result: dict[str, Device] = {}
    for entry in raw.get("boards", []):
        board_id = entry.get("id")
        if not board_id or board_id in result:
            raise ValueError(f"Invalid or duplicate catalog board id: {board_id!r}")
        data = dict(entry)
        data["label"] = data.pop("name")
        data["vendor"] = data.get("manufacturer", "unknown").lower()
        data.setdefault("pio_platform", data.get("platformio_platform"))
        data.setdefault("platformio_board_id", data.get("id") if data.get("platformio_platform") else None)
        data.setdefault("flash_bytes", 0)
        data.setdefault("ram_bytes", 0)
        data.setdefault("f_cpu_hz", 0)
        data.setdefault("frameworks", [])
        data.setdefault("upload_protocol", "unsupported")
        data.setdefault("debug_tool", "unsupported")
        data.setdefault("supports_live_debug", False)
        result[board_id] = Device(**data)
    return result


def validate_catalog() -> list[str]:
    """Return validation errors without importing PlatformIO or hardware tools."""
    errors: list[str] = []
    raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    seen: set[str] = set()
    for index, entry in enumerate(raw.get("boards", [])):
        prefix = f"boards[{index}]"
        for field in ("id", "name", "manufacturer", "mcu_manufacturer", "family", "mcu", "architecture"):
            if not entry.get(field):
                errors.append(f"{prefix}: missing required {field}")
        board_id = entry.get("id")
        if board_id in seen:
            errors.append(f"{prefix}: duplicate id {board_id}")
        seen.add(board_id)
        if entry.get("platformio_board_id") and not entry.get("platformio_platform"):
            errors.append(f"{prefix}: PlatformIO board id without platform")
    try:
        load_catalog()
    except (ValueError, TypeError) as exc:
        errors.append(str(exc))
    return errors
