"""Board metadata endpoints — read-only surface over the Board Registry."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from boards import device_manager
from boards.device import Device
from boards.family_map import derive_family_info
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
    """Re-import board metadata from PlatformIO. Manual trigger for now —
    not run automatically on every request since it shells out to `pio`."""
    count = registry.refresh(query)
    return {"imported": count}



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
    upload_protocol: str = "stlink"
    debug_tool: str = "stlink"
    openocd_interface: str = "interface/stlink.cfg"
    frameworks: list[str] = ["stm32cube"]


@router.post("/custom")
def add_custom_board(payload: CustomBoardRequest) -> dict:
    """Register a custom STM32 board/target for projects not in PlatformIO."""
    info = derive_family_info(payload.mcu)
    if info["family"] == "unknown" and payload.mcu.upper().startswith("STM32"):
        info = {
            "family": "STM32_GENERIC",
            "core": "cortex-m4",
            "hal_header": "main.h",
            "openocd_target": "target/stm32f4x.cfg",
        }
    device = Device(
        id=payload.id.strip(),
        label=payload.label or payload.id.strip(),
        vendor=payload.vendor,
        mcu=payload.mcu.strip(),
        family=info["family"],
        core=info["core"],
        flash_bytes=payload.flash_bytes,
        ram_bytes=payload.ram_bytes,
        f_cpu_hz=payload.f_cpu_hz,
        hal_header=info["hal_header"],
        upload_protocol=payload.upload_protocol,
        debug_tool=payload.debug_tool,
        openocd_target=info["openocd_target"],
        openocd_interface=payload.openocd_interface,
        frameworks=payload.frameworks,
        package_pins=derive_package_pin_count(payload.mcu),
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
    """Change which board a project targets. Validates ownership and that
    the board_id actually exists in the registry before writing."""
    with db_session(user_id) as session:
        # Reuses the same ownership check every other project route uses —
        # raises 404 if this project doesn't belong to user_id.
        get_project_or_404(session, project_id, user_id)

        try:
            device = device_manager.set_project_board(project_id, payload.board_id, session)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    return {"project_id": project_id, "board": device.model_dump()}
