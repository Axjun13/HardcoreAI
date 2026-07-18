"""Deterministic target-board selection from an approved research plan.

The board registry may contain hundreds of PlatformIO targets.  This module
turns plan/component requirements into a ranked, auditable decision without
letting an LLM invent a board id.  Explicit controller cards and exact board
mentions win; otherwise hardware capabilities, framework preference, GPIO
capacity, metadata quality, and the current target determine the ranking.
"""

from __future__ import annotations

import re
from typing import Any

from boards.device import Device, uses_arduino_framework, uses_espidf_framework
from boards.registry import registry
from services.research import selected_target_board_id


_CANONICAL_PRIORITY = {
    "esp32dev": 35,
    "esp32-s3-devkitc-1": 32,
    "esp32-c3-devkitm-1": 30,
    "uno": 30,
    "megaatmega2560": 28,
    "mkrwifi1010": 26,
    "zeroUSB": 24,
    "bluepill_f103c8": 25,
    "nucleo_f446re": 24,
}


def _normal(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").casefold())


def _component_pins(component: dict[str, Any]) -> list[dict[str, Any]]:
    pins = component.get("pins") or []
    if isinstance(pins, dict):
        return [dict(meta, name=name) for name, meta in pins.items()]
    return [item for item in pins if isinstance(item, dict)]


def infer_board_requirements(plan: str, components: list[dict[str, Any]]) -> dict[str, Any]:
    text = " ".join([
        plan or "",
        *(
            " ".join([
                str(item.get("name") or ""),
                str(item.get("description") or ""),
                " ".join(str(value) for value in item.get("protocols") or []),
            ])
            for item in components or []
        ),
    ]).casefold()
    connectivity = []
    checks = {
        "wifi": ("wifi", "wi-fi", "wireless lan"),
        "bluetooth": ("bluetooth", " ble ", "ble beacon"),
        "can": (" can bus", "canbus", "can-bus"),
        "usb": (" usb", "usb ", "hid device", "webusb"),
        "ethernet": ("ethernet",),
    }
    padded = f" {text} "
    for capability, needles in checks.items():
        if any(needle in padded for needle in needles):
            connectivity.append(capability)

    protocols: set[str] = set()
    gpio_count = 0
    needs_analog = False
    needs_pwm = False
    shared_signals: set[str] = set()
    for component in components or []:
        protocols.update(str(value).upper() for value in component.get("protocols") or [])
        for pin in _component_pins(component):
            label = f"{pin.get('name', '')} {pin.get('label', '')} {pin.get('role', '')}".upper()
            if any(token in label for token in ("VCC", "VIN", "VDD", "3V3", "5V", "GND", "VSS")):
                continue
            if "SDA" in label:
                shared_signals.add("I2C_SDA")
            elif "SCL" in label:
                shared_signals.add("I2C_SCL")
            elif "MOSI" in label:
                shared_signals.add("SPI_MOSI")
            elif "MISO" in label:
                shared_signals.add("SPI_MISO")
            elif "SCK" in label or "SPI CLK" in label:
                shared_signals.add("SPI_SCK")
            else:
                gpio_count += 1
            needs_analog = needs_analog or any(token in label for token in ("ANALOG", "ADC", " AOUT", " AO"))
            needs_pwm = needs_pwm or "PWM" in label
    gpio_count += len(shared_signals)

    framework = next(
        (name for name in ("espidf", "arduino", "stm32cube") if name in _normal(text)),
        None,
    )
    return {
        "connectivity": connectivity,
        "protocols": sorted(protocols),
        "minimum_gpio": gpio_count,
        "needs_analog": needs_analog,
        "needs_pwm": needs_pwm,
        "framework": framework,
    }


def _pin_capacity(device: Device) -> int | None:
    if device.pin_metadata:
        return sum(
            1 for pin in device.pin_metadata
            if str(pin.get("type") or "").casefold() not in {"power", "reset", "boot"}
        )
    header = device.arduino_pinout or {}
    explicit = header.get("digital")
    if isinstance(explicit, list):
        return len(explicit)
    labels = [*header.get("left", []), *header.get("right", [])]
    if labels:
        return sum(1 for label in labels if re.search(r"(?:GPIO|D|A)\d+", str(label), re.I))
    if device.full_pinout:
        return sum(1 for pin in device.full_pinout if re.fullmatch(r"P[A-Z]\d+", str(pin)))
    return None


def _capability(device: Device, name: str) -> bool:
    text = f"{device.id} {device.label} {device.mcu} {device.family}".casefold()
    family = device.family.casefold()
    if name == "wifi":
        return "esp32" in family or "esp8266" in family or "wifi" in text or "wi-fi" in text
    if name == "bluetooth":
        return (
            ("esp32" in family and "esp8266" not in family)
            or any(token in text for token in ("bluetooth", " ble", "nano33ble", "stm32wb", "stm32wba"))
        )
    if name == "can":
        signal_text = " ".join(
            str(signal.get("name") or "")
            for pin in device.pin_metadata or []
            for signal in pin.get("signals") or []
        ).casefold()
        return "can" in signal_text or "esp32" in family or device.family in {"STM32F4", "STM32F7", "STM32G4", "STM32H7"}
    if name == "usb":
        return device.arch == "arm-samd" or any(token in text for token in ("usb", "samd", "esp32s2", "esp32s3", "esp32c3"))
    if name == "ethernet":
        return "ethernet" in text or "eth" in device.id.casefold()
    return False


def _framework_name(device: Device) -> str:
    if uses_arduino_framework(device):
        return "arduino"
    if uses_espidf_framework(device):
        return "espidf"
    return "stm32cube" if device.arch == "arm-stm32" else (device.frameworks[0] if device.frameworks else "unknown")


def _rank_device(
    device: Device,
    *,
    text: str,
    requirements: dict[str, Any],
    current_board_id: str | None,
) -> tuple[int, list[str], list[str]]:
    score = _CANONICAL_PRIORITY.get(device.id, 0)
    reasons: list[str] = []
    warnings: list[str] = []
    compact = _normal(text)
    identities = [device.id, device.label, device.mcu, device.family]
    exact = next((value for value in identities if len(_normal(value)) >= 4 and _normal(value) in compact), None)
    if exact:
        score += 10_000
        reasons.append(f"The approved plan explicitly names {exact}.")

    for capability in requirements["connectivity"]:
        if _capability(device, capability):
            score += 450
            reasons.append(f"Provides the required {capability} capability.")
        else:
            score -= 2_000
            warnings.append(f"No {capability} capability is recorded for this board.")

    wanted_framework = requirements.get("framework")
    actual_framework = _framework_name(device)
    if wanted_framework:
        if wanted_framework == actual_framework:
            score += 350
            reasons.append(f"Matches the requested {actual_framework} framework.")
        else:
            score -= 1_000
            warnings.append(f"Uses {actual_framework}, not requested {wanted_framework}.")

    capacity = _pin_capacity(device)
    minimum_gpio = int(requirements.get("minimum_gpio") or 0)
    if capacity is not None:
        if capacity >= minimum_gpio:
            score += min(180, 40 + capacity)
            reasons.append(f"Exposes approximately {capacity} usable GPIOs for {minimum_gpio} required signals.")
        else:
            score -= 1_500 + (minimum_gpio - capacity) * 20
            warnings.append(f"Only {capacity} GPIOs are represented for {minimum_gpio} required signals.")
    elif minimum_gpio:
        score -= 80
        warnings.append("The imported registry record has no usable-pin count.")

    if device.pin_metadata:
        score += 140
        reasons.append("Includes signal-level pin metadata for assignment checks.")
    elif (device.arduino_pinout or {}).get("status") == "verified":
        score += 100
        reasons.append("Includes a verified board-header pin map.")
    elif device.arduino_pinout:
        score += 30
        warnings.append("Only a generic Arduino API pin namespace is available; physical wiring needs variant documentation.")
    elif device.full_pinout:
        score += 25
        warnings.append("Package pins are known, but peripheral alternate functions are incomplete.")

    if current_board_id and device.id == current_board_id:
        score += 90
        reasons.append("Keeps the current project target when it satisfies the plan.")
    if device.arch == "arm-stm32":
        try:
            from api.routers.hal_codegen import is_supported_family
            codegen_supported = is_supported_family(device.family)
        except Exception:
            codegen_supported = False
        if codegen_supported:
            score += 80
            reasons.append("The selected STM32 family has built-in HAL scaffolding support.")
        else:
            score -= 1_200
            warnings.append("This STM32 family has no built-in HAL scaffolding template.")
    elif uses_arduino_framework(device) or uses_espidf_framework(device):
        score += 80
        reasons.append(f"The {actual_framework} scaffold generator supports this target.")
    else:
        score -= 1_200
        warnings.append("No framework-specific firmware generator supports this target.")
    if not device.frameworks:
        score -= 500
        warnings.append("No build framework is registered.")
    return score, reasons, warnings


def select_board_for_plan(
    *,
    plan: str,
    components: list[dict[str, Any]],
    current_board_id: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Rank the entire registry and return a validated target decision."""
    requirements = infer_board_requirements(plan, components)
    explicit_component_board = selected_target_board_id(components)
    text = plan or ""
    ranked = []
    for device in registry.list():
        score, reasons, warnings = _rank_device(
            device,
            text=text,
            requirements=requirements,
            current_board_id=current_board_id,
        )
        if explicit_component_board == device.id:
            score += 20_000
            reasons.insert(0, "This board was explicitly selected as the controller component.")
        ranked.append({
            "board": device.model_dump(),
            "score": score,
            "reasons": reasons,
            "warnings": warnings,
        })
    ranked.sort(key=lambda item: (-item["score"], item["board"]["id"]))
    candidates = ranked[:max(1, limit)]
    selected = candidates[0] if candidates else None
    confidence = "low"
    if selected:
        margin = selected["score"] - (candidates[1]["score"] if len(candidates) > 1 else 0)
        confidence = "high" if explicit_component_board or selected["score"] >= 9_000 else "medium" if margin >= 150 else "low"
    return {
        "selected_board_id": selected["board"]["id"] if selected else current_board_id,
        "selected": selected,
        "candidates": candidates,
        "requirements": requirements,
        "confidence": confidence,
        "registry_size": len(ranked),
    }
