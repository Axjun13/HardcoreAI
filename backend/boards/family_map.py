"""Curated MCU-prefix -> family/core/HAL-header/OpenOCD-target mappings.

PlatformIO's board JSON gives us `mcu` (e.g. "STM32F446RET6") but not family,
core, HAL header, or OpenOCD target — these are derived here and are the one
part of the pipeline that has to be hand-maintained as new STM32 families
are added.
"""

# Longest/most-specific prefixes should be checked first if you ever add
# overlapping ones — for now these are all disjoint.
FAMILY_BY_MCU_PREFIX: dict[str, dict[str, str]] = {
    "STM32C5": {"family": "STM32C5", "core": "cortex-m33",
                "hal_header": "stm32c5xx_hal.h", "openocd_target": "target/stm32c5x.cfg"},
    "STM32C0": {"family": "STM32C0", "core": "cortex-m0plus",
                "hal_header": "stm32c0xx_hal.h", "openocd_target": "target/stm32c0x.cfg"},
    "STM32F1": {"family": "STM32F1", "core": "cortex-m3",
                "hal_header": "stm32f1xx_hal.h", "openocd_target": "target/stm32f1x.cfg"},
    "STM32F4": {"family": "STM32F4", "core": "cortex-m4",
                "hal_header": "stm32f4xx_hal.h", "openocd_target": "target/stm32f4x.cfg"},
    "STM32F0": {"family": "STM32F0", "core": "cortex-m0",
                "hal_header": "stm32f0xx_hal.h", "openocd_target": "target/stm32f0x.cfg"},
    "STM32F3": {"family": "STM32F3", "core": "cortex-m4",
                "hal_header": "stm32f3xx_hal.h", "openocd_target": "target/stm32f3x.cfg"},
    "STM32F7": {"family": "STM32F7", "core": "cortex-m7",
                "hal_header": "stm32f7xx_hal.h", "openocd_target": "target/stm32f7x.cfg"},
    "STM32L4": {"family": "STM32L4", "core": "cortex-m4",
                "hal_header": "stm32l4xx_hal.h", "openocd_target": "target/stm32l4x.cfg"},
    "STM32L0": {"family": "STM32L0", "core": "cortex-m0plus",
                "hal_header": "stm32l0xx_hal.h", "openocd_target": "target/stm32l0.cfg"},
    "STM32G0": {"family": "STM32G0", "core": "cortex-m0plus",
                "hal_header": "stm32g0xx_hal.h", "openocd_target": "target/stm32g0x.cfg"},
    "STM32G4": {"family": "STM32G4", "core": "cortex-m4",
                "hal_header": "stm32g4xx_hal.h", "openocd_target": "target/stm32g4x.cfg"},
    "STM32H7": {"family": "STM32H7", "core": "cortex-m7",
                "hal_header": "stm32h7xx_hal.h", "openocd_target": "target/stm32h7x.cfg"},
    "STM32L1": {"family": "STM32L1", "core": "cortex-m3",
                "hal_header": "stm32l1xx_hal.h", "openocd_target": "target/stm32l1.cfg"},
    "STM32L5": {"family": "STM32L5", "core": "cortex-m33",
                "hal_header": "stm32l5xx_hal.h", "openocd_target": "target/stm32l5x.cfg"},
    "STM32WB0": {"family": "STM32WB0", "core": "cortex-m0plus",
                 "hal_header": "stm32wb0x_hal.h", "openocd_target": "target/stm32wb0x.cfg"},
    "STM32WBA": {"family": "STM32WBA", "core": "cortex-m33",
                 "hal_header": "stm32wbaxx_hal.h", "openocd_target": "target/stm32wbax.cfg"},
    "STM32WB": {"family": "STM32WB", "core": "cortex-m4",
                "hal_header": "stm32wbxx_hal.h", "openocd_target": "target/stm32wbx.cfg"},
    "STM32U5": {"family": "STM32U5", "core": "cortex-m33",
                "hal_header": "stm32u5xx_hal.h", "openocd_target": "target/stm32u5x.cfg"},
    "STM32U3": {"family": "STM32U3", "core": "cortex-m33",
                "hal_header": "stm32u3xx_hal.h", "openocd_target": "target/stm32u3x.cfg"},
    "STM32WL": {"family": "STM32WL", "core": "cortex-m4",
                "hal_header": "stm32wlxx_hal.h", "openocd_target": "target/stm32wlx.cfg"},
    "STM32F2": {"family": "STM32F2", "core": "cortex-m3",
                "hal_header": "stm32f2xx_hal.h", "openocd_target": "target/stm32f2x.cfg"},
    "STM32H5": {"family": "STM32H5", "core": "cortex-m33",
                "hal_header": "stm32h5xx_hal.h", "openocd_target": "target/stm32h5x.cfg"},
    "STM32U0": {"family": "STM32U0", "core": "cortex-m0plus",
                "hal_header": "stm32u0xx_hal.h", "openocd_target": "target/stm32u0x.cfg"},
    "STM32N6": {"family": "STM32N6", "core": "cortex-m55",
                "hal_header": "stm32n6xx_hal.h", "openocd_target": "target/stm32n6x.cfg"},
    "STM32V8": {"family": "STM32V8", "core": "cortex-m85",
                "hal_header": "stm32v8xx_hal.h", "openocd_target": "target/stm32v8x.cfg"},
}

