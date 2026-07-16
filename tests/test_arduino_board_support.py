from backend.boards.device import ARDUINO_FRAMEWORK_ARCHES
from backend.boards.pinout import get_arduino_pinout
from backend.boards.pio_importer import import_arduino_framework_boards
from backend.boards.registry import registry
from backend.services.hardware import platformio_ini_for_board


def test_all_arduino_framework_arches_route_to_arduino_codegen():
    assert {"avr", "xtensa", "arm-samd", "arduino-generic"} <= ARDUINO_FRAMEWORK_ARCHES


def test_generic_arduino_pinout_exists_for_imported_board_without_curated_map():
    pinout = get_arduino_pinout("some_new_atmega_board", mcu="ATMEGA328P", arch="avr")

    assert pinout is not None
    assert pinout["status"] == "generic_arduino_api"
    assert "D13" in pinout["digital"]
    assert "A0" in pinout["analog"]


def test_samd_and_esp_get_generic_arduino_api_pin_names():
    samd = get_arduino_pinout("custom_samd", mcu="SAMD21G18A", arch="arm-samd")
    esp = get_arduino_pinout("custom_esp32", mcu="esp32", arch="xtensa")

    assert "SDA" in samd["i2c"]
    assert "GPIO2" in esp["digital"]


def test_platformio_ini_for_seeded_arduino_boards_is_not_stm32cube():
    uno_ini = platformio_ini_for_board("uno")
    zero_ini = platformio_ini_for_board("zeroUSB")

    assert "platform = atmelavr" in uno_ini
    assert "framework = arduino" in uno_ini
    assert "platform = atmelsam" in zero_ini
    assert "framework = arduino" in zero_ini
    assert "framework = stm32cube" not in uno_ini


def test_platformio_arduino_framework_importer_keeps_non_avr_samd_generic(monkeypatch):
    import backend.boards.pio_importer as importer

    monkeypatch.setattr(importer, "_run_pio_boards", lambda query="": [
        {
            "id": "teensy41",
            "name": "Teensy 4.1",
            "vendor": "PJRC",
            "platform": "teensy",
            "frameworks": ["arduino"],
            "mcu": "imxrt1062",
            "fcpu": 600000000,
            "rom": 8126464,
            "ram": 1048576,
            "upload": {"speed": 115200, "protocol": "teensy-cli"},
        },
        {
            "id": "native",
            "name": "Native",
            "vendor": "PlatformIO",
            "platform": "native",
            "frameworks": ["cmsis"],
            "mcu": "native",
        },
    ])

    boards = import_arduino_framework_boards()

    assert len(boards) == 1
    assert boards[0].id == "teensy41"
    assert boards[0].arch == "arduino-generic"
    assert boards[0].pio_platform == "teensy"
    assert boards[0].frameworks == ["arduino"]


def test_registry_returns_curated_and_generic_arduino_pinout():
    uno = registry.get("uno")

    assert uno is not None
    assert uno.arch == "avr"
    assert uno.arduino_pinout is not None
    assert uno.arduino_pinout["status"] == "verified"
