from schemas import ComponentDefinition, Pin
from services.research import (
    new_research_context,
    normalize_research_state,
    research_chat_messages,
    research_fallback_response,
    recommend_components,
    research_goal_text,
    render_project_readme,
    selected_target_board_id,
    selected_component_ids,
)


def test_research_prompt_is_conversational_during_ideation_and_decisive_later():
    recommendations = [{
        "id": "ssd1306",
        "name": "SSD1306 OLED",
        "difference": "Compare display voltage and I2C pins.",
    }]

    ideation = research_chat_messages(
        idea="I want to build a smartwatch",
        recommendations=recommendations,
        stage="ideation",
    )[0]["content"]
    selection = research_chat_messages(
        idea="Which display should I use?",
        recommendations=recommendations,
        stage="component_selection",
    )[0]["content"]

    assert "natural conversation" in ideation
    assert "Do not output a decision state" in ideation
    assert "component advisor" in selection
    assert "voltage and current" in selection


def test_research_fallback_does_not_repeat_a_clarifying_loop():
    response = research_fallback_response(
        idea="wdym, i thought i was pretty clear",
        recommendations=[],
        history=[
            {"role": "user", "content": "A compact Wi-Fi watch with gesture controls"},
            {"role": "assistant", "content": "What matters most?"},
        ],
        stage="ideation",
    )

    assert "you were clear" in response.casefold()
    assert "good starting point" not in response.casefold()
    assert "component selection" in response.casefold()


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


def test_recommendations_prioritize_discovered_or_ai_named_components():
    catalogue = {
        "relay": _component("relay", "Relay", "Actuator", "Switch a load"),
        "max30102": _component("max30102", "MAX30102", "Sensor", "Heart-rate and SpO2 sensor"),
    }

    result = recommend_components(
        catalogue=catalogue,
        goal="Build a wearable",
        preferred_ids=["max30102"],
    )

    assert result[0]["id"] == "max30102"


def test_research_goal_includes_assistant_part_suggestions():
    context = new_research_context(title="Watch")
    context["messages"] = [
        {"role": "user", "content": "I want health sensing"},
        {"role": "assistant", "content": "Use a MAX30102 optical sensor."},
    ]

    goal = research_goal_text({"contexts": [context]}, "Keep it compact")

    assert "MAX30102" in goal
    assert "Keep it compact" in goal


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


def test_confirmed_esp32_controller_resolves_project_target():
    assert selected_target_board_id([
        {
            "id": "esp32-devkit-v1",
            "name": "ESP32 DevKit V1",
            "category": "Microcontroller",
            "visual_type": "board",
        },
        {"id": "ssd1306-oled", "category": "Display", "visual_type": "display"},
    ]) == "esp32dev"


def test_multiple_controller_cards_do_not_silently_choose_a_target():
    assert selected_target_board_id([
        {"id": "esp32-devkit-v1", "category": "Microcontroller", "visual_type": "board"},
        {"id": "stm32-blue-pill", "category": "Microcontroller", "visual_type": "board"},
    ]) is None
