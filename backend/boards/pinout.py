"""Per-package pin lists — the physical pinout of an MCU package (LQFP48,
LQFP64, etc.), in silkscreen/datasheet pin-number order. One table per
package covers every board that uses that package, since the package
defines the pin layout, not the specific board.

PlatformIO has no equivalent data — this is entirely hand-authored from
datasheets, moved here from the frontend's old bluePillPins constant.
"""

# STM32F103C8T6 LQFP48 — moved from frontend/src/store.ts's old bluePillPins.
LQFP48_F1 = [
    "VBAT", "PC13", "PC14", "PC15", "PD0", "PD1", "NRST", "VSSA",
    "VDDA", "PA0", "PA1", "PA2", "PA3", "PA4", "PA5", "PA6",
    "PA7", "PB0", "PB1", "PB2", "PB10", "PB11", "VSS", "VDD",
    "PB12", "PB13", "PB14", "PB15", "PA8", "PA9", "PA10", "PA11",
    "PA12", "PA13", "VSS", "VDD", "PA14", "PA15", "PB3", "PB4",
    "PB5", "PB6", "PB7", "BOOT0", "PB8", "PB9", "VSS", "VDD",
]

# Standard Nucleo-64 LQFP64 package pinout (F401RE/F446RE/L476RG/G431RB/
# L152RE/etc. — verify per-part against its datasheet before trusting on
# unfamiliar boards; this is the common LQFP64 pin order ST uses across
# most mainstream-line Nucleo-64 parts).
LQFP64_NUCLEO64 = [
    "VBAT", "PC13", "PC14", "PC15", "PH0", "PH1", "NRST", "PC0",
    "PC1", "PC2", "PC3", "VSSA", "VDDA", "PA0", "PA1", "PA2",
    "PA3", "VSS", "VDD", "PA4", "PA5", "PA6", "PA7", "PC4",
    "PC5", "PB0", "PB1", "PB2", "PB10", "PB11", "VSS", "VDD",
    "PB12", "PB13", "PB14", "PB15", "PC6", "PC7", "PC8", "PC9",
    "PA8", "PA9", "PA10", "PA11", "PA12", "PA13", "VSS", "VDD",
    "PA14", "PA15", "PC10", "PC11", "PC12", "PD2", "PB3", "PB4",
    "PB5", "PB6", "PB7", "BOOT0", "PB8", "PB9", "VSS", "VDD",
]

# STM32H562xx/STM32H563xx LQFP144 — transcribed from ST datasheet DS14258
# Figure 10 "LQFP144 pinout" (source: user-provided screenshot of the
# official pin diagram, cross-checked 36 pins/side x 4 sides = 144).
# Matches nucleo_h563zi (STM32H563ZIT6) exactly — same die/package.
LQFP144_STM32H5 = [
    "PE2", "PE3", "PE4", "PE5", "PE6", "VBAT", "PC13", "PC14",
    "PC15", "PF0", "PF1", "PF2", "PF3", "PF4", "PF5", "VSS",
    "VDD", "PF6", "PF7", "PF8", "PF9", "PF10", "PH0", "PH1",
    "NRST", "PC0", "PC1", "PC2", "PC3", "VDD", "VSSA", "VREF+",
    "VDDA", "PA0", "PA1", "PA2", "PA3", "VSS", "VDD", "PA4",
    "PA5", "PA6", "PA7", "PC4", "PC5", "PB0", "PB1", "PB2",
    "PF11", "PF12", "VSS", "PF13", "PF14", "PF15", "PG0", "PG1",
    "PE7", "PE8", "PE9", "VSS", "VDD", "PE10", "PE11", "PE12",
    "PE13", "PE14", "PE15", "PB10", "PB11", "VCAP", "VSS", "VDD",
    "PB12", "PB13", "PB14", "PB15", "PD8", "PD9", "PD10", "PD11",
    "PD12", "PD13", "VSS", "VDD", "PD14", "PD15", "PG2", "PG3",
    "PG4", "PG5", "PG6", "PG7", "PG8", "VSS", "VDD", "PC6",
    "PC7", "PC8", "PC9", "PA8", "PA9", "PA10", "PA11", "PA12",
    "PA13", "VDDUSB", "VSS", "VDD", "PA14", "PA15", "PC10", "PC11",
    "PC12", "PD0", "PD1", "PD2", "PD3", "PD4", "PD5", "VSS",
    "VDDIO2", "PD7", "PD6", "PG9", "PG10", "PG11", "PG12", "PG13",
    "VSS", "PG14", "VDD", "PG15", "PB3", "PB4", "PB5", "PB6",
    "PB7", "PB8", "BOOT0", "PB9", "PE0", "VCAP", "VSS", "VDD",
]

