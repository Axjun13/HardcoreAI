from schemas import ComponentDefinition, Pin
from services.research import (
    new_research_context,
    normalize_research_state,
    recommend_components,
    render_project_readme,
    selected_component_ids,
)


def _component(
    cid: str,
    name: str,
    category: str,
    description: str,
    *,
    library_ids=None,
    buy_links=None,
    datasheet_url=None,
    thumbnail="generic",
):
    return ComponentDefinition(
        id=cid,
        name=name,
        category=category,
        description=description,
        visual_type="module",
        thumbnail=thumbnail,
        width=120,
        height=80,
        library_ids=library_ids or [],
        buy_links=buy_links or [],
        datasheet_url=datasheet_url,
        pins=[Pin(name="VCC", label="VCC", side="left", x=0, y=0, role="vcc")],
    )


def test_recommend_components_includes_links_libraries_and_difference():
    catalogue = {
        "ssd1306": _component(
            "ssd1306",
            "SSD1306 OLED",
            "Display",
            "Small I2C OLED display",
            library_ids=["u8g2"],
            buy_links=[{"vendor": "Mouser", "url": "https://example.com/buy"}],
            datasheet_url="https://example.com/ds.pdf",
            thumbnail="https://example.com/ssd1306.jpg",
        ),
        "relay": _component("relay", "Relay", "Actuator", "Switch a load"),
    }

    result = recommend_components(catalogue=catalogue, goal="oled display over i2c")

    assert result[0]["id"] == "ssd1306"
    assert result[0]["library_ids"] == ["u8g2"]
    assert result[0]["buy_links"][0]["url"] == "https://example.com/buy"
    assert result[0]["thumbnail"] == "https://example.com/ssd1306.jpg"
    assert "Display/output" in result[0]["difference"]


def test_render_project_readme_contains_handoff_context():
    readme = render_project_readme(
        project_name="Weather Node",
        board={
            "id": "esp32dev",
            "label": "ESP32 Dev Module",
            "mcu": "esp32",
            "family": "ESP32",
            "frameworks": ["arduino"],
        },
        research_state={
            "summary": "Use ESP32 with OLED display.",
            "selected_components": [{"id": "ssd1306", "name": "SSD1306 OLED"}],
            "decision_notes": "Prefer I2C to save pins.",
        },
        component_context={
            "components": [],
            "libraries": [{"id": "u8g2", "name": "U8g2", "pio_name": "U8g2"}],
            "wires": [],
        },
    )

    assert "# Weather Node" in readme
    assert "ESP32 Dev Module" in readme
    assert "SSD1306 OLED" in readme
    assert ".hardcoreai/research_state.json" in readme
    assert "U8g2: U8g2" in readme


def test_multiple_research_contexts_produce_one_deduplicated_decision():
    first = new_research_context(title="Display")
    first["selected_component_ids"] = ["ssd1306", "esp32"]
    second = new_research_context(title="Connectivity")
    second["selected_component_ids"] = ["esp32", "relay"]

    state = normalize_research_state({"contexts": [first, second]})

    assert state["active_context_id"] == first["id"]
    assert selected_component_ids(state) == ["ssd1306", "esp32", "relay"]
