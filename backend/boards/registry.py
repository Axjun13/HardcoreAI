"""Board Registry — the one place every module asks for board metadata.

Resolution order for get():
  1. Curated seed (_SEED) — hand-verified, always wins on conflict.
  2. Imported cache (populated by refresh(), backed by boards_cache.json).
  3. None — caller decides the fallback (usually registry.default()).
"""

from __future__ import annotations

import json
from pathlib import Path

from boards.device import Device
from boards.family_map import derive_family_info
from boards.pio_importer import import_boards

CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "boards_cache.json"

# Curated, hand-verified entries. These always take priority over imported
# data — if PlatformIO's metadata for a board is ever wrong, override it here
# rather than patching the importer.
_SEED: dict[str, Device] = {
    "nucleo_g431rb": Device(
        id="nucleo_g431rb", label="STM32G431RB (Nucleo-64)", vendor="st",
        mcu="STM32G431RBTx", family="STM32G4", core="cortex-m4",
        flash_bytes=131072, ram_bytes=32768, f_cpu_hz=170_000_000,
        hal_header="stm32g4xx_hal.h",
        openocd_target="target/stm32g4x.cfg", openocd_interface="interface/stlink.cfg",
    ),
    "nucleo_wl55jc": Device(
        id="nucleo_wl55jc", label="STM32WL55JC (Nucleo-64)", vendor="st",
        mcu="STM32WL55JCIx", family="STM32WL", core="cortex-m4",
        flash_bytes=262144, ram_bytes=65536, f_cpu_hz=4_000_000,
        hal_header="stm32wlxx_hal.h",
        openocd_target="target/stm32wlx.cfg", openocd_interface="interface/stlink.cfg",
    ),
    "nucleo_f091rc": Device(
        id="nucleo_f091rc", label="STM32F091RC (Nucleo-64)", vendor="st",
        mcu="STM32F091RCTx", family="STM32F0", core="cortex-m0",
        flash_bytes=262144, ram_bytes=32768, f_cpu_hz=48_000_000,
        hal_header="stm32f0xx_hal.h",
        openocd_target="target/stm32f0x.cfg", openocd_interface="interface/stlink.cfg",
    ),
    "nucleo_f303re": Device(
        id="nucleo_f303re", label="STM32F303RE (Nucleo-64)", vendor="st",
        mcu="STM32F303RETx", family="STM32F3", core="cortex-m4",
        flash_bytes=524288, ram_bytes=65536, f_cpu_hz=72_000_000,
        hal_header="stm32f3xx_hal.h",
        openocd_target="target/stm32f3x.cfg", openocd_interface="interface/stlink.cfg",
    ),
    "nucleo_f207zg": Device(
        id="nucleo_f207zg", label="STM32F207ZG (Nucleo-144)", vendor="st",
        mcu="STM32F207ZGTx", family="STM32F2", core="cortex-m3",
        flash_bytes=1048576, ram_bytes=131072, f_cpu_hz=120_000_000,
        hal_header="stm32f2xx_hal.h",
        openocd_target="target/stm32f2x.cfg", openocd_interface="interface/stlink.cfg",
    ),
    "nucleo_h563zi": Device(
        id="nucleo_h563zi", label="STM32H563ZI (Nucleo-144)", vendor="st",
        mcu="STM32H563ZITx", family="STM32H5", core="cortex-m33",
        flash_bytes=2097152, ram_bytes=655360, f_cpu_hz=250_000_000,
        hal_header="stm32h5xx_hal.h",
        openocd_target="target/stm32h5x.cfg", openocd_interface="interface/stlink.cfg",
    ),
    "nucleo_g071rb": Device(
        id="nucleo_g071rb", label="STM32G071RB (Nucleo-64)", vendor="st",
        mcu="STM32G071RBTx", family="STM32G0", core="cortex-m0plus",
        flash_bytes=131072, ram_bytes=36864, f_cpu_hz=64_000_000,
        hal_header="stm32g0xx_hal.h",
        openocd_target="target/stm32g0x.cfg", openocd_interface="interface/stlink.cfg",
    ),
    "nucleo_h743zi": Device(
        id="nucleo_h743zi", label="STM32H743ZI (Nucleo-144)", vendor="st",
        mcu="STM32H743ZITx", family="STM32H7", core="cortex-m7",
        flash_bytes=2097152, ram_bytes=1048576, f_cpu_hz=400_000_000,
        hal_header="stm32h7xx_hal.h",
        openocd_target="target/stm32h7x.cfg", openocd_interface="interface/stlink.cfg",
    ),
    "nucleo_l053r8": Device(
        id="nucleo_l053r8", label="STM32L053R8 (Nucleo-64)", vendor="st",
        mcu="STM32L053R8Tx", family="STM32L0", core="cortex-m0plus",
        flash_bytes=65536, ram_bytes=8192, f_cpu_hz=32_000_000,
        hal_header="stm32l0xx_hal.h",
        openocd_target="target/stm32l0.cfg", openocd_interface="interface/stlink.cfg",
    ),
    "nucleo_l152re": Device(
        id="nucleo_l152re", label="STM32L152RE (Nucleo-64)", vendor="st",
        mcu="STM32L152RETx", family="STM32L1", core="cortex-m3",
        flash_bytes=524288, ram_bytes=81920, f_cpu_hz=32_000_000,
        hal_header="stm32l1xx_hal.h",
        openocd_target="target/stm32l1.cfg", openocd_interface="interface/stlink.cfg",
    ),
    "nucleo_l552ze_q": Device(
        id="nucleo_l552ze_q", label="STM32L552ZE (Nucleo-144)", vendor="st",
        mcu="STM32L552ZETx", family="STM32L5", core="cortex-m33",
        flash_bytes=524288, ram_bytes=262144, f_cpu_hz=110_000_000,
        hal_header="stm32l5xx_hal.h",
        openocd_target="target/stm32l5x.cfg", openocd_interface="interface/stlink.cfg",
    ),
    "nucleo_wb55rg": Device(
        id="nucleo_wb55rg", label="STM32WB55RG (Nucleo-64)", vendor="st",
        mcu="STM32WB55RGVx", family="STM32WB", core="cortex-m4",
        flash_bytes=1048576, ram_bytes=196608, f_cpu_hz=64_000_000,
        hal_header="stm32wbxx_hal.h",
        openocd_target="target/stm32wbx.cfg", openocd_interface="interface/stlink.cfg",
    ),
    "nucleo_u575zi_q": Device(
        id="nucleo_u575zi_q", label="STM32U575ZI (Nucleo-144)", vendor="st",
        mcu="STM32U575ZITx", family="STM32U5", core="cortex-m33",
        flash_bytes=2097152, ram_bytes=786432, f_cpu_hz=160_000_000,
        hal_header="stm32u5xx_hal.h",
        openocd_target="target/stm32u5x.cfg", openocd_interface="interface/stlink.cfg",
    ),
    "bluepill_f103c8": Device(
        id="bluepill_f103c8", label="STM32F103 (Blue Pill)", vendor="generic",
        mcu="STM32F103C8Tx", family="STM32F1", core="cortex-m3",
        flash_bytes=65536, ram_bytes=20480, f_cpu_hz=72_000_000,
        hal_header="stm32f1xx_hal.h",
        openocd_target="target/stm32f1x.cfg", openocd_interface="interface/stlink.cfg",
    ),
    "nucleo_f401re": Device(
        id="nucleo_f401re", label="STM32F401RE (Nucleo-64)", vendor="st",
        mcu="STM32F401RETx", family="STM32F4", core="cortex-m4",
        flash_bytes=524288, ram_bytes=98304, f_cpu_hz=84_000_000,
        hal_header="stm32f4xx_hal.h",
        openocd_target="target/stm32f4x.cfg", openocd_interface="interface/stlink.cfg",
    ),
    "nucleo_f411re": Device(
        id="nucleo_f411re", label="STM32F411RE (Nucleo-64)", vendor="st",
        mcu="STM32F411RETx", family="STM32F4", core="cortex-m4",
        flash_bytes=524288, ram_bytes=131072, f_cpu_hz=100_000_000,
        hal_header="stm32f4xx_hal.h",
        openocd_target="target/stm32f4x.cfg", openocd_interface="interface/stlink.cfg",
    ),
    "nucleo_f446re": Device(
        id="nucleo_f446re", label="STM32F446RE (Nucleo-64)", vendor="st",
        mcu="STM32F446RETx", family="STM32F4", core="cortex-m4",
        flash_bytes=524288, ram_bytes=131072, f_cpu_hz=180_000_000,
        hal_header="stm32f4xx_hal.h",
        openocd_target="target/stm32f4x.cfg", openocd_interface="interface/stlink.cfg",
    ),
    "nucleo_l476rg": Device(
        id="nucleo_l476rg", label="STM32L476RG (Nucleo-64)", vendor="st",
        mcu="STM32L476RGTx", family="STM32L4", core="cortex-m4",
        flash_bytes=1048576, ram_bytes=131072, f_cpu_hz=80_000_000,
        hal_header="stm32l4xx_hal.h",
        openocd_target="target/stm32l4x.cfg", openocd_interface="interface/stlink.cfg",
    ),
    "disco_f746ng": Device(
        id="disco_f746ng", label="STM32F746NG (Discovery)", vendor="st",
        mcu="STM32F746NGHx", family="STM32F7", core="cortex-m7",
        flash_bytes=1048576, ram_bytes=327680, f_cpu_hz=216_000_000,
        hal_header="stm32f7xx_hal.h",
        openocd_target="target/stm32f7x.cfg", openocd_interface="interface/stlink.cfg",
    ),
}


