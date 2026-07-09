"""Curated MCU-prefix -> family/core/HAL-header/OpenOCD-target mappings.

PlatformIO's board JSON gives us `mcu` (e.g. "STM32F446RET6") but not family,
core, HAL header, or OpenOCD target — these are derived here and are the one
part of the pipeline that has to be hand-maintained as new STM32 families
are added.
"""

# Longest/most-specific prefixes should be checked first if you ever add
# overlapping ones — for now these are all disjoint.
FAMILY_BY_MCU_PREFIX: dict[str, dict[str, str]] = {
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
    "STM32WB": {"family": "STM32WB", "core": "cortex-m4",
                "hal_header": "stm32wbxx_hal.h", "openocd_target": "target/stm32wbx.cfg"},
    "STM32U5": {"family": "STM32U5", "core": "cortex-m33",
                "hal_header": "stm32u5xx_hal.h", "openocd_target": "target/stm32u5x.cfg"},
    "STM32WL": {"family": "STM32WL", "core": "cortex-m4",
                "hal_header": "stm32wlxx_hal.h", "openocd_target": "target/stm32wlx.cfg"},
    "STM32F2": {"family": "STM32F2", "core": "cortex-m3",
                "hal_header": "stm32f2xx_hal.h", "openocd_target": "target/stm32f2x.cfg"},
    "STM32H5": {"family": "STM32H5", "core": "cortex-m33",
                "hal_header": "stm32h5xx_hal.h", "openocd_target": "target/stm32h5x.cfg"},
}

_DEFAULT_ENTRY = {"family": "unknown", "core": "cortex-m4",
                   "hal_header": "main.h", "openocd_target": "target/stm32f4x.cfg"}


def derive_family_info(mcu: str) -> dict[str, str]:
    """mcu like 'STM32F446RET6' -> family/core/hal_header/openocd_target.
    Falls back to a generic Cortex-M4 guess for unrecognized prefixes rather
    than raising — an unknown board should still import with best-effort
    metadata, just flagged (see Device.family == "unknown") rather than
    crashing the whole import batch."""
    mcu_upper = mcu.upper()
    for prefix, info in FAMILY_BY_MCU_PREFIX.items():
        if mcu_upper.startswith(prefix):
            return info
    return _DEFAULT_ENTRY


_PROBE_TO_INTERFACE_CFG = {
    "stlink": "interface/stlink.cfg",
    "jlink": "interface/jlink.cfg",
    "cmsis-dap": "interface/cmsis-dap.cfg",
    "blackmagic": "interface/cmsis-dap.cfg",  # closest generic fallback
}


def derive_openocd_interface(debug_tools: dict) -> str:
    """Pick the default/onboard probe from PIO's debug.tools dict, map to
    an OpenOCD interface cfg. Falls back to stlink if nothing marked default."""
    for name, meta in debug_tools.items():
        if meta.get("default") or meta.get("onboard"):
            return _PROBE_TO_INTERFACE_CFG.get(name, "interface/stlink.cfg")
    return "interface/stlink.cfg"