# STM32F20x LQFP144 — transcribed from ST datasheet Figure 13 "STM32F20x
# LQFP144 pinout" (source: user-provided screenshots, including close-up
# crops of the bottom and top edges to resolve VSS/VDD pairs that were
# ambiguous in the full-diagram screenshot; cross-checked 36 pins/side x 4
# sides = 144). Matches nucleo_f207zg (STM32F207ZGT6) exactly.
LQFP144_STM32F2 = [
    "PE2", "PE3", "PE4", "PE5", "PE6", "VBAT", "PC13", "PC14",
    "PC15", "PF0", "PF1", "PF2", "PF3", "PF4", "PF5", "VSS",
    "VDD", "PF6", "PF7", "PF8", "PF9", "PF10", "PH0", "PH1",
    "NRST", "PC0", "PC1", "PC2", "PC3", "VDD", "VSSA", "VREF+",
    "VDDA", "PA0", "PA1", "PA2", "PA3", "VSS", "VDD", "PA4",
    "PA5", "PA6", "PA7", "PC4", "PC5", "PB0", "PB1", "PB2",
    "PF11", "PF12", "VSS", "VDD", "PF13", "PF14", "PF15", "PG0",
    "PG1", "PE7", "PE8", "PE9", "VSS", "VDD", "PE10", "PE11",
    "PE12", "PE13", "PE14", "PE15", "PB10", "PB11", "VCAP_1", "VDD",
    "PB12", "PB13", "PB14", "PB15", "PD8", "PD9", "PD10", "PD11",
    "PD12", "PD13", "VSS", "VDD", "PD14", "PD15", "PG2", "PG3",
    "PG4", "PG5", "PG6", "PG7", "PG8", "VSS", "VDD", "PC6",
    "PC7", "PC8", "PC9", "PA8", "PA9", "PA10", "PA11", "PA12",
    "PA13", "VCAP_2", "VSS", "VDD", "PA14", "PA15", "PC10", "PC11",
    "PC12", "PD0", "PD1", "PD2", "PD3", "PD4", "PD5", "VSS",
    "VDD", "PD6", "PD7", "PG9", "PG10", "PG11", "PG12", "PG13",
    "PG14", "VSS", "VDD", "PG15", "PB3", "PB4", "PB5", "PB6",
    "PB7", "BOOT0", "PB8", "PB9", "PE0", "PE1", "RFU", "VDD",
]

