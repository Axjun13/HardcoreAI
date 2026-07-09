import pytest

from backend.api.routers.hal_codegen import SUPPORTED_FAMILIES, generate_hal_files
from backend.boards.registry import registry


def get_board_for_family(family: str) -> str:
    for device in registry.list():
        if device.family == family:
            return device.id
    raise AssertionError(f"No registered board for STM32 family {family}")


@pytest.mark.parametrize("family", sorted(SUPPORTED_FAMILIES))
def test_all_supported_stm32_families_have_registered_boards(family):
    assert any(device.family == family for device in registry.list())


@pytest.mark.parametrize("family", sorted(SUPPORTED_FAMILIES))
def test_hal_generation_works_for_each_supported_stm32_family(family):
    board_id = get_board_for_family(family)
    files = generate_hal_files(board=board_id, peripherals=[{"id": "gpio"}])

    assert "src/hal/main_init.c" in files
    assert "src/hal/gpio_init.c" in files