_DEFAULT_ENTRY = {"family": "unknown", "core": "cortex-m4",
                   "hal_header": "main.h", "openocd_target": "target/stm32f4x.cfg"}


# AVR mcu (e.g. "ATMEGA328P") -> family/avrdude part/default programmer.
# Unlike STM32, AVR has no HAL header or OpenOCD target — flashing goes
# through avrdude, and the programmer depends on the board's bootloader
# (Uno/Nano/Mega use the "arduino"/"wiring" stk500 bootloader over serial;
# Leonardo/Micro use the "avr109" caterina bootloader over a virtual USB CDC).
AVR_FAMILY_BY_MCU_PREFIX: dict[str, dict[str, str]] = {
    "ATMEGA328P": {"family": "AVR-Mega", "core": "avr", "avrdude_mcu": "atmega328p",
                   "avrdude_programmer": "arduino"},
    "ATMEGA328": {"family": "AVR-Mega", "core": "avr", "avrdude_mcu": "atmega328p",
                  "avrdude_programmer": "arduino"},
    "ATMEGA2560": {"family": "AVR-Mega", "core": "avr", "avrdude_mcu": "atmega2560",
                   "avrdude_programmer": "wiring"},
    "ATMEGA32U4": {"family": "AVR-Mega", "core": "avr", "avrdude_mcu": "atmega32u4",
                   "avrdude_programmer": "avr109"},
    "ATMEGA1280": {"family": "AVR-Mega", "core": "avr", "avrdude_mcu": "atmega1280",
                   "avrdude_programmer": "arduino"},
    "ATMEGA168": {"family": "AVR-Mega", "core": "avr", "avrdude_mcu": "atmega168",
                  "avrdude_programmer": "arduino"},
    "ATTINY85": {"family": "AVR-Tiny", "core": "avr", "avrdude_mcu": "attiny85",
                 "avrdude_programmer": "usbtiny"},
    "ATTINY84": {"family": "AVR-Tiny", "core": "avr", "avrdude_mcu": "attiny84",
                 "avrdude_programmer": "usbtiny"},
}

_AVR_DEFAULT_ENTRY = {"family": "AVR-Mega", "core": "avr", "avrdude_mcu": "atmega328p",
                      "avrdude_programmer": "arduino"}


# ESP32/ESP8266 — flashed via esptool (not avrdude, not OpenOCD). Unlike
# AVR's flat mcu-prefix table, PlatformIO's board `mcu` field for these is
# already the exact chip name we want (esp32, esp32s3, esp8266), so this is
# a lookup by chip id rather than a prefix scan.
ESPRESSIF_CHIP_INFO: dict[str, dict[str, str]] = {
    "esp32": {"family": "ESP32", "core": "xtensa-lx6"},
    "esp32s2": {"family": "ESP32-S2", "core": "xtensa-lx7"},
    "esp32s3": {"family": "ESP32-S3", "core": "xtensa-lx7"},
    "esp32c2": {"family": "ESP32-C2", "core": "riscv32"},
    "esp32c3": {"family": "ESP32-C3", "core": "riscv32"},
    "esp32c5": {"family": "ESP32-C5", "core": "riscv32"},
    "esp32c6": {"family": "ESP32-C6", "core": "riscv32"},
    "esp32h2": {"family": "ESP32-H2", "core": "riscv32"},
    "esp32p4": {"family": "ESP32-P4", "core": "riscv32"},
    "esp8266": {"family": "ESP8266", "core": "xtensa-lx106"},
}
_ESPRESSIF_DEFAULT_ENTRY = {"family": "ESP32", "core": "xtensa-lx6"}


def derive_espressif_info(mcu: str) -> dict[str, str]:
    """mcu like 'esp32' / 'ESP32S3' -> family/core. Falls back to a
    reasonable ESP32 default for unrecognized chip ids rather than raising,
    same best-effort philosophy as derive_avr_info."""
    key = "".join(ch for ch in mcu.lower() if ch.isalnum())
    return ESPRESSIF_CHIP_INFO.get(key, _ESPRESSIF_DEFAULT_ENTRY)