# STM32H743/753 LQFP144 — transcribed from ST datasheet DS12110 Figure 7
# "LQFP144 pinout" (source: user-provided screenshots, including close-up
# crops of the top and bottom edges to resolve VSS/VDD filler pins that were
# ambiguous in the full-diagram screenshot; cross-checked 36 pins/side x 4
# sides = 144). Matches nucleo_h743zi (STM32H743ZIT6) exactly. Note: pins 28
# and 29 are printed on the datasheet as "PC2_C"/"PC3_C" (the _C suffix
# marks the comparator-capable alternate pad on this family) — kept exactly
# as labeled on the datasheet rather than simplified to PC2/PC3.
LQFP144_STM32H7 = [
    "PE2", "PE3", "PE4", "PE5", "PE6", "VBAT", "PC13", "PC14",
    "PC15", "PF0", "PF1", "PF2", "PF3", "PF4", "PF5", "VSS",
    "VDD", "PF6", "PF7", "PF8", "PF9", "PF10", "PH0", "PH1",
    "NRST", "PC0", "PC1", "PC2_C", "PC3_C", "VDD", "VSSA", "VREF+",
    "VDDA", "PA0", "PA1", "PA2", "PA3", "VSS", "VDD", "PA4",
    "PA5", "PA6", "PA7", "PC4", "PC5", "PB0", "PB1", "PB2",
    "PF11", "PF12", "VSS", "VDD", "PF13", "PF14", "PF15", "PG0",
    "PG1", "PE7", "PE8", "PE9", "VSS", "VDD", "PE10", "PE11",
    "PE12", "PE13", "PE14", "PE15", "PB10", "PB11", "VCAP", "VDD",
    "PB12", "PB13", "PB14", "PB15", "PD8", "PD9", "PD10", "PD11",
    "PD12", "PD13", "VSS", "VDD", "PD14", "PD15", "PG2", "PG3",
    "PG4", "PG5", "PG6", "PG7", "PG8", "VSS", "VDD33USB", "PC6",
    "PC7", "PC8", "PC9", "PA8", "PA9", "PA10", "PA11", "PA12",
    "PA13", "VCAP", "VSS", "VDD", "PA14", "PA15", "PC10", "PC11",
    "PC12", "PD0", "PD1", "PD2", "PD3", "PD4", "PD5", "VSS",
    "VDD", "PD6", "PD7", "PG9", "PG10", "PG11", "PG12", "PG13",
    "PG14", "VSS", "VDD", "PG15", "PB3", "PB4", "PB5", "PB6",
    "PB7", "BOOT0", "PB8", "PB9", "PE0", "PE1", "PDR_ON", "VDD",
]

