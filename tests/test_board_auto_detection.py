from pathlib import Path

from backend.boards.detector import detect_from_workspace
from backend.boards.device import Device
from backend.boards.family_map import derive_family_info
from backend.boards.registry import BoardRegistry, registry
from backend.boards.stm32_part import derive_package_pin_count
from backend.boards import stm32_metadata
from backend.api.routers import hal_codegen
from backend.services.hardware import _PLATFORMIO_INI_TEMPLATE


def test_detects_exact_platformio_board(tmp_path: Path):
    (tmp_path / "platformio.ini").write_text(
        "[env:nucleo_f401re]\n"
        "platform = ststm32\n"
        "board = nucleo_f401re\n"
        "framework = stm32cube\n",
        encoding="utf-8",
    )

    candidates = detect_from_workspace(tmp_path)

    assert candidates
    assert candidates[0].board.id == "nucleo_f401re"
    assert candidates[0].confidence == 0.98


def test_detects_cubemx_ioc_mcu_by_family(tmp_path: Path):
    (tmp_path / "firmware.ioc").write_text(
        "Mcu.Name=STM32F446RET6\n",
        encoding="utf-8",
    )

    candidates = detect_from_workspace(tmp_path)

    assert candidates
    assert candidates[0].board.family == "STM32F4"
    assert any(candidate.board.id == "nucleo_f446re" for candidate in candidates)


def test_platformio_template_retains_runtime_board_placeholders():
    ini = _PLATFORMIO_INI_TEMPLATE.format(
        env="nucleo_h743zi",
        board="nucleo_h743zi",
    )

    assert "[env:nucleo_h743zi]" in ini
    assert "board = nucleo_h743zi" in ini


def test_newer_stm32_families_are_classified_for_registry_imports():
    assert derive_family_info("STM32C031C6T6")["family"] == "STM32C0"
    assert derive_family_info("STM32C531RET6")["family"] == "STM32C5"
    assert derive_family_info("STM32U385RGT6")["family"] == "STM32U3"
    assert derive_family_info("STM32WBA52CGU6")["family"] == "STM32WBA"
    assert derive_family_info("STM32WB05KZV6")["family"] == "STM32WB0"
    assert derive_family_info("STM32N657X0H3Q")["family"] == "STM32N6"


def test_stm32_part_number_package_pin_count_is_exposed():
    assert derive_package_pin_count("STM32F401RETx") == 64
    assert derive_package_pin_count("STM32H743ZITx") == 144
    assert derive_package_pin_count("STM32F103C8Tx") == 48

    board = registry.get("nucleo_f401re")

    assert board is not None
    assert board.package_pins == 64
    assert board.pinout_status == "verified"


def test_custom_registry_board_can_target_new_stm32_family(tmp_path: Path, monkeypatch):
    import backend.boards.registry as registry_module

    monkeypatch.setattr(registry_module, "CUSTOM_PATH", tmp_path / "boards_custom.json")
    custom_registry = BoardRegistry()

    board = custom_registry.add_custom(Device(
        id="my_u385_board",
        label="My STM32U385 Board",
        vendor="custom",
        mcu="STM32U385RGT6",
        family="STM32U3",
        core="cortex-m33",
        flash_bytes=1048576,
        ram_bytes=262144,
        f_cpu_hz=96_000_000,
        hal_header="stm32u3xx_hal.h",
        openocd_target="target/stm32u3x.cfg",
    ))

    assert board.package_pins == 64
    assert board.pinout_status == "package_count_only"
    assert custom_registry.get("my_u385_board") is not None


def test_unknown_stm32_custom_family_gets_generic_hal(monkeypatch):
    def fake_get(board_id: str) -> Device:
        return Device(
            id=board_id,
            label="Future STM32 Board",
            vendor="custom",
            mcu="STM32ZZ999RGT6",
            family="STM32ZZ",
            core="cortex-m33",
            flash_bytes=1048576,
            ram_bytes=262144,
            f_cpu_hz=96_000_000,
            hal_header="stm32zz_hal.h",
            openocd_target="target/stm32f4x.cfg",
        )

    monkeypatch.setattr(hal_codegen.registry, "get", fake_get)

    files = hal_codegen.generate_hal_files(
        board="future_board",
        peripherals=[{"id": "gpio"}, {"id": "usart1"}],
    )

    assert "src/hal/main_init.c" in files
    assert "src/hal/gpio_init.c" in files
    assert "src/hal/usart1_init.c" in files


def test_stm32_open_pin_data_imports_pins_af_and_peripherals(tmp_path: Path, monkeypatch):
    source = tmp_path / "STM32_open_pin_data"
    mcu_dir = source / "mcu"
    ip_dir = mcu_dir / "IP"
    ip_dir.mkdir(parents=True)
    (mcu_dir / "STM32F401R(D-E)Tx.xml").write_text("""\
<?xml version="1.0" encoding="UTF-8"?>
<Mcu Family="STM32F4" Line="STM32F401" Package="LQFP64" RefName="STM32F401R(D-E)Tx" xmlns="http://dummy.com">
  <Core>Arm Cortex-M4</Core>
  <Frequency>84</Frequency>
  <Ram>96</Ram>
  <Flash>512</Flash>
  <IP InstanceName="USART2" Name="USART" Version="sci"/>
  <IP InstanceName="SPI1" Name="SPI" Version="spi"/>
  <IP InstanceName="GPIO" Name="GPIO" Version="STM32F401_gpio_v1_0"/>
  <Pin Name="PA2" Position="1" Type="I/O">
    <Signal Name="USART2_TX"/>
    <Signal Name="GPIO" IOModes="Input,Output,Analog,EVENTOUT,EXTI"/>
  </Pin>
  <Pin Name="VSS" Position="2" Type="Power"/>
</Mcu>
""", encoding="utf-8")
    (ip_dir / "GPIO-STM32F401_gpio_v1_0_Modes.xml").write_text("""\
<?xml version="1.0" encoding="UTF-8"?>
<IP Name="GPIO" Version="STM32F401_gpio_v1_0" xmlns="http://dummy.com">
  <GPIO_Pin PortName="PA" Name="PA2">
    <PinSignal Name="USART2_TX">
      <SpecificParameter Name="GPIO_AF">
        <PossibleValue>GPIO_AF7_USART2</PossibleValue>
      </SpecificParameter>
    </PinSignal>
  </GPIO_Pin>
</IP>
""", encoding="utf-8")
    monkeypatch.setattr(stm32_metadata, "METADATA_PATH", tmp_path / "stm32_mcu_metadata.json")

    result = stm32_metadata.build_metadata_cache(source)
    meta = stm32_metadata.get_mcu_metadata("STM32F401RETx")
    validation = stm32_metadata.validate_peripherals("STM32F401RETx", ["usart2", "i2c1"])

    assert result["imported"] == 1
    assert meta is not None
    assert meta["package"] == "LQFP64"
    assert meta["pins"][0]["name"] == "PA2"
    assert meta["pins"][0]["signals"][0]["af"] == "GPIO_AF7_USART2"
    assert validation["metadata_available"] is True
    assert validation["missing"] == ["i2c1"]
