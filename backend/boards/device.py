from pydantic import BaseModel

class Device(BaseModel):
    id: str
    label: str
    vendor: str = "unknown"
    mcu: str
    family: str
    core: str = "cortex-m3"
    flash_bytes: int = 65536
    ram_bytes: int = 20480
    f_cpu_hz: int = 72_000_000
    hal_header: str
    upload_protocol: str = "stlink"
    debug_tool: str = "stlink"
    openocd_target: str
    openocd_interface: str = "interface/stlink.cfg"
    frameworks: list[str] = ["stm32cube"]
    full_pinout: list[str] | None = None
    package_pins: int | None = None
    pinout_status: str = "unavailable"
    pin_metadata: list[dict] | None = None