class BoardRegistry:
    def __init__(self) -> None:
        self._imported: dict[str, Device] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        if not CACHE_PATH.exists():
            return
        try:
            raw = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            self._imported = {
                bid: self._reclassify(Device(**data)) for bid, data in raw.items()
            }
        except Exception as exc:
            print(f"[registry] cache load failed, ignoring: {exc}")
            self._imported = {}

    @staticmethod
    def _reclassify(device: Device) -> Device:
        """Re-derive family/core/hal_header/openocd_target from the device's
        mcu string using the *current* family_map, instead of trusting
        whatever was on disk. The cache is written once by refresh() and can
        go stale relative to family_map.py (e.g. a family added after the
        cache was last generated) — this makes the cache self-heal on every
        load rather than silently carrying "unknown"/wrong classifications
        until someone remembers to hit /api/boards/refresh."""
        if device.family != "unknown" and device.family != "":
            # Already classified — still worth reconciling core/hal_header/
            # openocd_target in case family_map.py's mapping for this family
            # changed, but never downgrade a known family to "unknown".
            info = derive_family_info(device.mcu)
            if info["family"] != device.family:
                # family_map has no entry matching this mcu (fell through to
                # the generic default) — keep the existing classification
                # rather than overwriting good data with a guess.
                return device
            return device.model_copy(update={
                "core": info["core"],
                "hal_header": info["hal_header"],
                "openocd_target": info["openocd_target"],
            })

        info = derive_family_info(device.mcu)
        if info["family"] == "unknown":
            return device  # still unclassifiable — leave as-is
        return device.model_copy(update={
            "family": info["family"],
            "core": info["core"],
            "hal_header": info["hal_header"],
            "openocd_target": info["openocd_target"],
        })

    def _write_cache(self) -> None:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        raw = {bid: device.model_dump() for bid, device in self._imported.items()}
        CACHE_PATH.write_text(json.dumps(raw, indent=2), encoding="utf-8")

    def list(self) -> list[Device]:
        merged = {**self._imported, **_SEED}  # seed wins on id collision
        return sorted(merged.values(), key=lambda d: d.id)

    def default(self) -> Device:
        return _SEED["bluepill_f103c8"]

    def refresh(self, query: str = "STM32") -> int:
        """Re-import from PlatformIO, overwrite the cache. Never raises —
        returns 0 and leaves the existing cache untouched on failure."""
        imported = import_boards(query)
        if not imported:
            return 0
        self._imported = {d.id: d for d in imported}
        self._write_cache()
        return len(self._imported)
    
    def get(self, board_id: str) -> Device | None:
        device = _SEED.get(board_id) or self._imported.get(board_id)
        if device and device.full_pinout is None:
            from boards.pinout import get_full_pinout
            pinout = get_full_pinout(board_id, mcu=device.mcu)
            if pinout:
                device = device.model_copy(update={"full_pinout": pinout})
        return device


registry = BoardRegistry()