"""Builds the board-specific section of the agent's system prompot from the
project's actual Device, replacing what used to be hardcoded Blue Pill text
in solver.py's _AGENT_SYSTEM.
"""

from __future__ import annotations

from boards.device import Device
from boards.registry import registry

# Per-family facts the prompt needs that aren't in the Device model itself
# (onboard LED pin, PLL field names, GPIO quirks). Same curation principle
# as boards/family_map.py — hand-verified, not derived from PlatformIO.
_FAMILY_NOTES: dict[str, dict[str, str]] = {
    "STM32F2": {
    "led_pin": "PA5 (Nucleo-64 onboard LD2 — active HIGH)",
    "gpio_quirk": "GPIO_InitTypeDef HAS an .Alternate field, same shape as F4/F7.",
    "clock_fields": "Uses PLLM/PLLN/PLLP/PLLQ fractional PLL configuration, like F4. "
                    "Enable PWR clock and configure voltage scaling before high-speed clocks.",
    "dma_model": "Stream-based DMA1/DMA2 controller, same model as F4/F7 (streams + channel selection).",
    "adc_notes": "ADC_InitTypeDef includes .Resolution and .ClockPrescaler fields, matching the F4-family HAL.",
    },
    "STM32H5": {
    "led_pin": "PA5 (Nucleo-H563 onboard LD2 — active HIGH)",
    "gpio_quirk": "Same .Alternate field shape as other post-F1 families.",
    "clock_fields": "Uses PLLM/PLLN/PLLP/PLLQ/PLLR configuration similar to modern STM32 families. "
                    "Voltage scaling and FLASH latency must be configured before high-speed operation.",
    "dma_model": "Uses GPDMA rather than classic DMA1/DMA2 streams or DMAMUX-based DMA. "
                 "Initialization API differs from F4/F7/L4 families.",
    "adc_notes": "Modern ADC_InitTypeDef with Resolution and ClockPrescaler fields. "
                 "Cortex-M33 with TrustZone support, but this template assumes non-secure mode unless explicitly configured.",
    },
    "STM32G4": {
        "led_pin": "PA5 (Nucleo-64 onboard LD2 — active HIGH)",
        "gpio_quirk": "Same .Alternate field shape as F4/F7/L4.",
        "clock_fields": "HSI16 internal + PLLM/PLLN/PLLR (same 3-output PLL shape as L4). "
                         "170 MHz needs PWR_REGULATOR_VOLTAGE_SCALE1_BOOST and FLASH_LATENCY_4.",
        "dma_model": "DMAMUX, same as L4 — DMA_HandleTypeDef.Init.Request field.",
        "adc_notes": "Same .Resolution/.ClockPrescaler shape as F4/F7/L4.",
    },
    "STM32G0": {
        "led_pin": "PA5 (Nucleo-64 onboard LD2 — active HIGH)",
        "gpio_quirk": "Same .Alternate field shape as other post-F1 families.",
        "clock_fields": "HSI16 internal + PLLM/PLLN/PLLR, simpler than G4/L4 (no PLLQ needed). "
                         "64 MHz max needs FLASH_LATENCY_2.",
        "dma_model": "DMAMUX, same as L4/G4.",
        "adc_notes": "Same .Resolution/.ClockPrescaler shape as other post-F1 families. "
                      "Cortex-M0+ core has NO NVIC sub-priority — priority grouping is always 0.",
    },
    "STM32H7": {
        "led_pin": "PB0 (Nucleo-144 H743ZI onboard LD1 — active HIGH)",
        "gpio_quirk": "Same .Alternate field shape as other post-F1 families.",
        "clock_fields": "HAS FOUR APB domains (D1/D2/D3), not two — RCC_CLOCKTYPE_D1PCLK1/"
                         "D3PCLK1 fields exist ONLY on H7. Power supply scheme (LDO/SMPS) is "
                         "board-specific hardware — verify before trusting generated clock code.",
        "dma_model": "Stream-based, same as F4/F7.",
        "adc_notes": "Same .Resolution field as F4/F7/L4/G4/G0, but ClockPrescaler uses "
                      "ADC_CLOCK_ASYNC_* values (H7's ADC clock can run async from AHB).",
    },
    "STM32L0": {
        "led_pin": "PA5 (Nucleo-32/64 onboard LD2 — active HIGH)",
        "gpio_quirk": "HAS .Alternate field, same shape as F4/F7/L4/G4/G0 (unlike F1).",
        "clock_fields": "OLDER PLLMUL/PLLDIV scheme (not PLLM/N/P/Q/R). Must switch to voltage "
                         "range 1 before exceeding 16 MHz — the default range hard-faults at 32 MHz.",
        "dma_model": "Single DMA1 with numbered channels, like F1 — L0 predates DMAMUX.",
        "adc_notes": "Simpler ADC_InitTypeDef than post-L4 families — check exact field names "
                      "against the L0 HAL, they differ from the F4/L4/G4/G0 shape used elsewhere.",
    },
    "STM32L5": {
        "led_pin": "PA5 (Nucleo-L552 onboard LD2 — active HIGH)",
        "gpio_quirk": "Same .Alternate field shape as L4/G4/G0.",
        "clock_fields": "Same PLLM/N/P/Q/R shape as L4, higher max (110 MHz vs 80 MHz).",
        "dma_model": "DMAMUX, same as L4.",
        "adc_notes": "Same .Resolution/.ClockPrescaler shape as L4/G4/G0. "
                      "TrustZone security isolation is available but NOT configured by "
                      "this template (non-secure/default mode only) — flag this to the "
                      "user if they ask about secure-world features.",
    },
    "STM32WB": {
        "led_pin": "PB5 (Nucleo-WB55 onboard LD2 — active HIGH)",
        "gpio_quirk": "Same .Alternate field shape as L4/L5.",
        "clock_fields": "Same PLLM/N/P/Q/R shape as L4, lower max (64 MHz, CPU1/M4 only).",
        "dma_model": "DMAMUX, same as L4/L5.",
        "adc_notes": "Same .Resolution/.ClockPrescaler shape as L4/L5. "
                      "IMPORTANT: WB has a second Cortex-M0+ core running the BLE/802.15.4 "
                      "radio stack. This template only brings up CPU1 (the M4) — it does NOT "
                      "configure or wake the radio co-processor. If the user asks about BLE, "
                      "IPCC, or the wireless stack, tell them this isn't covered here.",
    },
    "STM32U5": {
        "led_pin": "PA5 (Nucleo-U575 onboard LD2 — active HIGH)",
        "gpio_quirk": "Same .Alternate field shape as other post-F1 families.",
        "clock_fields": "Uses a split MSI (MSIS/MSIK) unique to U5 — PLL source is MSIS, "
                         "not plain MSI. Exact PLLM/N/R values here are structurally correct "
                         "but less rigorously verified than other families — double-check "
                         "against CubeMX before trusting on real hardware.",
        "dma_model": "GPDMA (Generalized DMA) — a newer, different controller from the "
                      "DMAMUX-based DMA1 used on L4/L5/WB/G4/G0. Different init API.",
        "adc_notes": "ADC1/ADC4/DAC1 share a clock mux unique to U5 (SYSCLK/HCLK/pll2_r/"
                      "HSE/HSI16/MSIK inputs) — different from every other family here. "
                      "TrustZone available but NOT configured (non-secure/default mode only).",
    },
    "STM32WL": {
        "led_pin": "PB5 (Nucleo-WL55JC onboard LD2 — active HIGH)",
        "gpio_quirk": "Same .Alternate field shape as WB/L4/L5.",
        "clock_fields": "Runs directly off MSI at 4 MHz with NO PLL by default (matches ST's "
                         "own LoRa reference examples) — prioritizes low power over speed. "
                         "VOLTAGE_SCALE2, FLASH_LATENCY_0.",
        "dma_model": "DMAMUX, same as WB/L4/L5.",
        "adc_notes": "Same .Resolution/.ClockPrescaler shape as WB/L4/L5. "
                      "IMPORTANT: dual-core parts (e.g. WL55) have a second Cortex-M0+ core "
                      "running the sub-GHz LoRa/(G)FSK radio stack — NOT configured by this "
                      "template. Some WL parts (WLE5) are single-core M4 only. If the user "
                      "asks about LoRa, SubGHz, or the radio, tell them this isn't covered here.",
    },
    "STM32C0": {
        "led_pin": "PA5 (Nucleo-64 convention, assumed by analogy — not confirmed per-board; "
                    "some C0 boards are Nucleo-32 with a different LED pin, verify against the "
                    "board's User Manual).",
        "gpio_quirk": "Same .Alternate field shape as other post-F1 families.",
        "clock_fields": "NO PLL on this family at all (confirmed in RM0490) — SYSCLK comes "
                         "directly from HSI48 divided by HSIDIV, max 48 MHz. Do not generate "
                         "PLL.* struct fields for C0, HAL_RCC_OscConfig will reject them.",
        "dma_model": "Single DMA1 with numbered channels, no DMAMUX — entry-level part, same "
                      "generation pattern as L0/L1/F1.",
        "adc_notes": "Same .Resolution/.ClockPrescaler shape as other post-F1 families. "
                      "Cortex-M0+ core has NO NVIC sub-priority — priority grouping is always 0. "
                      "Flash wait-state count (1WS at 48 MHz) is inferred from the same-generation "
                      "G0/F0/L0 pattern, not individually confirmed against RM0490's own table.",
    },
    "STM32U0": {
        "led_pin": "PA5 (Nucleo-64 convention, assumed by analogy — not confirmed per-board; "
                    "verify against the board's User Manual).",
        "gpio_quirk": "Same .Alternate field shape as other post-F1 families.",
        "clock_fields": "Newer PLLM/PLLN/PLLR field scheme (like G0/G4), NOT L0's older "
                         "PLLMUL/PLLDIV. Generated code deliberately targets a conservative "
                         "32 MHz SYSCLK rather than U0's documented maximum — ST's own RM0503, "
                         "datasheet, and CubeMX disagree with each other on that number (56 vs "
                         "64 MHz have both been cited), so don't push higher without resolving "
                         "that discrepancy against your specific silicon revision first.",
        "dma_model": "Assumed single DMA1 with numbered channels, no DMAMUX, by analogy with "
                      "C0/L0 — not individually confirmed against RM0503's DMA chapter.",
        "adc_notes": "Same .Resolution/.ClockPrescaler shape as other post-F1 families. "
                      "Cortex-M0+ core has NO NVIC sub-priority — priority grouping is always 0.",
    },
    "STM32C5": {
        "led_pin": "PA5 assumed (Nucleo-64 convention) — UNVERIFIED, C5 is brand-new, no quoted board schematic.",
        "gpio_quirk": "Same .Alternate field shape as other post-F1 families.",
        "clock_fields": "BEST-EFFORT: modeled on U5/H5's PLLM/N/P/Q/R scheme, conservative 48 MHz target. Not matched against a real RM/DS quote — verify before trusting.",
        "dma_model": "BEST-EFFORT: GPDMA assumed by analogy with U5/H5, unverified.",
        "adc_notes": "BEST-EFFORT: post-F1 ADC shape assumed. Cortex-M33, 4-bit NVIC preemption, unverified for this family.",
    },
    "STM32WB0": {
        "led_pin": "PA5 assumed (Nucleo-64 convention) — UNVERIFIED.",
        "gpio_quirk": "Same .Alternate field shape as other post-F1 families.",
        "clock_fields": "STRUCTURAL WARNING: BLE part — like WBA, ST expects clock changes to go through its own stack helpers once radio is active, not bare HAL_RCC_ClockConfig. Generated block is HSI-only, fine for non-radio bring-up only.",
        "dma_model": "BEST-EFFORT: single DMA1, no DMAMUX, by analogy with C0. Unverified.",
        "adc_notes": "BEST-EFFORT, unverified. Cortex-M0+, no NVIC sub-priority.",
    },
    "STM32WBA": {
        "led_pin": "PB4 assumed from board connector layout pattern — UNVERIFIED, check UM3103's actual schematic before trusting.",
        "gpio_quirk": "Same .Alternate field shape as other post-F1 families.",
        "clock_fields": "STRUCTURAL WARNING: ST documents a dedicated System Clock Manager (SCM) for WBA because the BLE stack force-switches the clock to 16 MHz internally during radio init — route clock changes through scm_setsystemclock(), not raw HAL_RCC_ClockConfig, once BLE is in play. Known rev-A PLL step-switch errata (ES0592) too. Generated block is safe for non-radio bring-up only.",
        "dma_model": "BEST-EFFORT: GPDMA assumed by analogy with H5/U5, unverified.",
        "adc_notes": "BEST-EFFORT, unverified. Cortex-M33, 4-bit NVIC preemption.",
    },
    "STM32U3": {
        "led_pin": "PA5 assumed (Nucleo-64 convention) — UNVERIFIED.",
        "gpio_quirk": "Same .Alternate field shape as other post-F1 families.",
        "clock_fields": "BEST-EFFORT: modeled directly on U5's PLLM/N/P/Q/R scheme (U3 is U5's newer low-power sibling), conservative 48 MHz target, not matched against a quoted RM/DS example.",
        "dma_model": "BEST-EFFORT: GPDMA assumed by analogy with U5, unverified.",
        "adc_notes": "BEST-EFFORT, unverified. Cortex-M33, 4-bit NVIC preemption.",
    },
    "STM32N6": {
        "led_pin": "PA5 placeholder — N6 has no Nucleo-64 form factor (it's the STM32N6570-DK Discovery board), near-certainly wrong. Check the DK schematic.",
        "gpio_quirk": "Same .Alternate field shape as other post-F1 families.",
        "clock_fields": "HIGH RISK: N6 is an AI/NPU application-class part with its own multi-PLL RCC scheme (RM0486) and an external boot-flash-loader stage this template doesn't attempt to replicate. Treat generated RCC code as a placeholder, not a working bring-up — port ST's actual STM32CubeN6 clock example in by hand.",
        "dma_model": "BEST-EFFORT: stream-based DMA assumed by analogy with H7, unverified — N6 may use GPDMA/HPDMA instead per RM0486.",
        "adc_notes": "BEST-EFFORT, unverified. Cortex-M55, 4-bit NVIC preemption assumed.",
    },
    "STM32V8": {
        "led_pin": "PA5 placeholder — no real board exists yet (Nucleo-V8 still 'coming soon' per ST).",
        "gpio_quirk": "Same .Alternate field shape as other post-F1 families.",
        "clock_fields": "HIGHEST RISK IN THIS SET: V8 was only announced Nov 2025 (OEM availability Q1 2026) — no public datasheet or reference manual exists to verify anything against yet. Modeled on H7 (ST describes V8 as a non-pin-compatible H7 update) purely as a structural placeholder. Replace this whole block once ST publishes real RM/DS for V8 — do not build on these numbers.",
        "dma_model": "BEST-EFFORT: stream-based DMA assumed by analogy with H7, unverified — V8 may use GPDMA/HPDMA instead.",
        "adc_notes": "BEST-EFFORT, unverified. Cortex-M85, 4-bit NVIC preemption assumed.",
    },
    "STM32F0": {
        "led_pin": "PA5 (Nucleo-F0 onboard LD2 — active HIGH)",
        "gpio_quirk": "HAS .Alternate field, same as F4/F7/L-series (unlike F1).",
        "clock_fields": "OLDER PREDIV/PLLMUL scheme (not PLLM/N/P/Q/R), same as F1/F3/L0/L1. "
                         "Typically runs off internal HSI48 (no crystal needed) at 48 MHz max.",
        "dma_model": "Single DMA1 with numbered channels, like F1 — F0 predates DMAMUX.",
        "adc_notes": "Simpler ADC_InitTypeDef, check exact fields against F0 HAL.",
    },
    "STM32F3": {
        "led_pin": "PA5 (Nucleo-F303 onboard LD2 — active HIGH)",
        "gpio_quirk": "HAS .Alternate field, same as F4/F7/L-series.",
        "clock_fields": "Same PREDIV/PLLMUL scheme and same 8 MHz HSE * 9 = 72 MHz formula as F1.",
        "dma_model": "Single DMA1 with numbered channels, same as F1/F0.",
        "adc_notes": "ADC12 shared clock-enable macro (like F0), but richer ADC_InitTypeDef "
                      "fields closer to F4's shape.",
    },
    "STM32L1": {
        "led_pin": "PA5 (Nucleo-64 onboard LD2 — active HIGH)",
        "gpio_quirk": "Same .Alternate field shape as L0.",
        "clock_fields": "Same PLLMUL/PLLDIV scheme and voltage-range gotcha as L0.",
        "dma_model": "Single DMA1 with numbered channels, same as L0/F1.",
        "adc_notes": "Older ADC_InitTypeDef shape, distinct from post-L4 families.",
    },
    "STM32L4": {
        "led_pin": "PA5 (Nucleo-64 onboard LD2 — active HIGH)",
        "gpio_quirk": "Same .Alternate field shape as F4/F7 for AF pins.",
        "clock_fields": "Uses MSI (internal, no crystal) + PLLM/PLLN/PLLR (PLLR, not PLLP, feeds SYSCLK — L4-specific). Max 80 MHz needs FLASH_LATENCY_4.",
        "dma_model": "Uses DMAMUX — any DMA channel can serve any peripheral request via DMA_HandleTypeDef.Init.Request. This field does NOT exist on F1/F4/F7's HAL.",
        "adc_notes": "Same .Resolution/.ClockPrescaler shape as F4/F7.",
    },
    "STM32F1": {
        "led_pin": "PC13 (active LOW — drive low to turn the LED on)",
        "gpio_quirk": "F1 GPIO has NO .Alternate field. Never write .Alternate = GPIO_AFx_.... "
                      "Enable AFIO clock with __HAL_RCC_AFIO_CLK_ENABLE() for any remapped pin.",
        "clock_fields": "Use RCC_PLL_MUL9-style single-multiplier PLL fields — never PLLM/PLLN/PLLP/PLLQ (those are F4/F7/H7 only).",
        "dma_model": "Single DMA1 controller with numbered channels (DMA1_Channel1_IRQn, etc.), not streams.",
        "adc_notes": "ADC is fixed 12-bit. ADC_InitTypeDef has NO .Resolution or .ClockPrescaler field.",
    },
    "STM32F4": {
        "led_pin": "PA5 (Nucleo-64 boards' onboard LD2 — active HIGH)",
        "gpio_quirk": "F4 GPIO_InitTypeDef HAS a .Alternate field — required for any AF pin "
                      "(UART TX/RX, SPI SCK/MISO/MOSI, etc). Set it to the correct GPIO_AFx_<PERIPH> value.",
        "clock_fields": "Use fractional PLL fields: PLLM, PLLN, PLLP, PLLQ. Enable the power interface "
                         "clock (__HAL_RCC_PWR_CLK_ENABLE()) and set voltage scaling before configuring the PLL.",
        "dma_model": "Two DMA controllers (DMA1, DMA2), each with 8 numbered streams, each stream also "
                      "needs a channel selection — a different model from F1's single controller + channels.",
        "adc_notes": "ADC_InitTypeDef HAS .Resolution and .ClockPrescaler fields that F1 lacks.",
    },
    "STM32F7": {
        "led_pin": "PI1 (Discovery-F746/F767 onboard LD1)",
        "gpio_quirk": "F7 GPIO_InitTypeDef HAS a .Alternate field, same as F4 — required for any AF pin.",
        "clock_fields": "Fractional PLL (PLLM/PLLN/PLLP/PLLQ), same shape as F4, but F7 needs "
                         "HAL_PWREx_EnableOverDrive() above 180 MHz and FLASH_LATENCY_7 at 216 MHz.",
        "dma_model": "Stream-based DMA1/DMA2, same model as F4.",
        "adc_notes": "Same .Resolution/.ClockPrescaler fields as F4.",
    },
}