# STM32L552/L562 LQFP144 — transcribed from ST datasheet "Figure 7. LQFP144
# pinout" (source: user-provided screenshot; cross-checked 36 pins/side x 4
# sides = 144, all four sides counted correctly on first pass). Matches
# nucleo_l552ze_q (STM32L552ZET6) exactly. Note real differences from the
# other LQFP144 families here, read directly off the datasheet rather than
# assumed: separate VREF-/VREF+ pins, a shared PH3-BOOT0 pin, and
# VDDIO2/VDDUSB power domains instead of VCAP.
LQFP144_STM32L5 = [
    "PE2", "PE3", "PE4", "PE5", "PE6", "VBAT", "PC13", "PC14",
    "PC15", "PF0", "PF1", "PF2", "PF3", "PF4", "PF5", "VSS",
    "VDD", "PF6", "PF7", "PF8", "PF9", "PF10", "PH0", "PH1",
    "NRST", "PC0", "PC1", "PC2", "PC3", "VSSA", "VREF-", "VREF+",
    "VDDA", "PA0", "PA1", "PA2", "PA3", "VSS", "VDD", "PA4",
    "PA5", "PA6", "PA7", "PC4", "PC5", "PB0", "PB1", "PB2",
    "PF11", "PF12", "VSS", "VDD", "PF13", "PF14", "PF15", "PG0",
    "PG1", "PE7", "PE8", "PE9", "VSS", "VDD", "PE10", "PE11",
    "PE12", "PE13", "PE14", "PE15", "PB10", "PB11", "VSS", "VDD",
    "PB12", "PB13", "PB14", "PB15", "PD8", "PD9", "PD10", "PD11",
    "PD12", "PD13", "VSS", "VDD", "PD14", "PD15", "PG2", "PG3",
    "PG4", "PG5", "PG6", "PG7", "PG8", "VSS", "VDDIO2", "PC6",
    "PC7", "PC8", "PC9", "PA8", "PA9", "PA10", "PA11", "PA12",
    "PA13", "VDDUSB", "VSS", "VDD", "PA14", "PA15", "PC10", "PC11",
    "PC12", "PD0", "PD1", "PD2", "PD3", "PD4", "PD5", "VSS",
    "VDD", "PD6", "PD7", "PG9", "PG10", "PG11", "PG12", "PG13",
    "PG14", "VSS", "VDDIO2", "PG15", "PB3", "PB4", "PB5", "PB6",
    "PB7", "PH3-BOOT0", "PB8", "PB9", "PE0", "PE1", "VSS", "VDD",
]
# STM32U575xx LQFP144 — transcribed from ST datasheet DS13737
# Figure "LQFP144 pinout". Matches nucleo_u575zi_q (STM32U575ZIT6Q).
LQFP144_STM32U5 = [
    "PE2", "PE3", "PE4", "PE5", "PE6", "VBAT", "PC13", "PC14",
    "PC15", "PF0", "PF1", "PF2", "PF3", "PF4", "PF5", "VSS",
    "VDD", "PF6", "PF7", "PF8", "PF9", "PF10", "PH0", "PH1",
    "NRST", "PC0", "PC1", "PC2", "PC3", "VSSA", "VREF-", "VREF+",
    "VDDA", "PA0", "PA1", "PA2", "PA3", "VSS", "VDD", "PA4",
    "PA5", "PA6", "PA7", "PC4", "PC5", "PB0", "PB1", "PB2",
    "PF11", "PF12", "VSS", "VDD", "PF13", "PF14", "PF15", "PG0",
    "PG1", "PE7", "PE8", "PE9", "VSS", "VDD", "PE10", "PE11",
    "PE12", "PE13", "PE14", "PE15", "PB10", "PB11", "VSS", "VDD",
    "PB12", "PB13", "PB14", "PB15", "PD8", "PD9", "PD10", "PD11",
    "PD12", "PD13", "VSS", "VDD", "PD14", "PD15", "PG2", "PG3",
    "PG4", "PG5", "PG6", "PG7", "PG8", "VSS", "VDDIO2", "PC6",
    "PC7", "PC8", "PC9", "PA8", "PA9", "PA10", "PA11", "PA12",
    "PA13", "VDDUSB", "VSS", "VDD", "PA14", "PA15", "PC10", "PC11",
    "PC12", "PD0", "PD1", "PD2", "PD3", "PD4", "PD5", "VSS",
    "VDDIO2", "PD7", "PD6", "PG9", "PG10", "PG11", "PG12", "PG13",
    "VSS", "PG14", "VDD", "PG15", "PB3", "PB4", "PB5", "PB6",
    "PB7", "PB8", "PH3-BOOT0", "PB9", "PE0", "PE1", "VSS", "VDD",
]

# Maps a board's package (derived below) to its pin list.
PACKAGE_PINOUTS: dict[str, list[str]] = {
    "LQFP48": LQFP48_F1,
    "LQFP64": LQFP64_NUCLEO64,
    "LQFP144_STM32H5": LQFP144_STM32H5,
    "LQFP144_STM32F2": LQFP144_STM32F2,
    "LQFP144_STM32H7": LQFP144_STM32H7,
    "LQFP144_STM32L5": LQFP144_STM32L5,
    "LQFP144_STM32U5": LQFP144_STM32U5,
}
# Board id -> package. Extend this as you add real per-board verification —
# start with boards you actually have or care about most.
#
# Nucleo-144 / Discovery boards (U575ZI-Q, F746NG Discovery) are
# intentionally NOT mapped here. Their real packages are much larger than
# LQFP64 (typically LQFP144-class with Zio + Morpho headers) and a previous
# version of this table incorrectly pointed them at LQFP64_NUCLEO64,
# silently showing a 64-pin diagram for a ~144-pin board. Add them back once
# a real per-part LQFP144 table has been hand-verified against the
# datasheet — do not reuse LQFP64_NUCLEO64 for them. (H563ZI, F207ZG,
# H743ZI, and L552ZE-Q below use the datasheet's own LQFP144 figure rather
# than guessing from another package's layout.)
BOARD_PACKAGE: dict[str, str] = {
    "bluepill_f103c8": "LQFP48",
    "nucleo_f401re": "LQFP64",
    "nucleo_f411re": "LQFP64",
    "nucleo_f446re": "LQFP64",
    "nucleo_g431rb": "LQFP64",
    "nucleo_l476rg": "LQFP64",
    "nucleo_l152re": "LQFP64",
    "nucleo_f091rc": "LQFP64",
    "nucleo_f303re": "LQFP64",
    "nucleo_g071rb": "LQFP64",
    "nucleo_l053r8": "LQFP64",
    "nucleo_wb55rg": "LQFP64",
    "nucleo_wl55jc": "LQFP64",
    "nucleo_h563zi": "LQFP144_STM32H5",
    "nucleo_f207zg": "LQFP144_STM32F2",
    "nucleo_h743zi": "LQFP144_STM32H7",
    "nucleo_l552ze_q": "LQFP144_STM32L5",
    "nucleo_u575zi_q": "LQFP144_STM32U5",
}

