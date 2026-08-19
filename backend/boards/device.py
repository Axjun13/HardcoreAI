from pydantic import BaseModel

# Arches whose firmware is written against the Arduino framework API
# (setup()/loop(), pinMode, Serial, etc.) rather than a vendor HAL — used
# throughout the codebase to dispatch codegen/scaffolding/context-building
# without repeating an arch-list literal at every call site.
ARDUINO_FRAMEWORK_ARCHES = {"avr", "xtensa", "arm-samd", "arm-renesas", "arduino-generic"}


def uses_arduino_framework(device: "Device | None") -> bool:
    if device is None:
        return False
    return device.arch in ARDUINO_FRAMEWORK_ARCHES and "arduino" in (device.frameworks or [])


def uses_espidf_framework(device: "Device | None") -> bool:
    if device is None:
        return False
    return device.arch == "xtensa" and "espidf" in (device.frameworks or [])

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
    pio_platform: str | None = None

    # arch selects which toolchain/codegen/debug path the rest of the app
    # uses. "arm-stm32" is the original (and only, until now) value — every
    # STM32-only field below stays required-in-practice for that arch but
    # is Optional[...] at the model level so non-ARM boards (AVR, etc.)
    # don't have to fake OpenOCD/HAL metadata that doesn't apply to them.
    arch: str = "arm-stm32"  # "arm-stm32" | "avr" | "xtensa" | "arm-samd" | "arm-renesas" | "arduino-generic"

    # --- STM32/OpenOCD-family fields (arch == "arm-stm32") ---
    hal_header: str | None = None
    openocd_target: str | None = None
    openocd_interface: str | None = "interface/stlink.cfg"

    # --- AVR/avrdude fields (arch == "avr") ---
    avrdude_mcu: str | None = None          # avrdude -p, e.g. "atmega328p"
    avrdude_programmer: str | None = None   # avrdude -c, e.g. "arduino", "avr109", "wiring"
    upload_speed: int | None = None         # bootloader baud, e.g. 115200

    # --- ESP32/ESP8266/esptool fields (arch == "xtensa") ---
    flash_mode: str | None = None           # "dio" | "qio" etc.
    flash_freq: str | None = None           # "40m" | "80m" etc.

    # --- SAMD/bossac fields (arch == "arm-samd") ---
    bossac_offset: str | None = None        # flash offset past the UF2 bootloader, e.g. "0x2000"

    upload_protocol: str = "stlink"
    debug_tool: str = "stlink"
    supports_live_debug: bool = True        # False for classic AVR (no on-chip debug via bootloader)
    frameworks: list[str] = ["stm32cube"]
    full_pinout: list[str] | None = None
    package_pins: int | None = None
    pinout_status: str = "unavailable"
    pin_metadata: list[dict] | None = None
    # Header-style pin labels for Arduino boards (see boards/pinout.py
    # get_arduino_pinout) — a different shape from full_pinout (dict of
    # left/right or digital/analog lists vs a flat chip-package list), so
    # it's a separate field rather than overloading full_pinout.
    arduino_pinout: dict | None = None

    # Catalog fields are deliberately optional: a missing value means the
    # source did not establish it, never an inferred specification.  Keeping
    # these on Device also means existing registry/API consumers continue to
    # receive the original fields unchanged.
    manufacturer: str | None = None          # board manufacturer / brand
    mcu_manufacturer: str | None = None      # silicon manufacturer
    architecture: str | None = None          # display taxonomy, e.g. ARM Cortex-M4
    series: str | None = None
    variant: str | None = None
    board_type: str | None = None
    description: str | None = None
    voltage: str | None = None
    gpio_count: int | None = None
    adc_channels: int | None = None
    dac_channels: int | None = None
    pwm_channels: int | None = None
    uart: int | None = None
    spi: int | None = None
    i2c: int | None = None
    can: bool | None = None
    usb: bool | None = None
    ethernet: bool | None = None
    wifi: bool | None = None
    bluetooth: bool | None = None
    debug_interface: list[str] | None = None
    debugger: list[str] | None = None
    bootloader: str | None = None
    platformio_board_id: str | None = None
    toolchain: str | None = None
    datasheet_url: str | None = None
    manufacturer_url: str | None = None
    documentation_url: str | None = None
    supported: bool = True
    availability: str | None = None
    qemu_supported: bool | None = None