_BOARD_NOTES: dict[str, dict[str, str]] = {
    "bluepill_f103c8": {
        "led_pin": "PC13 (Blue Pill onboard LED, active LOW)",
        "board_tip": "Blue Pill has no integrated ST-LINK. Use an external ST-LINK or serial bootloader for flashing.",
    },
    "nucleo_f446re": {
        "led_pin": "PA5 (Nucleo-64 onboard LD2 — active HIGH)",
        "board_tip": "Nucleo-64 boards include an on-board ST-LINK and Arduino-compatible headers.",
    },
    "nucleo_g431rb": {
        "led_pin": "PA5 (Nucleo-64 onboard LD2 — active HIGH)",
        "board_tip": "G4 Nucleo boards use the same Nucleo-64 pinout family as other STM32 Nucleo boards.",
    },
    "disco_f746ng": {
        "led_pin": "LED1 (Discovery board onboard LED, active HIGH)",
        "board_tip": "Discovery boards usually expose user buttons and a display header; this template assumes the MCU on the board only.",
    },
}

_DEFAULT_NOTES = _FAMILY_NOTES["STM32F1"]  # Blue Pill stays the safe fallback

_BOARD_NOTES: dict[str, dict[str, str]] = {
    "bluepill_f103c8": {
        "led_pin": "PC13 (Blue Pill onboard LED, active LOW)",
        "board_tip": "Blue Pill has no integrated ST-LINK. Use an external ST-LINK or serial bootloader for flashing.",
    },
    "nucleo_f446re": {
        "led_pin": "PA5 (Nucleo-64 onboard LD2 — active HIGH)",
        "board_tip": "Nucleo-64 boards include an on-board ST-LINK and Arduino-compatible headers.",
    },
    "nucleo_g431rb": {
        "led_pin": "PA5 (Nucleo-64 onboard LD2 — active HIGH)",
        "board_tip": "G4 Nucleo boards use the same Nucleo-64 pinout family as other STM32 Nucleo boards.",
    },
    "disco_f746ng": {
        "led_pin": "LED1 (Discovery board onboard LED, active HIGH)",
        "board_tip": "Discovery boards usually expose user buttons and a display header; this template assumes the MCU on the board only.",
    },
}


