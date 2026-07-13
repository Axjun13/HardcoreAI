"""STM32 part-number helpers.

This module decodes only stable, public part-number structure. It does not
replace verified package pinout tables; it lets the IDE say "this is a
64-pin part" without inventing the physical pin names/order.
"""

from __future__ import annotations

import re


PIN_COUNT_BY_CODE: dict[str, int] = {
    "A": 169,
    "B": 208,
    "C": 48,
    "F": 20,
    "G": 28,
    "H": 40,
    "I": 176,
    "J": 72,  # Some wafer-level parts use 8; 72 is the common STM32 board case.
    "K": 32,
    "M": 81,
    "N": 216,
    "Q": 132,
    "R": 64,
    "T": 36,
    "U": 63,
    "V": 100,
    "Z": 144,
}


def normalize_part(mcu: str) -> str:
    return "".join(ch for ch in mcu.upper() if ch.isalnum())


def strip_temperature_suffix(mcu: str) -> str:
    part = normalize_part(mcu)
    return re.sub(r"([A-Z])[0-9A-ZX]$", r"\1", part)


def derive_package_pin_count(mcu: str) -> int | None:
    part = strip_temperature_suffix(mcu)
    if not part.startswith("STM32") or len(part) < 10:
        return None

    # Most STM32 orderable part numbers end in:
    #   <pin-count-code><flash-size-code><package-code><temperature/grade>
    # PlatformIO often stores the last grade as x, e.g. STM32F401RETx.
    package_count_code = part[-3]
    return PIN_COUNT_BY_CODE.get(package_count_code)
