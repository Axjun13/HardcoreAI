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
from boards.family_map import (
    derive_family_info,
    derive_openocd_interface,
    derive_avr_info,
    derive_espressif_info,
    derive_samd_info,
    SAMD_DEFAULT_OPENOCD_INTERFACE,
)
from boards.stm32_part import derive_package_pin_count

# PlatformIO's "platform" field (not "vendor") is what actually tells us the
# toolchain family — e.g. board id "uno" has platform "atmelavr", vendor
# "Arduino". Add new arches here as they're wired up (espressif32, atmelsam).
_PLATFORM_TO_ARCH: dict[str, str] = {
    "atmelavr": "avr",
    "espressif32": "xtensa",
    "espressif8266": "xtensa",
    "atmelsam": "arm-samd",
    "ststm32": "arm-stm32",
}

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
        frameworks = raw.get("frameworks", [])
        platform = raw.get("platform", "")
        arch = _PLATFORM_TO_ARCH.get(platform)
        if arch is None:
            arch = "arduino-generic" if "arduino" in frameworks else "arm-stm32"
        common = dict(
            id=raw["id"],
            label=f"{raw.get('mcu', raw['id'])} ({raw.get('name', raw['id'])})",
            vendor=raw.get("vendor", "unknown"),
            mcu=mcu,
            arch=arch,
            pio_platform=platform,
            flash_bytes=int(raw.get("rom", 65536)),
            ram_bytes=int(raw.get("ram", 20480)),
            f_cpu_hz=int(raw.get("fcpu", 72_000_000)),
            frameworks=frameworks,
        )

        if arch == "avr":
            avr_info = derive_avr_info(mcu)
            return Device(
                **common,
                family=avr_info["family"],
                core=avr_info["core"],
                avrdude_mcu=avr_info["avrdude_mcu"],
                avrdude_programmer=avr_info["avrdude_programmer"],
                upload_speed=int(raw.get("upload", {}).get("speed", 115200)),
                upload_protocol=avr_info["avrdude_programmer"],
                debug_tool="avrdude",
                supports_live_debug=False,  # no OpenOCD/GDB path for classic AVR bootloaders
                pinout_status="unavailable",  # Arduino digital/analog pin maps are curated in the seed, not derived
            )

        if arch == "xtensa":
            esp_info = derive_espressif_info(mcu)
            return Device(
                **common,
                family=esp_info["family"],
                core=esp_info["core"],
                upload_speed=int(raw.get("upload", {}).get("speed", 460800)),
                flash_mode="dio",
                flash_freq="40m",
                upload_protocol="esptool",
                debug_tool="esptool",
                supports_live_debug=False,  # JTAG debug exists on some ESP32 variants but isn't wired up here yet
                pinout_status="unavailable",
            )

        if arch == "arm-samd":
            samd_info = derive_samd_info(mcu)
            debug_tools = raw.get("debug", {}).get("tools", {})
            # Same signal STM32 boards use: PlatformIO's board JSON only
            # has a `debug.tools` entry when the board actually exposes a
            # debug port (onboard EDBG, or documented SWD pads with a
            # known default probe) — its absence means this specific
            # board has no wired-up debug connection, not just that we
            # haven't gotten to it yet.
            has_debug_port = bool(debug_tools)
            return Device(
                **common,
                family=samd_info["family"],
                core=samd_info["core"],
                upload_speed=int(raw.get("upload", {}).get("speed", 921600)),
                bossac_offset="0x2000",
                upload_protocol="sam-ba",
                debug_tool="openocd" if has_debug_port else "bossac",
                openocd_target=samd_info["openocd_target"] if has_debug_port else None,
                openocd_interface=(
                    derive_openocd_interface(debug_tools, fallback=SAMD_DEFAULT_OPENOCD_INTERFACE)
                    if has_debug_port else None
                ),
                supports_live_debug=has_debug_port,
                pinout_status="unavailable",
            )

        if arch == "arduino-generic":
            upload = raw.get("upload", {})
            protocols = upload.get("protocols") or []
            protocol = upload.get("protocol") or (protocols[0] if protocols else "serial")
            return Device(
                **common,
                family=platform.upper() if platform else "Arduino",
                core=mcu,
                upload_speed=int(upload.get("speed", 115200)),
                upload_protocol=protocol,
                debug_tool=protocol,
                supports_live_debug=False,
                pinout_status="unavailable",
            )

        # arm-stm32 (default/original path — unchanged behavior)
        family_info = derive_family_info(mcu)
        debug_tools = raw.get("debug", {}).get("tools", {})
        return Device(
            **common,
            family=family_info["family"],
            core=family_info["core"],
            hal_header=family_info["hal_header"],
            openocd_target=family_info["openocd_target"],
            openocd_interface=derive_openocd_interface(debug_tools),
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


def import_arduino_framework_boards() -> list[Device]:
    """Fetch every PlatformIO board that advertises Arduino framework support."""
    try:
        raw_boards = _run_pio_boards("")
    except Exception as exc:
        print(f"[pio_importer] all-board Arduino import failed: {exc}")
        return []

    devices = [
        _normalize(board)
        for board in raw_boards
        if "arduino" in (board.get("frameworks") or [])
    ]
    return [d for d in devices if d is not None]