def get_device_for_project(project_id: str, session) -> Device:
    """Thin re-export so solver.py doesn't need to import boards.device_manager
    directly — keeps the agent package's dependency surface small."""
    from boards import device_manager
    return device_manager.for_project(project_id, session)


_ARDUINO_BOARD_NOTES: dict[str, dict[str, str]] = {
    "uno": {"led_pin": "D13 (onboard LED, active HIGH)",
            "board_tip": "Uses the STK500 bootloader over USB-serial (CH340/FTDI) — no on-chip debug."},
    "nanoatmega328": {"led_pin": "D13 (onboard LED, active HIGH)",
                       "board_tip": "Older bootloader — upload speed is 57600, not 115200."},
    "megaatmega2560": {"led_pin": "D13 (onboard LED, active HIGH)",
                        "board_tip": "Uses the 'wiring' bootloader protocol, not 'arduino'."},
    "leonardo": {"led_pin": "D13 (onboard LED, active HIGH)",
                 "board_tip": "Native USB (32U4) — enumerates via the avr109/Caterina bootloader; port may change after reset."},
    "micro": {"led_pin": "D13 (onboard LED, active HIGH)",
              "board_tip": "Native USB (32U4), same caveats as Leonardo."},
    "esp32dev": {"led_pin": "no standard onboard LED across ESP32 dev boards — check silkscreen, often GPIO2",
                 "board_tip": "Dual-core Xtensa LX6, WiFi+BT built in. analogWrite on some cores needs the ESP32 LEDC API instead — check the installed Arduino-ESP32 core version."},
    "esp32-s3-devkitc-1": {"led_pin": "onboard addressable RGB LED (often GPIO48) — not a plain digitalWrite pin",
                            "board_tip": "S3 has native USB — some boards need 'Upload Mode' boot-button held during flash."},
    "esp32-c3-devkitm-1": {"led_pin": "check silkscreen — varies by C3 board revision",
                            "board_tip": "RISC-V core (not Xtensa) — same Arduino API surface, different core internals."},
    "nodemcuv2": {"led_pin": "D4/GPIO2 (onboard LED, active LOW)",
                  "board_tip": "ESP8266 has one analog input (A0, 0-1V range) — not multiple ADC channels like ESP32."},
    "d1_mini": {"led_pin": "D4/GPIO2 (onboard LED, active LOW)",
                "board_tip": "Same ESP8266 single-ADC caveat as NodeMCU."},
    "mkrwifi1010": {"led_pin": "check silkscreen (LED_BUILTIN maps correctly via the Arduino core)",
                     "board_tip": "3.3V logic only — do NOT drive 5V into any pin. NINA WiFi module uses SPI internally, don't reuse those pins."},
    "mkrzero": {"led_pin": "check silkscreen (LED_BUILTIN maps correctly via the Arduino core)",
                "board_tip": "3.3V logic only. Has an onboard SD card slot on SPI."},
    "zeroUSB": {"led_pin": "L LED near the USB connector (LED_BUILTIN)",
                "board_tip": "3.3V logic only. Onboard EDBG chip supports real SWD debugging in Arduino IDE — not wired into this app's debug session yet, so treat as flash+Serial Monitor only here."},
}


