import pytest

from backend.api.routers.board_context import _FAMILY_NOTES, build_board_context
from backend.api.routers import hal_codegen
from backend.boards.device import Device
from backend.api.routers.hal_codegen import (
    FAMILY_TEMPLATES,
    INIT_CALLS,
    INCLUDES,
    generate_hal_files,
)
from backend.boards.registry import registry


SUPPORTED_FAMILIES = [
    "STM32F0",
    "STM32F1",
    "STM32F2",
    "STM32F3",
    "STM32F4",
    "STM32F7",
    "STM32G0",
    "STM32G4",
    "STM32H5",
    "STM32H7",
    "STM32L0",
    "STM32L1",
    "STM32L4",
    "STM32L5",
    "STM32U5",
    "STM32WB",
    "STM32WL",
]


# ---------------------------------------------------------------------
# FAMILY COVERAGE
# ---------------------------------------------------------------------

@pytest.mark.parametrize("family", SUPPORTED_FAMILIES)
def test_family_has_templates(family):
    assert family in FAMILY_TEMPLATES


@pytest.mark.parametrize("family", SUPPORTED_FAMILIES)
def test_family_has_board_notes(family):
    assert family in _FAMILY_NOTES


@pytest.mark.parametrize("family", SUPPORTED_FAMILIES)
def test_family_has_registered_board(family):
    assert any(
        board.family == family
        for board in registry.list()
    )


def get_board_for_family(family: str) -> str:
    for device in registry.list():
        if device.family == family:
            return device.id
    raise AssertionError(f"No board registered for STM32 family {family}")


@pytest.mark.parametrize("board_id", ["bluepill_f103c8", "nucleo_f446re", "disco_f746ng"])
def test_seeded_board_has_full_pinout_and_board_context(board_id):
    device = registry.get(board_id)
    assert device is not None
    assert device.full_pinout is not None
    assert len(device.full_pinout) > 0

    context = build_board_context(device)
    assert "Pinout: full board pinout available" in context
    assert "Board id (use exactly this string when calling generate_hal)" in context


@pytest.mark.parametrize("board_id", ["nucleo_f401re", "nucleo_f411re"])
def test_additional_common_nucleo_boards_have_registry_and_pinout(board_id):
    device = registry.get(board_id)
    assert device is not None
    assert device.family in {"STM32F4"}
    assert device.full_pinout is not None
    assert len(device.full_pinout) > 0


# ---------------------------------------------------------------------
# PERIPHERAL COVERAGE
# ---------------------------------------------------------------------

REQUIRED_PERIPHERALS = [
    "gpio",
    "usart1",
    "spi1",
    "i2c1",
    "adc1",
]


@pytest.mark.parametrize("family", SUPPORTED_FAMILIES)
@pytest.mark.parametrize("peripheral", REQUIRED_PERIPHERALS)
def test_family_supports_required_peripherals(family, peripheral):
    assert peripheral in FAMILY_TEMPLATES[family]


@pytest.mark.parametrize("peripheral", REQUIRED_PERIPHERALS)
def test_init_call_exists(peripheral):
    assert peripheral in INIT_CALLS


@pytest.mark.parametrize("peripheral", REQUIRED_PERIPHERALS)
def test_include_exists(peripheral):
    assert peripheral in INCLUDES

def test_unknown_stm32_family_uses_generic_templates(monkeypatch):
    def fake_get(board_id: str) -> Device:
        return Device(
            id=board_id,
            label="STM32XX Generic Board",
            vendor="st",
            mcu="STM32XX",
            family="STM32XX",
            core="cortex-m0",
            flash_bytes=65536,
            ram_bytes=8192,
            f_cpu_hz=48_000_000,
            hal_header="stm32xx_hal.h",
            openocd_target="target/stm32f1x.cfg",
            openocd_interface="interface/stlink.cfg",
        )

    monkeypatch.setattr(hal_codegen.registry, "get", fake_get)
    files = hal_codegen.generate_hal_files(
        board="generic_board",
        peripherals=[{"id": "gpio"}, {"id": "usart1"}],
    )

    assert "src/hal/main_init.c" in files
    assert "src/hal/gpio_init.c" in files
    assert "src/hal/usart1_init.c" in files


@pytest.mark.parametrize("family", SUPPORTED_FAMILIES)
def test_gpio_project_generates(family):

    files = generate_hal_files(
        board=get_board_for_family(family),
        peripherals=[
            {
                "id": "gpio",
                "label": "GPIO"
            }
        ],
    )

    assert "src/hal/main_init.c" in files
    assert "src/hal/gpio_init.c" in files

@pytest.mark.parametrize("family", SUPPORTED_FAMILIES)
def test_uart_project_generates(family):

    files = generate_hal_files(
        board=get_board_for_family(family),
        peripherals=[
            {"id": "gpio"},
            {"id": "usart1"},
        ],
    )

    assert "src/hal/usart1_init.c" in files

@pytest.mark.parametrize("family", SUPPORTED_FAMILIES)
def test_adc_project_generates(family):

    files = generate_hal_files(
        board=get_board_for_family(family),
        peripherals=[
            {"id": "gpio"},
            {"id": "adc1"},
        ],
    )

    assert "src/hal/adc1_init.c" in files