# SAMD (Arduino MKR/Zero family) — flashed via bossac over the native-USB
# UF2/SAM-BA bootloader (1200bps touch-reset), not avrdude or esptool.
# Unlike classic AVR, SAMD is a real Cortex-M part, and boards with an
# actual on-chip debug connection (Zero's onboard EDBG, or any SAMD wired
# to an external CMSIS-DAP/J-Link probe via its SWD pads) can do real GDB
# debugging through OpenOCD, same pipeline as STM32 — arm-none-eabi-gdb
# doesn't care that the target is SAMD instead of STM32.
#
# `openocd_target`/`openocd_interface` here are die-level metadata (which
# OpenOCD target script matches this chip, and what interface a SAMD
# debug probe normally speaks) — NOT a claim that every board with this
# die has a debug port wired up. Whether a *board* actually exposes one
# is a per-board fact that lives on the board's `supports_live_debug` flag
# in the registry (e.g. Arduino Zero's onboard EDBG: True; MKR boards,
# which have no onboard debugger and only expose SWD on unpopulated
# pads: False until someone wires up an external probe and flips it).
SAMD_CHIP_INFO: dict[str, dict[str, str]] = {
    "samd21g18a": {"family": "SAMD21", "core": "cortex-m0+",
                   "openocd_target": "target/at91samdXX.cfg"},
    "samd21e18a": {"family": "SAMD21", "core": "cortex-m0+",
                   "openocd_target": "target/at91samdXX.cfg"},
    "samd51j19a": {"family": "SAMD51", "core": "cortex-m4",
                   "openocd_target": "target/atsame5x.cfg"},
    "samd51g19a": {"family": "SAMD51", "core": "cortex-m4",
                   "openocd_target": "target/atsame5x.cfg"},
}
_SAMD_DEFAULT_ENTRY = {"family": "SAMD21", "core": "cortex-m0+",
                        "openocd_target": "target/at91samdXX.cfg"}

# EDBG (Zero) and the vast majority of third-party SAMD debug probes
# implement the CMSIS-DAP protocol, so this is the sane default rather
# than assuming ST-Link (which doesn't support SAMD at all).
SAMD_DEFAULT_OPENOCD_INTERFACE = "interface/cmsis-dap.cfg"


def derive_samd_info(mcu: str) -> dict[str, str]:
    return SAMD_CHIP_INFO.get(mcu.lower(), _SAMD_DEFAULT_ENTRY)


def derive_avr_info(mcu: str) -> dict[str, str]:
    """mcu like 'ATMEGA328P-PU' -> family/core/avrdude_mcu/avrdude_programmer.
    Same best-effort-fallback philosophy as derive_family_info: an
    unrecognized AVR part still imports, flagged via family=='AVR-Mega'
    default rather than crashing the batch."""
    mcu_upper = mcu.upper()
    for prefix, info in sorted(AVR_FAMILY_BY_MCU_PREFIX.items(), key=lambda item: len(item[0]), reverse=True):
        if mcu_upper.startswith(prefix):
            return info
    return _AVR_DEFAULT_ENTRY


def derive_family_info(mcu: str) -> dict[str, str]:
    """mcu like 'STM32F446RET6' -> family/core/hal_header/openocd_target.
    Falls back to a generic Cortex-M4 guess for unrecognized prefixes rather
    than raising — an unknown board should still import with best-effort
    metadata, just flagged (see Device.family == "unknown") rather than
    crashing the whole import batch."""
    mcu_upper = mcu.upper()
    for prefix, info in sorted(FAMILY_BY_MCU_PREFIX.items(), key=lambda item: len(item[0]), reverse=True):
        if mcu_upper.startswith(prefix):
            return info
    return _DEFAULT_ENTRY


_PROBE_TO_INTERFACE_CFG = {
    "stlink": "interface/stlink.cfg",
    "jlink": "interface/jlink.cfg",
    "cmsis-dap": "interface/cmsis-dap.cfg",
    "blackmagic": "interface/cmsis-dap.cfg",  # closest generic fallback
    "edbg": "interface/cmsis-dap.cfg",  # Arduino Zero's onboard debugger, CMSIS-DAP-compatible
}


def derive_openocd_interface(debug_tools: dict, fallback: str = "interface/stlink.cfg") -> str:
    """Pick the default/onboard probe from PIO's debug.tools dict, map to
    an OpenOCD interface cfg. `fallback` is used both when nothing is
    marked default/onboard and when a recognized-but-unmapped probe name
    shows up — callers outside the STM32 path (e.g. SAMD, whose debugger
    is never an ST-Link) should pass their own family-appropriate default
    rather than silently getting stlink.cfg."""
    for name, meta in debug_tools.items():
        if meta.get("default") or meta.get("onboard"):
            return _PROBE_TO_INTERFACE_CFG.get(name, fallback)
    return fallback