def _build_arduino_board_context(device: Device) -> str:
    notes = _ARDUINO_BOARD_NOTES.get(device.id, {"led_pin": "check board silkscreen", "board_tip": ""})
    board_tip_line = f"  Notes: {notes['board_tip']}\n" if notes.get("board_tip") else ""
    if device.arch == "avr":
        upload_line = f"avrdude via {device.avrdude_programmer or 'the board default programmer'}, {device.upload_speed or 115200} baud"
    elif device.arch == "arm-samd":
        upload_line = f"bossac (1200bps touch-reset into the UF2/SAM-BA bootloader), {device.upload_speed or 921600} baud"
    else:
        upload_line = f"esptool, {device.upload_speed or 460800} baud"
    return f"""\
══════════════════════════════════════════════════════════════
RULE 1 — BOARD: {device.label} ({device.mcu}, Arduino/{device.family} family)
══════════════════════════════════════════════════════════════
The target for THIS project is: {device.label}
  Board id (use exactly this string when calling generate_hal): {device.id}
  MCU: {device.mcu}
  Framework: Arduino (setup()/loop() — NOT STM32 HAL, NO #include of HAL headers)
  Core clock: {device.f_cpu_hz} Hz

  ✗ Never ask the user which board — it is fixed for this project.
  ✗ Never emit STM32 HAL/register code, HAL_Init(), or #include "stm32*_hal.h" for this board.
  ✗ Never assume live GDB breakpoint debugging is available — this board has no
    on-chip debug interface over its bootloader (flash + Serial Monitor only).

All generated code must use the Arduino API (pinMode/digitalWrite/analogRead/
Serial/Wire/SPI) — this board has no register-level HAL of its own to target.

BOARD-SPECIFIC FACTS:
  Onboard LED: {notes['led_pin']}
  Upload: {upload_line}
{board_tip_line}CODE GENERATION: generate_hal(board, peripherals) — pass board="{device.id}" exactly; \
it emits an Arduino src/main.cpp sketch, not HAL files, for this board.
"""