import re

# Board id -> package, for the hand-curated seed boards this data was
# originally verified against.
BOARD_PACKAGE_BY_ID: dict[str, str] = BOARD_PACKAGE

# Verified board id -> its exact MCU part number. Kept as a static table
# here (rather than importing boards.registry) to avoid a circular import —
# registry.get() calls into this module to resolve full_pinout.
_KNOWN_VERIFIED_MCUS: dict[str, str] = {
    "bluepill_f103c8": "STM32F103C8Tx",
    "nucleo_f091rc": "STM32F091RCTx",
    "nucleo_f207zg": "STM32F207ZGTx",
    "nucleo_f303re": "STM32F303RETx",
    "nucleo_f401re": "STM32F401RETx",
    "nucleo_f411re": "STM32F411RETx",
    "nucleo_f446re": "STM32F446RETx",
    "nucleo_g071rb": "STM32G071RBTx",
    "nucleo_g431rb": "STM32G431RBTx",
    "nucleo_h563zi": "STM32H563ZITx",
    "nucleo_h743zi": "STM32H743ZITx",
    "nucleo_l053r8": "STM32L053R8Tx",
    "nucleo_l152re": "STM32L152RETx",
    "nucleo_l476rg": "STM32L476RGTx",
    "nucleo_l552ze_q": "STM32L552ZETx",
    "nucleo_u575zi_q": "STM32U575ZITx",
    "nucleo_wb55rg": "STM32WB55RGVx",
    "nucleo_wl55jc": "STM32WL55JCIx",
}


def base_part(mcu: str) -> str:
    """Strip only the trailing temperature/packing-grade character (e.g. the
    '6' in STM32F103C8T6, or the 'x' wildcard in STM32F103C8Tx). That grade
    marking is a manufacturing/binning detail — it does not change the die
    or the package, so it cannot change the pin layout. Everything before
    it (line, pin-count code, flash-size code, package letter) fully
    determines the physical pinout.
    """
    return re.sub(r"([A-Z])[0-9A-Zx]$", r"\1", mcu)


def get_full_pinout(board_id: str, mcu: str | None = None) -> list[str] | None:
    """Full physical pin list for a board, in package order.

    Resolution order:
      1. This exact board id has a hand-verified package (the original
         curated set).
      2. `mcu` (if given) matches — after stripping only the non-electrical
         temp/packing suffix — the exact same die+package as one of the
         boards in (1). Same silicon, same pins, so the data is still fully
         real, just reused instead of retyped. This is how e.g. the
         BlackPill F103C8 and genericSTM32F103C8 pick up the Blue Pill's
         verified LQFP48 table automatically.

    Returns None if neither resolves — callers should fall back to showing
    no pinout diagram rather than a wrong one.
    """
    package = BOARD_PACKAGE_BY_ID.get(board_id)
    if package is None and mcu:
        base = base_part(mcu)
        for verified_id, verified_mcu in _KNOWN_VERIFIED_MCUS.items():
            if base_part(verified_mcu) == base:
                package = BOARD_PACKAGE_BY_ID.get(verified_id)
                break
    if package is None:
        return None
    return PACKAGE_PINOUTS.get(package)