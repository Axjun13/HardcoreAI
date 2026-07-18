from backend.api.routers.arduino_codegen import generate_arduino_files
from backend.api.routers.espidf_codegen import generate_espidf_files
from backend.boards.device import uses_arduino_framework, uses_espidf_framework
from backend.boards.family_map import derive_espressif_info
from backend.boards.pio_importer import import_boards
from backend.services.hardware import platformio_ini_for_board


def test_newer_esp_chips_are_classified():
    assert derive_espressif_info("ESP32C3")["core"] == "riscv32"
    assert derive_espressif_info("ESP32C6")["family"] == "ESP32-C6"
    assert derive_espressif_info("ESP32S3")["family"] == "ESP32-S3"
    assert derive_espressif_info("ESP8266")["family"] == "ESP8266"


def test_esp8266_arduino_wifi_uses_correct_header():
    files = generate_arduino_files("nodemcuv2", [{"id": "wifi"}])

    assert "#include <ESP8266WiFi.h>" in files["src/main.cpp"]
    assert "#include <WiFi.h>" not in files["src/main.cpp"]


def test_esp32_arduino_platformio_ini_uses_arduino_framework():
    ini = platformio_ini_for_board("esp32dev")

    assert "platform = espressif32" in ini
    assert "framework = arduino" in ini
    assert "board = esp32dev" in ini


def test_espidf_generator_emits_app_main():
    files = generate_espidf_files("esp32-c6-devkitc-1", [{"id": "gpio"}, {"id": "wifi"}])
    content = files["src/main.c"]

    assert "void app_main(void)" in content
    assert '#include "esp_wifi.h"' in content
    assert "gpio_set_direction" in content


def test_espidf_only_platformio_board_is_not_treated_as_arduino(monkeypatch):
    import backend.boards.pio_importer as importer

    monkeypatch.setattr(importer, "_run_pio_boards", lambda query="": [
        {
            "id": "esp32-c6-devkitc-1",
            "name": "Espressif ESP32-C6-DevKitC-1",
            "platform": "espressif32",
            "mcu": "ESP32C6",
            "fcpu": 160000000,
            "ram": 327680,
            "rom": 8388608,
            "frameworks": ["espidf"],
            "vendor": "Espressif",
            "upload": {"speed": 460800, "protocol": "esptool"},
        }
    ])

    board = import_boards("esp32-c6")[0]

    assert board.arch == "xtensa"
    assert board.core == "riscv32"
    assert board.frameworks == ["espidf"]
    assert uses_espidf_framework(board) is True
    assert uses_arduino_framework(board) is False