def _build_espidf_board_context(device: Device) -> str:
    return f"""\
══════════════════════════════════════════════════════════════
RULE 1 — BOARD: {device.label} ({device.mcu}, {device.family} / ESP-IDF)
══════════════════════════════════════════════════════════════
The target for THIS project is: {device.label}
  Board id (use exactly this string when calling generate_hal): {device.id}
  MCU: {device.mcu}
  Framework: ESP-IDF (app_main(), FreeRTOS tasks, esp_* APIs — NOT Arduino setup()/loop())
  Core clock: {device.f_cpu_hz} Hz

  ✗ Never ask the user which board — it is fixed for this project.
  ✗ Never emit STM32 HAL code or Arduino setup()/loop() for this board.
  ✓ Use ESP-IDF headers such as freertos/FreeRTOS.h, freertos/task.h,
    esp_log.h, driver/gpio.h, esp_wifi.h, and related ESP-IDF driver APIs.

BOARD-SPECIFIC FACTS:
  Upload: esptool via PlatformIO, {device.upload_speed or 460800} baud
  GPIO namespace: use GPIO_NUM_x constants and verify strapping/flash pins
  Code entrypoint: void app_main(void)

CODE GENERATION: generate_hal(board, peripherals) — pass board="{device.id}" exactly; \
it emits ESP-IDF src/main.c scaffolding for this board.
"""


