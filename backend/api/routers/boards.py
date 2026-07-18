"""Board metadata endpoints — read-only surface over the Board Registry."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from boards.device import Device
from boards.family_map import (
    derive_family_info,
    derive_avr_info,
    derive_espressif_info,
    derive_samd_info,
)
from boards.registry import registry
from boards import stm32_metadata
from boards.stm32_part import derive_package_pin_count
from core.security import get_current_user_id
from db.session import db_session
from services.projects import get_project_or_404

router = APIRouter(prefix="/api/boards", tags=["Boards"])


@router.get("")
def list_boards(family: str | None = None) -> list[dict]:
    """List all known boards (curated + imported), optionally filtered by family."""
    boards = registry.list()
    if family:
        boards = [b for b in boards if b.family.lower() == family.lower()]
    return [b.model_dump() for b in boards]


@router.get("/{board_id}")
def get_board(board_id: str) -> dict:
    device = registry.get(board_id)
    if not device:
        raise HTTPException(status_code=404, detail=f"Unknown board: {board_id}")
    return device.model_dump()


@router.post("/refresh")
def refresh_boards(query: str = "STM32") -> dict:
    """Re-import a single platform query's worth of board metadata from
    PlatformIO (e.g. query="STM32", "Arduino", "ESP32", "ESP8266", "MKR",
    "Zero"). Manual trigger for now — not run automatically on every
    request since it shells out to `pio`. For pulling every platform at
    once, use POST /refresh-all instead."""
    count = registry.refresh(query)
    return {"query": query, "imported": count}


@router.post("/refresh-all")
def refresh_all_boards() -> dict:
    """Re-import board metadata for every known platform (STM32, Arduino,
    ESP32, ESP8266, MKR, Zero) in one call. registry.refresh_all() already
    did this work — this just exposes it, since previously the only
    reachable route defaulted to STM32 alone and there was no way to grow
    the AVR/ESP32/ESP8266/SAMD side of the catalog from the UI."""
    breakdown = registry.refresh_all()
    return {"imported_by_platform": breakdown, "imported": sum(breakdown.values())}



class SetProjectBoardRequest(BaseModel):
    board_id: str


class CustomBoardRequest(BaseModel):
    id: str
    label: str | None = None
    mcu: str
    vendor: str = "custom"
    flash_bytes: int = 65536
    ram_bytes: int = 20480
    f_cpu_hz: int = 72_000_000
    # Optional — if omitted, arch is guessed from `mcu` the same way
    # pio_importer._normalize() does it (ATMEGA*/ATTINY* -> avr, esp32*/
    # esp8266 -> xtensa, samd* -> arm-samd, else arm-stm32). Pass this
    # explicitly if a custom part number doesn't match any of those
    # prefixes but isn't STM32 either.
    arch: str | None = None
    pio_platform: str | None = None
    upload_protocol: str | None = None
    debug_tool: str | None = None
    openocd_interface: str = "interface/stlink.cfg"
    frameworks: list[str] | None = None
    # AVR-only
    avrdude_programmer: str | None = None
    # ESP-only
    flash_mode: str = "dio"
    flash_freq: str = "40m"
    # SAMD-only
    bossac_offset: str = "0x2000"


def _guess_arch(mcu: str) -> str:
    """Same best-effort prefix heuristic pio_importer._normalize() uses for
    boards imported from PlatformIO, applied here so hand-added custom
    boards get routed to the right toolchain/codegen path too instead of
    always landing on the STM32/OpenOCD path regardless of MCU."""
    mcu_upper = mcu.upper()
    if mcu_upper.startswith("ATMEGA") or mcu_upper.startswith("ATTINY"):
        return "avr"
    mcu_lower = mcu.lower()
    if mcu_lower.startswith("esp32") or mcu_lower.startswith("esp8266"):
        return "xtensa"
    if mcu_lower.startswith("samd"):
        return "arm-samd"
    return "arm-stm32"


@router.post("/custom")
def add_custom_board(payload: CustomBoardRequest) -> dict:
    """Register a custom board/target for projects not in PlatformIO.
    Previously this only ever built an STM32/OpenOCD Device regardless of
    the MCU passed in, so a hand-added AVR/ESP32/SAMD board would silently
    get STM32 fields (stlink upload, an OpenOCD target, stm32cube
    framework) that don't apply to it. Now it dispatches on arch the same
    way pio_importer.py and the board registry do."""
    mcu = payload.mcu.strip()
    arch = payload.arch or _guess_arch(mcu)

    if arch == "avr":
        avr_info = derive_avr_info(mcu)
        device = Device(
            id=payload.id.strip(), label=payload.label or payload.id.strip(),
            vendor=payload.vendor, mcu=mcu, arch="avr",
            family=avr_info["family"], core=avr_info["core"],
            flash_bytes=payload.flash_bytes, ram_bytes=payload.ram_bytes,
            f_cpu_hz=payload.f_cpu_hz,
            avrdude_mcu=avr_info["avrdude_mcu"],
            avrdude_programmer=payload.avrdude_programmer or avr_info["avrdude_programmer"],
            upload_protocol=payload.upload_protocol or avr_info["avrdude_programmer"],
            debug_tool=payload.debug_tool or "avrdude",
            supports_live_debug=False,
            frameworks=payload.frameworks or ["arduino"],
            pinout_status="unavailable",
        )
    elif arch == "xtensa":
        esp_info = derive_espressif_info(mcu)
        device = Device(
            id=payload.id.strip(), label=payload.label or payload.id.strip(),
            vendor=payload.vendor, mcu=mcu, arch="xtensa",
            family=esp_info["family"], core=esp_info["core"],
            flash_bytes=payload.flash_bytes, ram_bytes=payload.ram_bytes,
            f_cpu_hz=payload.f_cpu_hz,
            flash_mode=payload.flash_mode, flash_freq=payload.flash_freq,
            upload_protocol=payload.upload_protocol or "esptool",
            debug_tool=payload.debug_tool or "esptool",
            supports_live_debug=False,
            frameworks=payload.frameworks or ["arduino"],
            pinout_status="unavailable",
        )
    elif arch == "arm-samd":
        samd_info = derive_samd_info(mcu)
        device = Device(
            id=payload.id.strip(), label=payload.label or payload.id.strip(),
            vendor=payload.vendor, mcu=mcu, arch="arm-samd",
            family=samd_info["family"], core=samd_info["core"],
            flash_bytes=payload.flash_bytes, ram_bytes=payload.ram_bytes,
            f_cpu_hz=payload.f_cpu_hz,
            bossac_offset=payload.bossac_offset,
            upload_protocol=payload.upload_protocol or "sam-ba",
            debug_tool=payload.debug_tool or "bossac",
            supports_live_debug=False,
            frameworks=payload.frameworks or ["arduino"],
            pinout_status="unavailable",
        )
    elif arch == "arduino-generic":
        device = Device(
            id=payload.id.strip(), label=payload.label or payload.id.strip(),
            vendor=payload.vendor, mcu=mcu, arch="arduino-generic",
            pio_platform=payload.pio_platform,
            family=(payload.pio_platform or "Arduino").upper(),
            core=mcu,
            flash_bytes=payload.flash_bytes, ram_bytes=payload.ram_bytes,
            f_cpu_hz=payload.f_cpu_hz,
            upload_protocol=payload.upload_protocol or "serial",
            debug_tool=payload.debug_tool or "serial",
            supports_live_debug=False,
            frameworks=payload.frameworks or ["arduino"],
            pinout_status="unavailable",
        )
    else:
        info = derive_family_info(mcu)
        if info["family"] == "unknown" and mcu.upper().startswith("STM32"):
            info = {
                "family": "STM32_GENERIC",
                "core": "cortex-m4",
                "hal_header": "main.h",
                "openocd_target": "target/stm32f4x.cfg",
            }
        device = Device(
            id=payload.id.strip(), label=payload.label or payload.id.strip(),
            vendor=payload.vendor, mcu=mcu, arch="arm-stm32",
            family=info["family"], core=info["core"],
            flash_bytes=payload.flash_bytes, ram_bytes=payload.ram_bytes,
            f_cpu_hz=payload.f_cpu_hz,
            hal_header=info["hal_header"],
            upload_protocol=payload.upload_protocol or "stlink",
            debug_tool=payload.debug_tool or "stlink",
            openocd_target=info["openocd_target"],
            openocd_interface=payload.openocd_interface,
            frameworks=payload.frameworks or ["stm32cube"],
            package_pins=derive_package_pin_count(mcu),
            pinout_status="package_count_only",
        )

    return registry.add_custom(device).model_dump()


@router.get("/stm32-data/status")
def stm32_data_status() -> dict:
    return stm32_metadata.metadata_status()


@router.post("/stm32-data/import")
def import_stm32_data(source_dir: str | None = None) -> dict:
    """Clone/read ST STM32_open_pin_data and build HardcoreAI's metadata cache."""
    try:
        return stm32_metadata.build_metadata_cache(source_dir)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/mcu/{mcu}/metadata")
def get_mcu_metadata(mcu: str) -> dict:
    meta = stm32_metadata.get_mcu_metadata(mcu)
    if not meta:
        raise HTTPException(
            status_code=404,
            detail="STM32 metadata not found. Import STM32 data first.",
        )
    return meta


@router.post("/mcu/{mcu}/validate-peripherals")
def validate_mcu_peripherals(mcu: str, peripheral_ids: list[str]) -> dict:
    return stm32_metadata.validate_peripherals(mcu, peripheral_ids)


@router.patch("/projects/{project_id}")
def set_project_board(
    project_id: str,
    payload: SetProjectBoardRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """Change the board and atomically configure its PlatformIO environment."""
    with db_session(user_id) as session:
        project = get_project_or_404(session, project_id, user_id)

        try:
            from services.hardware import configure_project_environment

            device, _content, path = configure_project_environment(
                project_id,
                payload.board_id,
                session=session,
                project=project,
            )
            session.commit()
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    return {
        "project_id": project_id,
        "board": device.model_dump(),
        "platformio_path": str(path),
    }
