from services.board_selection import infer_board_requirements, select_board_for_plan


def test_explicit_board_name_wins_across_registry():
    decision = select_board_for_plan(
        plan="Use the ESP32-S3-DevKitC-1 with Arduino and native USB.",
        components=[],
        current_board_id="bluepill_f103c8",
    )

    assert decision["selected_board_id"] == "esp32-s3-devkitc-1"
    assert decision["confidence"] == "high"
    assert decision["registry_size"] >= 10


def test_wireless_plan_moves_default_stm32_to_capable_board():
    decision = select_board_for_plan(
        plan="A Wi-Fi and Bluetooth environmental monitor using the Arduino framework.",
        components=[],
        current_board_id="bluepill_f103c8",
    )

    board = decision["selected"]["board"]
    assert "ESP32" in board["family"]
    assert board["frameworks"] == ["arduino"]
    assert {"wifi", "bluetooth"}.issubset(decision["requirements"]["connectivity"])


def test_explicit_controller_component_is_authoritative():
    decision = select_board_for_plan(
        plan="Read an OLED over I2C.",
        components=[{
            "id": "esp32-devkit-v1",
            "name": "ESP32 DevKit V1",
            "category": "Microcontroller",
            "visual_type": "board",
        }],
        current_board_id="nucleo_f446re",
    )

    assert decision["selected_board_id"] == "esp32dev"
    assert decision["confidence"] == "high"


def test_ambiguous_plan_keeps_compatible_current_board():
    decision = select_board_for_plan(
        plan="Blink a status LED.",
        components=[],
        current_board_id="nucleo_f446re",
    )

    assert decision["selected_board_id"] == "nucleo_f446re"


def test_component_pin_demand_is_extracted_for_ranking():
    requirements = infer_board_requirements("Read two sensors", [{
        "name": "module",
        "pins": [
            {"name": "VCC", "role": "power"},
            {"name": "GND", "role": "ground"},
            {"name": "SDA", "role": "i2c"},
            {"name": "SCL", "role": "i2c"},
            {"name": "IRQ", "role": "gpio"},
        ],
    }])

    assert requirements["minimum_gpio"] == 3
