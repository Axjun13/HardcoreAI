import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from boards.catalog import load_catalog, validate_catalog
from api.routers.boards import list_boards, search_boards
from services.hardware import platformio_ini_for_board


def test_priority_catalog_is_valid_and_has_priority_vendor_coverage():
    assert validate_catalog() == []
    boards = load_catalog().values()
    manufacturers = {board.manufacturer for board in boards}
    assert {"Renesas", "Microchip", "Texas Instruments", "Arduino", "Espressif"} <= manufacturers


def test_board_api_filters_and_search_catalog_data():
    assert any(board["id"] == "renesas-ek-ra6m5" for board in list_boards(manufacturer="Renesas"))
    assert any(board["id"] == "ti-lp-mspm0g3507" for board in list_boards(family="MSPM0"))
    assert any(board["id"] == "esp32-c6-devkitc-1" for board in search_boards("C6"))


def test_platformio_ti_alias_is_normalized_for_manufacturer_filter():
    assert any(board["id"] == "lpmsp430g2553" for board in list_boards(manufacturer="Texas Instruments"))


def test_catalog_platformio_mapping_uses_catalog_board_id():
    ini = platformio_ini_for_board("arduino-nano-every")
    assert "platform = atmelmegaavr" in ini
    assert "board = nano_every" in ini