def build_board_context(device: Device) -> str:
    """Renders the board-specific block that replaces solver.py's old
    hardcoded RULE 1 / RULE 3.4 Blue-Pill text."""
    from boards.device import uses_arduino_framework, uses_espidf_framework
    if uses_arduino_framework(device):
        return _build_arduino_board_context(device)
    if uses_espidf_framework(device):
        return _build_espidf_board_context(device)

    notes = _FAMILY_NOTES.get(device.family, _DEFAULT_NOTES)
    notes = {**notes, **_BOARD_NOTES.get(device.id, {})}
    pinout_available = "full board pinout available" if device.full_pinout else "no full board pinout available"
    # Local import to avoid a module-load-time circular import between
    # agent/board_context.py and api/routers/hal_codegen.py.
    from api.routers.hal_codegen import is_supported_family
    codegen_supported = is_supported_family(device.family)

    codegen_line = (
        f'generate_hal(board, peripherals) — pass board="{device.id}" exactly.'
        if codegen_supported else
        f"generate_hal() does NOT yet support {device.family} boards. "
        f"If the user asks for HAL init code on this board, tell them this board's "
        f"family isn't supported for code generation yet — do not attempt to write "
        f"peripheral init code by hand as a substitute."
    )

    board_tip = notes.get("board_tip", "")
    board_tip_line = f"  Notes: {board_tip}\n" if board_tip else ""

    return f"""\
══════════════════════════════════════════════════════════════
RULE 1 — BOARD: {device.label} ({device.mcu}, {device.family} family)
══════════════════════════════════════════════════════════════
The target for THIS project is: {device.label}
  Board id (use exactly this string when calling generate_hal): {device.id}
  MCU: {device.mcu}
  HAL header: {device.hal_header}
  Core clock: {device.f_cpu_hz} Hz

  ✗ Never ask the user which board — it is fixed for this project.
  ✗ Never generate code for any STM32 family other than {device.family}.
  ✗ Never use headers, clock fields, or APIs from a different family.

All generated code, clock config, and HAL headers must be {device.family}-specific.

BOARD-SPECIFIC FACTS:
  Onboard LED: {notes['led_pin']}
  GPIO: {notes['gpio_quirk']}
  Clock: {notes['clock_fields']}
  DMA: {notes['dma_model']}
  ADC: {notes['adc_notes']}
  Pinout: {pinout_available}
{board_tip_line}CODE GENERATION: {codegen_line}
"""
