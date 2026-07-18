from schemas import ComponentDefinition, Pin
from services.component_resolution import context_to_markdown, resolve_component_context


def test_resolve_component_context_collects_links_pins_and_libraries():
    catalogue = {
        "ssd1306-oled": ComponentDefinition(
            id="ssd1306-oled",
            name="SSD1306 OLED",
            category="Display",
            description="I2C monochrome OLED display",
            visual_type="module",
            thumbnail="oled",
            width=120,
            height=80,
            library_ids=["u8g2"],
            buy_links=[{"vendor": "Generic", "url": "https://example.com/oled"}],
            datasheet_url="https://example.com/ssd1306.pdf",
            aliases=["oled"],
            pins=[
                Pin(name="VCC", label="VCC", side="left", x=0, y=10, role="vcc"),
                Pin(name="SDA", label="SDA", side="left", x=0, y=20, role="i2c-sda"),
            ],
        ),
        "bluepill": ComponentDefinition(
            id="bluepill",
            name="Blue Pill",
            category="Controller",
            description="STM32F103 board",
            visual_type="board",
            thumbnail="board",
            width=160,
            height=320,
            pins=[
                Pin(name="PB7", label="PB7", side="right", x=100, y=20, role="i2c-sda"),
            ],
        ),
    }
    workbench = {
        "placed_components": [
            {"id": "mcu", "definition_id": "bluepill", "display_name": "MCU"},
            {"id": "display", "definition_id": "ssd1306-oled", "display_name": "OLED"},
        ],
        "wires": [
            {
                "id": "wire-1",
                "from": {"componentId": "mcu", "pinName": "PB7"},
                "to": {"componentId": "display", "pinName": "SDA"},
            }
        ],
    }

    context = resolve_component_context(catalogue=catalogue, workbench=workbench)

    assert context["components"][1]["buy_links"][0]["url"] == "https://example.com/oled"
    assert context["components"][1]["pins"]["SDA"]["role"] == "i2c-sda"
    assert context["libraries"][0]["id"] == "u8g2"
    assert context["wires"][0]["to"]["component"] == "OLED"


def test_component_context_markdown_is_compact_and_actionable():
    markdown = context_to_markdown({
        "components": [
            {
                "display_name": "OLED",
                "definition_id": "ssd1306-oled",
                "description": "I2C display",
                "library_ids": ["u8g2"],
                "datasheet_url": "https://example.com/ds.pdf",
                "buy_links": [{"vendor": "Mouser", "url": "https://example.com/buy"}],
                "pins": {"SDA": {"role": "i2c-sda"}},
            }
        ],
        "libraries": [{"id": "u8g2", "name": "U8g2", "pio_name": "U8g2"}],
        "wires": [],
    })

    assert "SELECTED COMPONENTS" in markdown
    assert "Buy links: Mouser: https://example.com/buy" in markdown
    assert "U8g2: U8g2" in markdown


def test_research_selection_is_merged_without_a_workbench_instance():
    catalogue = {
        "sensor": ComponentDefinition(
            id="sensor",
            name="Research Sensor",
            category="Sensor",
            description="Selected during ideation",
            visual_type="module",
            thumbnail="generic",
            width=100,
            height=80,
            library_ids=["dht-sensor"],
            pins=[Pin(name="DATA", label="DATA", side="left", x=0, y=20, role="gpio")],
        )
    }

    context = resolve_component_context(
        catalogue=catalogue,
        workbench={"placed_components": [], "wires": []},
        selected_component_ids=["sensor"],
    )

    assert context["components"][0]["instance_id"] == "research:sensor"
    assert context["components"][0]["source"] == "research"
    assert context["libraries"][0]["id"] == "dht-sensor"


def test_research_selection_does_not_duplicate_a_placed_component():
    component = ComponentDefinition(
        id="sensor",
        name="Sensor",
        category="Sensor",
        description="Already placed",
        visual_type="module",
        thumbnail="generic",
        width=100,
        height=80,
        pins=[],
    )
    context = resolve_component_context(
        catalogue={"sensor": component},
        workbench={
            "placed_components": [{"id": "42", "definition_id": "sensor"}],
            "wires": [],
        },
        selected_component_ids=["sensor"],
    )

    assert len(context["components"]) == 1
    assert context["components"][0]["source"] == "workbench"
