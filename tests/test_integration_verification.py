import asyncio

import services.integration_verification as verification_service
from services.integration_verification import (
    build_pin_configuration,
    design_pin_assignments,
    infer_protocols,
    phase3_todos,
    render_connection_diagram,
    render_pin_diagram,
    set_todo_status,
)


def test_phase3_todos_are_required_ordered_and_mutable():
    state = {"todos": phase3_todos([{"id": "oled", "name": "OLED"}])}

    assert state["todos"][0]["id"] == "select:board"
    assert state["todos"][1]["id"] == "verify:oled"
    assert all(item["required"] for item in state["todos"])
    assert state["todos"][-1]["id"] == "act:flash"

    set_todo_status(state, "verify:oled", "completed", "4 pins checked")
    assert state["todos"][1]["status"] == "completed"
    assert state["todos"][1]["detail"] == "4 pins checked"


def test_protocol_inference_and_board_pin_design_share_i2c_bus():
    pins = [
        {"name": "VCC", "label": "VCC", "role": "power"},
        {"name": "GND", "label": "GND", "role": "ground"},
        {"name": "SDA", "label": "SDA", "role": "i2c data"},
        {"name": "SCL", "label": "SCL", "role": "i2c clock"},
    ]
    assert infer_protocols(pins) == ["I2C"]

    board = {"id": "esp32dev", "label": "ESP32", "family": "ESP32", "arch": "xtensa"}
    verified = [
        {"component_id": "oled", "name": "OLED", "pins": pins, "protocols": ["I2C"]},
        {"component_id": "bme", "name": "BME280", "pins": pins, "protocols": ["I2C"]},
    ]
    assignments = design_pin_assignments(board, verified)

    sda_pins = {item["board_pin"] for item in assignments if item["component_pin"] == "SDA"}
    scl_pins = {item["board_pin"] for item in assignments if item["component_pin"] == "SCL"}
    assert sda_pins == {"GPIO21"}
    assert scl_pins == {"GPIO22"}
    assert "GPIO21" in render_pin_diagram(board, assignments)
    assert "flowchart LR" in render_connection_diagram(board, assignments)
    config = build_pin_configuration(board, assignments, verified)
    assert config["board"]["id"] == "esp32dev"
    assert config["protocols"] == ["I2C"]
    assert config["pin_mapping_quality"] == "verified"


def test_generic_arduino_board_marks_framework_pin_constants_provisional():
    board = {
        "id": "mkrwifi1010",
        "label": "MKR WiFi 1010",
        "family": "SAMD21",
        "arch": "arm-samd",
        "arduino_pinout": {
            "digital": [f"D{i}" for i in range(14)],
            "i2c": ["SDA", "SCL"],
            "status": "generic_arduino_api",
        },
    }
    verified = [{
        "component_id": "oled",
        "name": "OLED",
        "pins": [
            {"name": "SDA", "label": "SDA", "role": "i2c data"},
            {"name": "SCL", "label": "SCL", "role": "i2c clock"},
        ],
        "protocols": ["I2C"],
    }]

    assignments = design_pin_assignments(board, verified)

    assert {item["board_pin"] for item in assignments} == {"SDA", "SCL"}
    assert {item["status"] for item in assignments} == {"provisional"}
    config = build_pin_configuration(board, assignments, verified)
    assert config["pin_mapping_quality"] == "provisional"


def test_online_verification_reports_granular_activity(monkeypatch):
    async def run_inline(function, *args):
        return function(*args)

    monkeypatch.setattr(verification_service.asyncio, "to_thread", run_inline)
    monkeypatch.setattr(
        verification_service,
        "search_web",
        lambda query, count: [{
            "title": "Example official datasheet",
            "url": "https://example.com/part.pdf",
            "snippet": "SDA and SCL interface pins",
        }],
    )
    monkeypatch.setattr(verification_service, "fetch_datasheet_text", lambda url: "SDA SCL VCC GND")

    async def complete(provider, messages):
        return '{"datasheet_url":"https://example.com/part.pdf","pins":[],"protocols":null,"configuration_notes":null,"warnings":null}'

    monkeypatch.setattr(verification_service.llm, "complete", complete)
    activities = []

    async def report(activity):
        activities.append(activity)

    result = asyncio.run(verification_service.verify_component_online(
        {
            "id": "part",
            "name": "Example Part",
            "pins": [
                {"name": "SDA", "label": "SDA", "role": "i2c"},
                {"name": "SCL", "label": "SCL", "role": "i2c"},
            ],
        },
        "deepseek",
        report,
    ))

    assert [item["phase"] for item in activities] == [
        "web_search", "source_review", "datasheet", "analysis", "validation"
    ]
    assert result["verified"] is True
