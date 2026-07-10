"""Imports board metadata from PlatformIO into HardcoreAI's own Device model.

Strategy mirrors api/routers/library_search.py: try the fast path, fall back
gracefully, never raise up to the caller. `pio boards --json-output` is
preferred over the registry REST API here because it returns full board
metadata (mcu, ram, rom, debug tools) in one call with no auth/rate-limit
concerns — the REST API is reserved as a future fallback if ever needed.
"""

from __future__ import annotations

import json
import subprocess

from boards.device import Device
from boards.family_map import derive_family_info, derive_openocd_interface
from boards.stm32_part import derive_package_pin_count

IMPORT_TIMEOUT_S = 60


def _run_pio_boards(query: str = "") -> list[dict]:
    """Runs `pio boards [query] --json-output`. Raises on failure — caller
    decides how to handle that (registry.refresh() catches it).

    Imports services.hardware lazily (not at module level) to avoid a
    circular import: hardware.py -> boards.registry -> pio_importer ->
    services.hardware would otherwise form a cycle at load time.
    """
    from services.hardware import ensure_platformio, pio_bin

    pio = pio_bin()
    if not pio:
        pio = ensure_platformio()

    cmd = [pio, "boards", "--json-output"]
    if query:
        cmd.insert(2, query)

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=IMPORT_TIMEOUT_S,
    )
    if result.returncode != 0:
        raise RuntimeError(f"`pio boards` failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


def _normalize(raw: dict) -> Device | None:
    """One PlatformIO board JSON object -> a Device. Returns None (rather
    than raising) for malformed entries so one bad board doesn't kill the
    whole import batch."""
    try:
        mcu = raw["mcu"]
        family_info = derive_family_info(mcu)
        debug_tools = raw.get("debug", {}).get("tools", {})

        return Device(
            id=raw["id"],
            label=f"{raw.get('mcu', raw['id'])} ({raw.get('name', raw['id'])})",
            vendor=raw.get("vendor", "unknown"),
            mcu=mcu,
            family=family_info["family"],
            core=family_info["core"],
            flash_bytes=int(raw.get("rom", 65536)),
            ram_bytes=int(raw.get("ram", 20480)),
            f_cpu_hz=int(raw.get("fcpu", 72_000_000)),
            hal_header=family_info["hal_header"],
            openocd_target=family_info["openocd_target"],
            openocd_interface=derive_openocd_interface(debug_tools),
            frameworks=raw.get("frameworks", []),
            package_pins=derive_package_pin_count(mcu),
            pinout_status="package_count_only",
        )
    except (KeyError, TypeError, ValueError):
        return None


def import_boards(query: str = "STM32") -> list[Device]:
    """Fetch + normalize boards. Never raises — returns [] on total failure
    so registry.refresh() can fall back to the existing curated seed."""
    try:
        raw_boards = _run_pio_boards(query)
    except Exception as exc:
        print(f"[pio_importer] import failed: {exc}")
        return []

    devices = [_normalize(b) for b in raw_boards]
    return [d for d in devices if d is not None]
