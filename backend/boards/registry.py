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
from boards.catalog import load_catalog
from boards.family_map import derive_family_info
from boards.pio_importer import import_arduino_framework_boards, import_boards
from boards.stm32_part import derive_package_pin_count

CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "boards_cache.json"
CUSTOM_PATH = Path(__file__).resolve().parent.parent / "data" / "boards_custom.json"

# Curated, hand-verified entries. These always take priority over imported
# data — if PlatformIO's metadata for a board is ever wrong, override it here
# rather than patching the importer.
_SEED: dict[str, Device] = {
    # --- Arduino / AVR ---
    "uno": Device(
        id="uno", label="Arduino Uno (ATmega328P)", vendor="arduino",
        mcu="ATMEGA328P", family="AVR-Mega", core="avr", arch="avr",
        flash_bytes=32256, ram_bytes=2048, f_cpu_hz=16_000_000,
        avrdude_mcu="atmega328p", avrdude_programmer="arduino", upload_speed=115200,
        upload_protocol="arduino", debug_tool="avrdude", supports_live_debug=False,
        frameworks=["arduino"],
    ),
    "nanoatmega328": Device(
        id="nanoatmega328", label="Arduino Nano (ATmega328P, old bootloader)", vendor="arduino",
        mcu="ATMEGA328P", family="AVR-Mega", core="avr", arch="avr",
        flash_bytes=30720, ram_bytes=2048, f_cpu_hz=16_000_000,
        avrdude_mcu="atmega328p", avrdude_programmer="arduino", upload_speed=57600,
        upload_protocol="arduino", debug_tool="avrdude", supports_live_debug=False,
        frameworks=["arduino"],
    ),
    "megaatmega2560": Device(
        id="megaatmega2560", label="Arduino Mega 2560", vendor="arduino",
        mcu="ATMEGA2560", family="AVR-Mega", core="avr", arch="avr",
        flash_bytes=253952, ram_bytes=8192, f_cpu_hz=16_000_000,
        avrdude_mcu="atmega2560", avrdude_programmer="wiring", upload_speed=115200,
        upload_protocol="wiring", debug_tool="avrdude", supports_live_debug=False,
        frameworks=["arduino"],
    ),
    "leonardo": Device(
        id="leonardo", label="Arduino Leonardo (ATmega32U4)", vendor="arduino",
        mcu="ATMEGA32U4", family="AVR-Mega", core="avr", arch="avr",
        flash_bytes=28672, ram_bytes=2560, f_cpu_hz=16_000_000,
        avrdude_mcu="atmega32u4", avrdude_programmer="avr109", upload_speed=57600,
        upload_protocol="avr109", debug_tool="avrdude", supports_live_debug=False,
        frameworks=["arduino"],
    ),
    "micro": Device(
        id="micro", label="Arduino Micro (ATmega32U4)", vendor="arduino",
        mcu="ATMEGA32U4", family="AVR-Mega", core="avr", arch="avr",
        flash_bytes=28672, ram_bytes=2560, f_cpu_hz=16_000_000,
        avrdude_mcu="atmega32u4", avrdude_programmer="avr109", upload_speed=57600,
        upload_protocol="avr109", debug_tool="avrdude", supports_live_debug=False,
        frameworks=["arduino"],
    ),

    # --- ESP32 / ESP8266 ---
    "esp32dev": Device(
        id="esp32dev", label="ESP32 Dev Module", vendor="espressif",
        mcu="esp32", family="ESP32", core="xtensa-lx6", arch="xtensa",
        flash_bytes=4 * 1024 * 1024, ram_bytes=320 * 1024, f_cpu_hz=240_000_000,
        upload_speed=921600, flash_mode="dio", flash_freq="40m",
        upload_protocol="esptool", debug_tool="esptool", supports_live_debug=False,
        frameworks=["arduino"],
    ),
    "esp32-s3-devkitc-1": Device(
        id="esp32-s3-devkitc-1", label="ESP32-S3-DevKitC-1", vendor="espressif",
        mcu="esp32s3", family="ESP32", core="xtensa-lx7", arch="xtensa",
        flash_bytes=8 * 1024 * 1024, ram_bytes=320 * 1024, f_cpu_hz=240_000_000,
        upload_speed=921600, flash_mode="dio", flash_freq="80m",
        upload_protocol="esptool", debug_tool="esptool", supports_live_debug=False,
        frameworks=["arduino"],
    ),
    "esp32-c3-devkitm-1": Device(
        id="esp32-c3-devkitm-1", label="ESP32-C3-DevKitM-1", vendor="espressif",
        mcu="esp32c3", family="ESP32", core="riscv32", arch="xtensa",
        flash_bytes=4 * 1024 * 1024, ram_bytes=400 * 1024, f_cpu_hz=160_000_000,
        upload_speed=921600, flash_mode="dio", flash_freq="80m",
        upload_protocol="esptool", debug_tool="esptool", supports_live_debug=False,
        frameworks=["arduino"],
    ),
    "nodemcuv2": Device(
        id="nodemcuv2", label="NodeMCU 1.0 (ESP8266, 4M)", vendor="espressif",
        mcu="esp8266", family="ESP8266", core="xtensa-lx106", arch="xtensa",
        flash_bytes=4 * 1024 * 1024, ram_bytes=80 * 1024, f_cpu_hz=80_000_000,
        upload_speed=115200, flash_mode="dio", flash_freq="40m",
        upload_protocol="esptool", debug_tool="esptool", supports_live_debug=False,
        frameworks=["arduino"],
    ),
    "d1_mini": Device(
        id="d1_mini", label="WEMOS D1 Mini (ESP8266)", vendor="espressif",
        mcu="esp8266", family="ESP8266", core="xtensa-lx106", arch="xtensa",
        flash_bytes=4 * 1024 * 1024, ram_bytes=80 * 1024, f_cpu_hz=80_000_000,
        upload_speed=921600, flash_mode="dio", flash_freq="40m",
        upload_protocol="esptool", debug_tool="esptool", supports_live_debug=False,
        frameworks=["arduino"],
    ),

    # --- SAMD (Arduino MKR / Zero) ---
    # MKR boards have no onboard debugger — SWD is only available on
    # unpopulated castellated pads, so live debug needs an external
    # CMSIS-DAP/J-Link probe wired up by hand. Leaving these False until
    # there's a way to represent "debug available, but only with external
    # hardware" distinctly from "board has no debug port at all" (Zero,
    # below, is the one with a genuine onboard debugger).
    "mkrwifi1010": Device(
        id="mkrwifi1010", label="Arduino MKR WiFi 1010", vendor="arduino",
        mcu="samd21g18a", family="SAMD21", core="cortex-m0+", arch="arm-samd",
        flash_bytes=262144, ram_bytes=32768, f_cpu_hz=48_000_000,
        upload_speed=921600, bossac_offset="0x2000",
        upload_protocol="sam-ba", debug_tool="bossac", supports_live_debug=False,
        frameworks=["arduino"],
    ),
    "mkrzero": Device(
        id="mkrzero", label="Arduino MKR Zero", vendor="arduino",
        mcu="samd21g18a", family="SAMD21", core="cortex-m0+", arch="arm-samd",
        flash_bytes=262144, ram_bytes=32768, f_cpu_hz=48_000_000,
        upload_speed=921600, bossac_offset="0x2000",
        upload_protocol="sam-ba", debug_tool="bossac", supports_live_debug=False,
        frameworks=["arduino"],
    ),
    "zeroUSB": Device(
        id="zeroUSB", label="Arduino Zero (Native USB port)", vendor="arduino",
        mcu="samd21g18a", family="SAMD21", core="cortex-m0+", arch="arm-samd",
        flash_bytes=262144, ram_bytes=32768, f_cpu_hz=48_000_000,
        upload_speed=921600, bossac_offset="0x2000",
        upload_protocol="sam-ba", debug_tool="openocd",
        # Arduino Zero has a genuine onboard EDBG chip wired via SWD to the
        # SAMD21 — separate from either USB port used for flashing/serial,
        # so it works the same whether you build for zeroUSB (native port)
        # or the Programming-port variant. EDBG speaks CMSIS-DAP, so this
        # goes through the same OpenOCD+arm-none-eabi-gdb pipeline as
        # STM32 debug sessions (see services/debug.py) rather than needing
        # anything SAMD-specific.
        openocd_target="target/at91samdXX.cfg",
        openocd_interface="interface/cmsis-dap.cfg",
        supports_live_debug=True,
        frameworks=["arduino"],
    ),

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
    # Released newer-family boards. Device identities and memory/clock values
    # are sourced from ST's product pages/data briefs; keeping these curated
    # prevents support from depending on a user's optional PlatformIO cache.
    "nucleo_c031c6": Device(
        id="nucleo_c031c6", label="STM32C031C6 (Nucleo-64)", vendor="st",
        mcu="STM32C031C6Tx", family="STM32C0", core="cortex-m0plus",
        flash_bytes=32 * 1024, ram_bytes=12 * 1024, f_cpu_hz=48_000_000,
        hal_header="stm32c0xx_hal.h",
        openocd_target="target/stm32c0x.cfg", openocd_interface="interface/stlink.cfg",
    ),
    "nucleo_c562re": Device(
        id="nucleo_c562re", label="STM32C562RE (Nucleo-64)", vendor="st",
        mcu="STM32C562RETx", family="STM32C5", core="cortex-m33",
        flash_bytes=512 * 1024, ram_bytes=128 * 1024, f_cpu_hz=144_000_000,
        hal_header="stm32c5xx_hal.h",
        openocd_target="target/stm32c5x.cfg", openocd_interface="interface/stlink.cfg",
    ),
    "nucleo_u083rc": Device(
        id="nucleo_u083rc", label="STM32U083RC (Nucleo-64)", vendor="st",
        mcu="STM32U083RCTx", family="STM32U0", core="cortex-m0plus",
        flash_bytes=256 * 1024, ram_bytes=40 * 1024, f_cpu_hz=56_000_000,
        hal_header="stm32u0xx_hal.h",
        openocd_target="target/stm32u0x.cfg", openocd_interface="interface/stlink.cfg",
    ),
    "nucleo_wb09ke": Device(
        id="nucleo_wb09ke", label="STM32WB09KE (Nucleo-64)", vendor="st",
        mcu="STM32WB09KEVx", family="STM32WB0", core="cortex-m0plus",
        flash_bytes=512 * 1024, ram_bytes=64 * 1024, f_cpu_hz=64_000_000,
        hal_header="stm32wb0x_hal.h",
        openocd_target="target/stm32wb0x.cfg", openocd_interface="interface/stlink.cfg",
    ),
    "nucleo_wba55cg": Device(
        id="nucleo_wba55cg", label="STM32WBA55CG (Nucleo-64)", vendor="st",
        mcu="STM32WBA55CGUx", family="STM32WBA", core="cortex-m33",
        flash_bytes=1024 * 1024, ram_bytes=128 * 1024, f_cpu_hz=100_000_000,
        hal_header="stm32wbaxx_hal.h",
        openocd_target="target/stm32wbax.cfg", openocd_interface="interface/stlink.cfg",
    ),
    "nucleo_u3c5zi_q": Device(
        id="nucleo_u3c5zi_q", label="STM32U3C5ZI-Q (Nucleo-144)", vendor="st",
        mcu="STM32U3C5ZIT6Q", family="STM32U3", core="cortex-m33",
        flash_bytes=2 * 1024 * 1024, ram_bytes=640 * 1024, f_cpu_hz=96_000_000,
        hal_header="stm32u3xx_hal.h",
        openocd_target="target/stm32u3x.cfg", openocd_interface="interface/stlink.cfg",
    ),
    "stm32n6570_dk": Device(
        id="stm32n6570_dk", label="STM32N6570-DK Discovery", vendor="st",
        mcu="STM32N657X0H3Q", family="STM32N6", core="cortex-m55",
        # N657X0 is a flashless MCU; the kit supplies external xSPI storage.
        flash_bytes=0, ram_bytes=4 * 1024 * 1024, f_cpu_hz=800_000_000,
        hal_header="stm32n6xx_hal.h",
        openocd_target="target/stm32n6x.cfg", openocd_interface="interface/stlink.cfg",
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
        self._custom: dict[str, Device] = {}
        self._catalog: dict[str, Device] = load_catalog()
        self._load_cache()
        self._load_custom()

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

    def _load_custom(self) -> None:
        if not CUSTOM_PATH.exists():
            return
        try:
            raw = json.loads(CUSTOM_PATH.read_text(encoding="utf-8"))
            self._custom = {
                bid: self._reclassify(Device(**data)) for bid, data in raw.items()
            }
        except Exception as exc:
            print(f"[registry] custom board load failed, ignoring: {exc}")
            self._custom = {}

    @staticmethod
    def _reclassify(device: Device) -> Device:
        """Re-derive family/core/hal_header/openocd_target from the device's
        mcu string using the *current* family_map, instead of trusting
        whatever was on disk. The cache is written once by refresh() and can
        go stale relative to family_map.py (e.g. a family added after the
        cache was last generated) — this makes the cache self-heal on every
        load rather than silently carrying "unknown"/wrong classifications
        until someone remembers to hit /api/boards/refresh."""
        # PlatformIO abbreviates Texas Instruments as "TI". Normalize it at
        # the registry boundary so a manufacturer filter returns both the
        # curated TI catalog and every PlatformIO-imported TI board.
        if device.vendor.strip().lower() == "ti" and not device.manufacturer:
            device = device.model_copy(update={
                "manufacturer": "Texas Instruments",
                "mcu_manufacturer": "Texas Instruments",
            })
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

    def _write_custom(self) -> None:
        CUSTOM_PATH.parent.mkdir(parents=True, exist_ok=True)
        raw = {bid: device.model_dump() for bid, device in self._custom.items()}
        CUSTOM_PATH.write_text(json.dumps(raw, indent=2), encoding="utf-8")

    def list(self) -> list[Device]:
        # Existing curated seed keeps precedence for backward compatibility;
        # custom boards still win over every built-in source.
        merged = {**self._catalog, **self._imported, **_SEED, **self._custom}
        return sorted((self._with_pinout_metadata(d) for d in merged.values()), key=lambda d: d.id)

    def default(self) -> Device:
        return _SEED["bluepill_f103c8"]

    def refresh(self, query: str = "STM32") -> int:
        """Re-import a single query's worth of boards from PlatformIO and
        merge into the imported cache (does not clear other platforms'
        entries — call refresh_all() to rebuild the whole cache from
        scratch). Never raises — returns 0 and leaves the existing cache
        untouched on failure."""
        imported = import_boards(query)
        if not imported:
            return 0
        self._imported.update({d.id: self._reclassify(d) for d in imported})
        self._write_cache()
        return len(imported)

    def refresh_all(self) -> dict[str, int]:
        """Rebuild the imported cache from every known platform query.
        Returns a per-query breakdown (e.g. {"STM32": 299, "Arduino": 27,
        "ESP32": 14, ...}) rather than a bare total, since a single number
        hides which platform(s) actually came back with 0 (e.g. `pio` not
        finding a match, or a query string PlatformIO doesn't recognize)."""
        self._imported = {}
        breakdown: dict[str, int] = {}
        arduino_imported = import_arduino_framework_boards()
        self._imported.update({d.id: self._reclassify(d) for d in arduino_imported})
        breakdown["Arduino-framework"] = len(arduino_imported)

        # TI is queried explicitly as PlatformIO does not include it in the
        # STM32/Arduino/ESP platform searches.  These independent searches
        # keep every currently PlatformIO-listed TI target discoverable.
        for query in ("STM32", "ESP32", "ESP8266", "MSP430", "MSP432", "Tiva"):
            imported = import_boards(query)
            self._imported.update({d.id: self._reclassify(d) for d in imported})
            breakdown[query] = len(imported)
        self._write_cache()
        return breakdown
    
    def get(self, board_id: str) -> Device | None:
        device = self._custom.get(board_id) or _SEED.get(board_id) or self._imported.get(board_id) or self._catalog.get(board_id)
        if device:
            device = self._with_pinout_metadata(device)
        if device and device.full_pinout is None:
            from boards.pinout import get_full_pinout
            pinout = get_full_pinout(board_id, mcu=device.mcu)
            if pinout:
                device = device.model_copy(update={
                    "full_pinout": pinout,
                    "package_pins": len(pinout),
                    "pinout_status": "verified",
                })
        # A curated package pin list and signal-level MCU metadata complement
        # each other. Previously, having full_pinout suppressed the metadata
        # lookup, so even well-known Nucleo boards lost all alternate-function
        # information before Phase 3 tried to assign I2C/SPI/UART pins.
        if device and device.arch == "arm-stm32" and device.pin_metadata is None:
            try:
                from boards.stm32_metadata import get_mcu_metadata
                meta = get_mcu_metadata(device.mcu)
            except Exception:
                meta = None
            if meta and meta.get("pins"):
                pinout = device.full_pinout or [pin["name"] for pin in meta["pins"]]
                device = device.model_copy(update={
                    "full_pinout": pinout,
                    "package_pins": len(pinout),
                    "pinout_status": device.pinout_status if device.full_pinout else "st_open_pin_data",
                    "pin_metadata": meta["pins"],
                })
        if device and device.arch in {"avr", "xtensa", "arm-samd", "arduino-generic"} and device.arduino_pinout is None:
            from boards.pinout import get_arduino_pinout
            header = get_arduino_pinout(board_id, mcu=device.mcu, arch=device.arch)
            if header:
                device = device.model_copy(update={"arduino_pinout": header})
        return device

    def add_custom(self, device: Device) -> Device:
        classified = self._with_pinout_metadata(self._reclassify(device))
        self._custom[classified.id] = classified
        self._write_custom()
        return classified

    @staticmethod
    def _with_pinout_metadata(device: Device) -> Device:
        package_pins = device.package_pins or derive_package_pin_count(device.mcu)
        pinout_status = device.pinout_status
        if device.full_pinout:
            package_pins = len(device.full_pinout)
            pinout_status = "verified"
        elif package_pins:
            pinout_status = "package_count_only"
        return device.model_copy(update={
            "package_pins": package_pins,
            "pinout_status": pinout_status,
        })


registry = BoardRegistry()
