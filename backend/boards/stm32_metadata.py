"""STM32 metadata cache built from ST's STM32_open_pin_data XML files.

The source repository is official ST data:
https://github.com/STMicroelectronics/STM32_open_pin_data

HardcoreAI keeps a compact JSON cache so the app can run offline after import.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from xml.etree import ElementTree as ET

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
DEFAULT_SOURCE_DIR = BACKEND_DIR / "vendor" / "STM32_open_pin_data"
METADATA_PATH = DATA_DIR / "stm32_mcu_metadata.json"
SOURCE_URL = "https://github.com/STMicroelectronics/STM32_open_pin_data.git"


def ensure_source(source_dir: Path | None = None) -> Path:
    """Return a local STM32_open_pin_data checkout, cloning if needed."""
    source = Path(os.environ.get("STM32_OPEN_PIN_DATA_DIR") or source_dir or DEFAULT_SOURCE_DIR)
    if (source / "mcu").is_dir():
        return source

    source.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--depth", "1", SOURCE_URL, str(source)],
        check=True,
        capture_output=True,
        text=True,
        timeout=300,
    )
    return source


def build_metadata_cache(source_dir: str | Path | None = None) -> dict:
    source = ensure_source(Path(source_dir) if source_dir else None)
    mcu_dir = source / "mcu"
    items: list[dict] = []

    for path in sorted(mcu_dir.glob("*.xml")):
        try:
            items.append(_parse_mcu_xml(path, source))
        except Exception as exc:
            print(f"[stm32_metadata] skipped {path.name}: {exc}")

    payload = {
        "source": str(source),
        "source_url": SOURCE_URL,
        "count": len(items),
        "mcus": items,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    METADATA_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"imported": len(items), "path": str(METADATA_PATH), "source": str(source)}


def metadata_status() -> dict:
    if not METADATA_PATH.exists():
        return {"available": False, "count": 0, "path": str(METADATA_PATH)}
    try:
        payload = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"available": False, "count": 0, "path": str(METADATA_PATH)}
    return {
        "available": True,
        "count": payload.get("count", len(payload.get("mcus", []))),
        "path": str(METADATA_PATH),
        "source": payload.get("source"),
        "source_url": payload.get("source_url", SOURCE_URL),
    }


def get_mcu_metadata(mcu: str) -> dict | None:
    payload = _load_cache()
    if not payload:
        return None

    target = _normalize(mcu)
    best: dict | None = None
    for item in payload.get("mcus", []):
        ref = _normalize(item.get("ref_name", ""))
        if target == ref:
            return item
        if _ref_pattern_matches(ref, target):
            best = item
    return best


def validate_peripherals(mcu: str, peripheral_ids: list[str]) -> dict:
    meta = get_mcu_metadata(mcu)
    if not meta:
        return {"mcu": mcu, "metadata_available": False, "available": [], "missing": peripheral_ids}

    available_names = {p["instance"].upper() for p in meta.get("peripherals", [])}
    normalized = [_peripheral_instance(pid) for pid in peripheral_ids]
    missing = [
        original for original, instance in zip(peripheral_ids, normalized)
        if instance not in available_names and instance not in {"GPIO", "RCC", "NVIC", "DMA", "SYS"}
    ]
    return {
        "mcu": mcu,
        "metadata_available": True,
        "available": sorted(available_names),
        "missing": missing,
    }


def _parse_mcu_xml(path: Path, source: Path) -> dict:
    tree = ET.parse(path)
    root = tree.getroot()
    gpio_version = None
    peripherals = []
    for ip in _children(root, "IP"):
        instance = ip.attrib.get("InstanceName") or ip.attrib.get("Name")
        if not instance:
            continue
        peripherals.append({
            "instance": instance,
            "type": ip.attrib.get("Name", ""),
            "version": ip.attrib.get("Version", ""),
            "config_file": ip.attrib.get("ConfigFile", ""),
        })
        if ip.attrib.get("Name") == "GPIO":
            gpio_version = ip.attrib.get("Version")

    af_by_pin = _parse_gpio_af(source, gpio_version)
    pins = []
    for pin in _children(root, "Pin"):
        name = pin.attrib.get("Name", "")
        clean_name = _clean_pin_name(name)
        signals = []
        for signal in _children(pin, "Signal"):
            signal_name = signal.attrib.get("Name")
            if not signal_name:
                continue
            signals.append({
                "name": signal_name,
                "af": af_by_pin.get(_clean_pin_name(name), {}).get(signal_name),
                "io_modes": signal.attrib.get("IOModes", ""),
            })
        pins.append({
            "name": clean_name,
            "raw_name": name,
            "position": _int_or_none(pin.attrib.get("Position")),
            "type": pin.attrib.get("Type", ""),
            "signals": signals,
        })

    pins.sort(key=lambda p: p["position"] or 0)
    return {
        "ref_name": root.attrib.get("RefName", path.stem),
        "family": root.attrib.get("Family", ""),
        "line": root.attrib.get("Line", ""),
        "package": root.attrib.get("Package", ""),
        "clock_tree": root.attrib.get("ClockTree", ""),
        "core": _text(root, "Core"),
        "max_frequency_mhz": _int_or_none(_text(root, "Frequency")),
        "flash_kb": [_int_or_none(node.text) for node in _children(root, "Flash") if node.text],
        "ram_kb": [_int_or_none(node.text) for node in _children(root, "Ram") if node.text],
        "peripherals": peripherals,
        "pins": pins,
        "pin_count": len(pins),
    }


def _parse_gpio_af(source: Path, gpio_version: str | None) -> dict[str, dict[str, str]]:
    if not gpio_version:
        return {}
    path = source / "mcu" / "IP" / f"GPIO-{gpio_version}_Modes.xml"
    if not path.exists():
        return {}

    root = ET.parse(path).getroot()
    result: dict[str, dict[str, str]] = {}
    for gpio_pin in _children(root, "GPIO_Pin"):
        pin_name = _clean_pin_name(gpio_pin.attrib.get("Name", ""))
        signal_map: dict[str, str] = {}
        for pin_signal in _children(gpio_pin, "PinSignal"):
            signal_name = pin_signal.attrib.get("Name")
            if not signal_name:
                continue
            af = None
            for specific in _children(pin_signal, "SpecificParameter"):
                if specific.attrib.get("Name") != "GPIO_AF":
                    continue
                values = _children(specific, "PossibleValue")
                if values and values[0].text:
                    af = values[0].text.strip()
            if af:
                signal_map[signal_name] = af
        if signal_map:
            result[pin_name] = signal_map
    return result


def _load_cache() -> dict | None:
    if not METADATA_PATH.exists():
        return None
    try:
        return json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _children(node: ET.Element, tag: str) -> list[ET.Element]:
    return [child for child in list(node) if _local_name(child.tag) == tag]


def _text(root: ET.Element, tag: str) -> str:
    for child in list(root):
        if _local_name(child.tag) == tag:
            return (child.text or "").strip()
    return ""


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _clean_pin_name(name: str) -> str:
    return re.split(r"\s+-\s+|-", name.strip(), maxsplit=1)[0].strip()


def _normalize(value: str) -> str:
    return "".join(ch for ch in value.upper() if ch.isalnum() or ch in "() -").replace(" ", "")


def _ref_pattern_matches(ref: str, target: str) -> bool:
    pattern = ""
    i = 0
    while i < len(ref):
        if ref[i] == "(":
            end = ref.find(")", i)
            group = ref[i + 1:end] if end != -1 else ""
            if len(group) == 3 and group[1] == "-":
                pattern += _range_chars(group[0], group[2])
                i = end + 1
                continue
        ch = ref[i]
        pattern += "[A-Z0-9X]" if ch == "X" else re.escape(ch)
        i += 1
    return re.fullmatch(pattern, target) is not None


def _range_chars(start: str, end: str) -> str:
    if start.isdigit() and end.isdigit():
        return "[" + "".join(str(i) for i in range(int(start), int(end) + 1)) + "]"
    if start.isalpha() and end.isalpha():
        return "[" + "".join(chr(i) for i in range(ord(start), ord(end) + 1)) + "]"
    return f"[{start}{end}]"


def _int_or_none(value: str | None) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _peripheral_instance(pid: str) -> str:
    value = pid.upper().replace("-", "_")
    aliases = {
        "UART1": "USART1",
        "UART2": "USART2",
        "UART3": "USART3",
        "GPIO": "GPIO",
        "RCC": "RCC",
        "NVIC": "NVIC",
    }
    return aliases.get(value, value)
