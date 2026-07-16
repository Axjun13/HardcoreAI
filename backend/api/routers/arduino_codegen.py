# arduino_codegen.py
# Arduino-framework counterpart to hal_codegen.py. STM32 HAL codegen exists
# because HAL init is verbose, family-specific, register-level boilerplate
# (RCC trees, DMA channels, NVIC priorities) that's genuinely worth
# generating. The Arduino framework exists specifically to hide all of
# that — there's no RCC/DMA/NVIC to configure — so this module is
# deliberately much smaller: one peripheral-selection UI, one flat
# main.cpp (setup()/loop()) rather than a src/hal/*.c file per peripheral.
#
# Pure function — takes board + peripherals, returns dict of {filepath: content}.
# No file I/O here, same contract as hal_codegen.generate_hal_files().

from __future__ import annotations
import textwrap
from typing import Any

from boards.registry import registry

# id -> (setup_line, loop_comment, extra_includes)
# Arduino pin numbers are placeholders the user swaps in Cursor-style —
# there's no per-family variation to generate here, unlike STM32 where the
# pin/AF mapping genuinely differs per package.
_PERIPHERAL_SNIPPETS: dict[str, dict[str, Any]] = {
    "gpio": {
        "includes": [],
        "globals": "const int LED_PIN = LED_BUILTIN;  // swap for your pin",
        "setup": "pinMode(LED_PIN, OUTPUT);",
        "loop": textwrap.dedent("""\
            digitalWrite(LED_PIN, HIGH);
            delay(500);
            digitalWrite(LED_PIN, LOW);
            delay(500);"""),
    },
    "usart1": {
        "includes": [],
        "globals": "",
        "setup": "Serial.begin(115200);",
        "loop": 'Serial.println("tick");\ndelay(1000);',
    },
    "adc1": {
        "includes": [],
        "globals": "const int ANALOG_PIN = A0;  // swap for your pin",
        "setup": "// analogRead needs no setup on AVR",
        "loop": textwrap.dedent("""\
            int value = analogRead(ANALOG_PIN);
            Serial.println(value);
            delay(200);"""),
    },
    "tim1": {  # PWM — Arduino calls this analogWrite, not a timer peripheral
        "includes": [],
        "globals": "const int PWM_PIN = 9;  // must be a ~PWM-marked pin",
        "setup": "pinMode(PWM_PIN, OUTPUT);",
        "loop": textwrap.dedent("""\
            for (int duty = 0; duty <= 255; duty++) {
                analogWrite(PWM_PIN, duty);
                delay(5);
            }"""),
    },
    "i2c1": {
        "includes": ["#include <Wire.h>"],
        "globals": "",
        "setup": "Wire.begin();",
        "loop": "// Wire.beginTransmission(addr) / Wire.write / Wire.endTransmission()",
    },
    "spi1": {
        "includes": ["#include <SPI.h>"],
        "globals": "",
        "setup": "SPI.begin();",
        "loop": "// SPI.beginTransaction(...) / SPI.transfer(byte) / SPI.endTransaction()",
    },
    "wifi": {  # ESP32/ESP8266 only — selecting this for an AVR board won't compile, same
               # as selecting any peripheral the target chip doesn't physically have.
        "includes": ["#include <WiFi.h>"],
        "globals": 'const char* WIFI_SSID = "your-ssid";\nconst char* WIFI_PASSWORD = "your-password";',
        "setup": textwrap.dedent("""\
            WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
            while (WiFi.status() != WL_CONNECTED) { delay(500); }"""),
        "loop": "// WiFi.status() == WL_CONNECTED to check the link is still up",
    },
}

# STM32-only peripheral ids that have no Arduino-framework equivalent —
# the framework configures these itself, so they're not user-selectable
# knobs the way they are in raw HAL. Recognized (not "unknown") so the
# caller can tell the user why nothing was generated for them, rather than
# it looking like a typo.
_NO_ARDUINO_EQUIVALENT = {"rcc", "dma", "nvic"}


def generate_arduino_files(
    board: str,
    peripherals: list[dict[str, Any]],
) -> dict[str, str]:
    """Returns { "src/main.cpp": "<setup()/loop() sketch>" } — Arduino
    projects don't split into a file-per-peripheral the way HAL codegen
    does, because there's no separate init struct per peripheral to
    generate; pinMode/Serial.begin/etc. are one-liners that all belong in
    setup() together.
    """
    device = registry.get(board)
    label = device.label if device else board

    includes: list[str] = []
    globals_: list[str] = []
    setup_lines: list[str] = []
    loop_lines: list[str] = []
    skipped: list[str] = []
    unknown: list[str] = []

    for p in peripherals:
        pid = p["id"]
        snippet = _PERIPHERAL_SNIPPETS.get(pid)
        if snippet is None:
            (skipped if pid in _NO_ARDUINO_EQUIVALENT else unknown).append(pid)
            continue
        snippet_includes = list(snippet["includes"])
        if pid == "wifi" and device and device.family == "ESP8266":
            snippet_includes = ["#include <ESP8266WiFi.h>"]
        includes.extend(snippet_includes)
        if snippet["globals"]:
            globals_.append(snippet["globals"])
        setup_lines.append(textwrap.indent(snippet["setup"], "  "))
        loop_lines.append(textwrap.indent(snippet["loop"], "  "))

    # Dedupe includes while preserving order (multiple peripherals may want <Wire.h>).
    seen = set()
    includes = [i for i in includes if not (i in seen or seen.add(i))]

    header = (
        f"// main.cpp — generated by HardcoreAI for {label}\n"
        f"#include <Arduino.h>\n"
        + ("\n".join(includes) + "\n" if includes else "")
    )
    body_globals = ("\n".join(globals_) + "\n\n") if globals_ else ""
    setup_body = "\n".join(setup_lines) if setup_lines else "  // nothing selected"
    loop_body = "\n".join(loop_lines) if loop_lines else "  // nothing selected"

    content = (
        f"{header}\n"
        f"{body_globals}"
        f"void setup() {{\n{setup_body}\n}}\n\n"
        f"void loop() {{\n{loop_body}\n}}\n"
    )

    files = {"src/main.cpp": content}

    notes = []
    if skipped:
        notes.append(
            f"// Note: {', '.join(skipped)} have no Arduino-framework equivalent — "
            "the framework configures clocks/DMA/interrupts itself."
        )
    if unknown:
        notes.append(f"// Note: unrecognized peripheral id(s), skipped: {', '.join(unknown)}")
    if notes:
        files["src/main.cpp"] = "\n".join(notes) + "\n\n" + files["src/main.cpp"]

    return files
