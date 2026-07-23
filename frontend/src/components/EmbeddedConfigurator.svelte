<script lang="ts">
  import { workspaceStore, actions, type PinConfig } from "../store";
  import { authenticatedFetch } from "../auth";
  import "./EmbeddedConfigurator.css";
  import {
    X,
    Search,
    ChevronRight,
    ChevronDown,
    RotateCcw,
    ExternalLink,
    Cpu,
    Zap,
    Clock,
    Wifi,
    Activity,
    FileCode,
    AlertTriangle,
    CheckCircle,
  } from "lucide-svelte";

  export let selectedBoard: string;
  export let onClose: () => void;
  export let isDetached: boolean;
  export let onDetach: () => void;
  export let onFilesGenerated: (
    files: { path: string; content: string }[],
  ) => void = () => {};

  const TABS = ["Pinout", "Clock", "Configuration", "Project"] as const;
  let activeTab: "Pinout" | "Clock" | "Configuration" | "Project" =
    "Configuration";
  let expandedCategories = new Set<string>(["system-core"]);
  let selectedPeripheral = "gpio";
  let searchQuery = "";

  // Interactive Pin Configuration State
  let editingPin: PinConfig | null = null;
  let pinLabel = "";
  let pinMode = "Alternate Function";
  let pinPull = "No pull-up/down";
  let pinSpeed = "High";
  let pinSignal = "";
  let pinAf = "";
  let pinEnabled = false;

  // Every full_pinout table in the backend (boards/pinout.py) is an LQFP
  // package today — keep this in sync if a QFN/BGA/UFQFPN table is ever
  // added there, since the count-to-name mapping stops being safe then.
  const LQFP_PACKAGE_NAMES: Record<number, string> = {
    48: "LQFP48",
    64: "LQFP64",
    144: "LQFP144",
  };

  const BOARD_SPECS: Record<
    string,
    {
      flash: string;
      ram: string;
      speed: string;
      core: string;
      pins: number;
      package: string;
    }
  > = {
    STM32F103: {
      flash: "64 KB",
      ram: "20 KB",
      speed: "72 MHz",
      core: "Cortex-M3",
      pins: 48,
      package: "LQFP48",
    },
  };

  const CATEGORIES = [
    {
      id: "system-core",
      label: "System Core",
      icon: Cpu,
      children: [
        { id: "rcc", label: "RCC", description: "Reset and Clock Control" },
        { id: "gpio", label: "GPIO", description: "General Purpose I/O" },
        {
          id: "nvic",
          label: "NVIC",
          description: "Nested Vectored Interrupt Controller",
        },
        { id: "sys", label: "SYS", description: "System Configuration" },
        { id: "dma", label: "DMA", description: "Direct Memory Access" },
      ],
    },
    {
      id: "analog",
      label: "Analog",
      icon: Activity,
      children: [
        {
          id: "adc1",
          label: "ADC1",
          description: "Analog-to-Digital Converter 1",
        },
        {
          id: "adc2",
          label: "ADC2",
          description: "Analog-to-Digital Converter 2",
        },
        { id: "dac", label: "DAC", description: "Digital-to-Analog Converter" },
        { id: "comp", label: "COMP", description: "Analog Comparator" },
      ],
    },
    {
      id: "timers",
      label: "Timers",
      icon: Clock,
      children: [
        {
          id: "tim1",
          label: "TIM1",
          description: "Advanced Timer 1 (PWM, Encoder)",
        },
        { id: "tim2", label: "TIM2", description: "General Purpose Timer 2" },
        { id: "tim3", label: "TIM3", description: "General Purpose Timer 3" },
        { id: "tim4", label: "TIM4", description: "General Purpose Timer 4" },
        { id: "tim5", label: "TIM5", description: "General Purpose Timer 5" },
        { id: "tim9", label: "TIM9", description: "General Purpose Timer 9" },
        {
          id: "systick",
          label: "SysTick",
          description: "System Tick Timer (HAL)",
        },
      ],
    },
    {
      id: "connectivity",
      label: "Connectivity",
      icon: Wifi,
      children: [
        {
          id: "usart1",
          label: "USART1",
          description: "Universal Sync/Async Receiver Transmitter 1",
        },
        {
          id: "usart2",
          label: "USART2",
          description: "Universal Sync/Async Receiver Transmitter 2",
        },
        {
          id: "usart6",
          label: "USART6",
          description: "Universal Sync/Async Receiver Transmitter 6",
        },
        {
          id: "spi1",
          label: "SPI1",
          description: "Serial Peripheral Interface 1",
        },
        {
          id: "spi2",
          label: "SPI2",
          description: "Serial Peripheral Interface 2",
        },
        {
          id: "i2c1",
          label: "I2C1",
          description: "Inter-Integrated Circuit 1",
        },
        {
          id: "i2c2",
          label: "I2C2",
          description: "Inter-Integrated Circuit 2",
        },
        {
          id: "usb",
          label: "USB OTG FS",
          description: "USB On-The-Go Full Speed",
        },
        {
          id: "sdio",
          label: "SDIO",
          description: "Secure Digital I/O Interface",
        },
      ],
    },
    {
      id: "middleware",
      label: "Middleware",
      icon: FileCode,
      children: [
        {
          id: "freertos",
          label: "FreeRTOS",
          description: "Real-Time Operating System",
        },
        { id: "fatfs", label: "FatFS", description: "FAT File System" },
        { id: "lwip", label: "LwIP", description: "Lightweight IP Stack" },
      ],
    },
  ];

  let peripheralConfigs: Record<string, any> = {
    gpio: {
      name: "GPIO",
      enabled: true,
      mode: "Output Push Pull",
      speed: "High",
      pullResistor: "No pull-up/down",
    },
    usart1: {
      name: "USART1",
      enabled: false,
      mode: "Asynchronous",
      params: {
        BaudRate: "115200",
        WordLength: "8 Bits",
        StopBits: "1",
        Parity: "None",
      },
    },
    usart2: {
      name: "USART2",
      enabled: true,
      mode: "Asynchronous",
      params: {
        BaudRate: "115200",
        WordLength: "8 Bits",
        StopBits: "1",
        Parity: "None",
      },
    },
    spi1: {
      name: "SPI1",
      enabled: true,
      mode: "Full-Duplex Master",
      params: {
        Prescaler: "2",
        CPOL: "Low",
        CPHA: "1 Edge",
        DataSize: "8 Bits",
      },
    },
    i2c1: {
      name: "I2C1",
      enabled: true,
      mode: "I2C",
      params: {
        SpeedMode: "Standard (100 kHz)",
        OwnAddress: "0x00",
        DualAddress: "Disabled",
      },
    },
    tim1: {
      name: "TIM1",
      enabled: false,
      mode: "PWM Generation",
      params: {
        Prescaler: "83",
        CounterPeriod: "999",
        ClockDivision: "No Division",
      },
    },
    tim2: {
      name: "TIM2",
      enabled: false,
      mode: "Up Counter",
      params: { Prescaler: "83", CounterPeriod: "999" },
    },
    adc1: {
      name: "ADC1",
      enabled: false,
      mode: "Independent Mode",
      params: {
        Resolution: "12 bits",
        DataAlignment: "Right",
        Channels: "IN0",
      },
    },
    rcc: {
      name: "RCC",
      enabled: true,
      mode: "Crystal/Ceramic Resonator",
      params: { HSE: "8 MHz", LSE: "32.768 kHz", SYSCLK: "72 MHz" },
    },
  };

  function formatByteSize(bytes: number | undefined | null) {
    if (typeof bytes !== "number" || !Number.isFinite(bytes) || bytes <= 0) {
      return "N/A";
    }
    const kb = bytes / 1024;
    if (kb >= 1024) {
      return `${(kb / 1024).toFixed(1)} MB`;
    }
    return `${Math.round(kb)} KB`;
  }

  $: boardMeta = $workspaceStore.selectedBoardInfo;
  $: specs = {
    flash: boardMeta?.flash_bytes
      ? formatByteSize(boardMeta.flash_bytes)
      : (BOARD_SPECS[selectedBoard]?.flash ?? BOARD_SPECS["STM32F103"].flash),
    ram: boardMeta?.ram_bytes
      ? formatByteSize(boardMeta.ram_bytes)
      : (BOARD_SPECS[selectedBoard]?.ram ?? BOARD_SPECS["STM32F103"].ram),
    speed: boardMeta?.f_cpu_hz
      ? `${Math.round(boardMeta.f_cpu_hz / 1_000_000)} MHz`
      : (BOARD_SPECS[selectedBoard]?.speed ?? BOARD_SPECS["STM32F103"].speed),
    core:
      boardMeta?.core ??
      BOARD_SPECS[selectedBoard]?.core ??
      BOARD_SPECS["STM32F103"].core,
    pins:
      boardMeta?.full_pinout?.length ??
      boardMeta?.package_pins ??
      BOARD_SPECS[selectedBoard]?.pins ??
      BOARD_SPECS["STM32F103"].pins,
    package: boardMeta?.full_pinout?.length
      ? (LQFP_PACKAGE_NAMES[boardMeta.full_pinout.length] ??
        `${boardMeta.full_pinout.length}-pin`)
      : (BOARD_SPECS[selectedBoard]?.package ??
        BOARD_SPECS["STM32F103"].package),
  };
  $: boardDisplayLabel = boardMeta?.label || selectedBoard || "Selected board";
  $: boardModel = boardMeta?.mcu || selectedBoard || "STM32";
  // Historically this only ever distinguished AVR from "everything else",
  // which silently mislabeled ESP32/ESP8266 (arch "xtensa") and SAMD (arch
  // "arm-samd") boards with STM32-only fields (STM32Cube HAL version, a
  // .ld linker file, arm-none-eabi-gcc as the toolchain) even though those
  // boards are actually flashed via esptool/bossac and built with the
  // Arduino framework (see ARDUINO_FRAMEWORK_ARCHES in boards/device.py on
  // the backend). Kept as a boolean for the AVR-specific bootloader string
  // below, but every other branch now keys off `archKind` so each arch
  // shows its own real toolchain/upload method instead of falling into the
  // STM32 branch by default.
  $: archKind = boardMeta?.arch ?? "arm-stm32";
  $: boardFrameworks = boardMeta?.frameworks ?? [];
  $: isArduinoFramework =
    boardFrameworks.includes("arduino") &&
    (archKind === "avr" ||
      archKind === "xtensa" ||
      archKind === "arm-samd" ||
      archKind === "arduino-generic");
  $: isEspIdfFramework =
    archKind === "xtensa" && boardFrameworks.includes("espidf");
  $: projectName = `blinky-${(selectedBoard || "board").replace(/[^a-z0-9]+/gi, "-").toLowerCase()}`;
  $: linkerFile = `${boardModel.replace(/[^a-zA-Z0-9]+/g, "") || "STM32"}_FLASH.ld`;
  $: halVersion = boardMeta?.family
    ? `STM32Cube ${boardMeta.family.replace("STM32", "")}`
    : "STM32Cube F1";

  // Per-arch project metadata for the Project tab. STM32 keeps its existing
  // row list (HAL version/linker file/heap+stack are genuinely per-board
  // there); the other three architectures all build through the Arduino
  // framework, but their toolchain/upload/core details differ from each
  // other and from STM32, not just from AVR.
  $: archProjectRows = isEspIdfFramework
    ? [
        {
          label: "Target Framework",
          value: "ESP-IDF via PlatformIO",
        },
        {
          label: "Target Toolchain compiler",
          value:
            boardMeta?.core === "riscv32"
              ? "riscv32-esp-elf-gcc"
              : "xtensa-esp32-elf-gcc",
        },
        {
          label: "Upload method",
          value: "esptool serial bootloader",
        },
        {
          label: "Entrypoint",
          value: "app_main()",
        },
        {
          label: "Runtime",
          value: "FreeRTOS + ESP-IDF drivers",
        },
      ]
    : archKind === "avr"
      ? [
          { label: "Target Toolchain compiler", value: "avr-gcc" },
          {
            label: "Upload method",
            value: `avrdude (${boardMeta?.avrdude_programmer ?? "arduino"} bootloader)`,
          },
          {
            label: "Processor Heap Limit",
            value: "n/a — AVR has no MMU/heap config",
          },
          {
            label: "Processor Stack Limit",
            value: "n/a — shares SRAM with heap",
          },
          {
            label: "Arduino Core Version",
            value: "arduino-avr-core (via PlatformIO)",
          },
        ]
      : archKind === "xtensa"
        ? [
            {
              label: "Target Toolchain compiler",
              value:
                "xtensa-esp32-elf-gcc (or riscv32-esp-elf-gcc on C-series)",
            },
            {
              label: "Upload method",
              value: "esptool (serial bootloader sync)",
            },
            {
              label: "Processor Heap Limit",
              value: "Dynamic FreeRTOS heap — no fixed limit set here",
            },
            {
              label: "Processor Stack Limit",
              value: "Per-task stack, sized by Arduino core defaults",
            },
            {
              label: "Arduino Core Version",
              value: "arduino-esp32 core (via PlatformIO)",
            },
          ]
        : archKind === "arm-samd"
          ? [
              {
                label: "Target Toolchain compiler",
                value: "arm-none-eabi-gcc",
              },
              {
                label: "Upload method",
                value: "bossac (SAM-BA/UF2 bootloader, 1200bps touch-reset)",
              },
              {
                label: "Processor Heap Limit",
                value: "n/a — shares SRAM with heap, Arduino core default",
              },
              {
                label: "Processor Stack Limit",
                value: "n/a — shares SRAM with heap",
              },
              {
                label: "Arduino Core Version",
                value: "arduino-samd-core (via PlatformIO)",
              },
            ]
          : archKind === "arduino-generic"
            ? [
                {
                  label: "Target Framework",
                  value: `Arduino via PlatformIO ${boardMeta?.pio_platform ?? "platform"}`,
                },
                {
                  label: "Upload method",
                  value:
                    boardMeta?.upload_protocol ?? "PlatformIO board default",
                },
                {
                  label: "Processor Heap Limit",
                  value: "Board/core default",
                },
                {
                  label: "Processor Stack Limit",
                  value: "Board/core default",
                },
                {
                  label: "Arduino Core Version",
                  value: "Resolved by selected PlatformIO platform",
                },
              ]
            : [
                {
                  label: "Target Toolchain compiler",
                  value: "arm-none-eabi-gcc",
                },
                { label: "Microcontroller Linker File", value: linkerFile },
                { label: "Processor Heap Limit", value: "0x200" },
                { label: "Processor Stack Limit", value: "0x400" },
                {
                  label: "STM32Cube HAL Version",
                  value: `${halVersion} v1.8.6`,
                },
              ];

  // Oscillator + PLL setup used by each family's SystemClock_Config()
  // template in hal_codegen.py. Mirrors the backend's per-family choices so
  // this tab is accurate for any of the 15 supported STM32 families, not
  // just the original F103 board.
  const FAMILY_CLOCK: Record<string, { source: string; pll: string }> = {
    STM32F0: {
      source: "HSI48 (internal, 48 MHz)",
      pll: "Direct — HSI48 used as SYSCLK",
    },
    STM32F1: { source: "HSE (8 MHz)", pll: "PLL ×9 (PLLMUL9)" },
    STM32F2: {
      source: "HSE (8 MHz, bypass via ST-LINK MCO)",
      pll: "PLLM=8, PLLN=240, PLLP=2",
    },
    STM32F3: { source: "HSE (8 MHz)", pll: "PLL ×9 (PLLMUL9)" },
    STM32F4: {
      source: "HSE (8 MHz)",
      pll: "PLLM=4, PLLN, PLLP=2 (board-specific N)",
    },
    STM32F7: { source: "HSE (8 MHz)", pll: "PLLM=4, PLLN=216, PLLP=2" },
    STM32G0: { source: "HSI16 (internal, 16 MHz)", pll: "PLLM÷1, PLLN=8" },
    STM32G4: {
      source: "HSI16 (internal, 16 MHz)",
      pll: "PLLM÷4, PLLN=85, PLLR÷2",
    },
    STM32H5: { source: "HSE (8 MHz, bypass)", pll: "PLLM=4, PLLN=250, PLLP=2" },
    STM32H7: { source: "HSI (internal, 64 MHz)", pll: "PLL1, HSI-fed" },
    STM32L0: { source: "HSI16 (internal, 16 MHz)", pll: "PLLMUL×4 / PLLDIV÷2" },
    STM32L1: { source: "HSI16 (internal, 16 MHz)", pll: "PLLMUL×4 / PLLDIV÷2" },
    STM32L4: { source: "MSI (4 MHz)", pll: "PLLM÷1, PLLN=40, PLLR÷2" },
    STM32L5: { source: "MSI (4 MHz)", pll: "PLLM÷1, PLLN=55, PLLR÷2" },
    STM32U5: { source: "MSIS (4 MHz)", pll: "PLLM÷1, PLLN=80, PLLR÷2" },
    STM32WB: {
      source: "MSI (4 MHz)",
      pll: "PLLM÷1, PLLN=32, PLLR÷2 (CPU1/M4)",
    },
    STM32WL: { source: "MSI (4 MHz)", pll: "PLL-derived SYSCLK" },
  };
  $: familyClock = FAMILY_CLOCK[boardMeta?.family ?? ""] ?? {
    source: "HSE (8 MHz)",
    pll: "PLL (family-specific — see generated code)",
  };
  $: clockTreeRows = [
    {
      src: familyClock.source,
      arrow: "→",
      node: familyClock.pll,
      result: `SYSCLK ${specs.speed}`,
    },
    {
      src: "SYSCLK",
      arrow: "→",
      node: "AHB / APB prescalers",
      result: `${specs.speed} domain`,
    },
  ];
  $: clockSourceRows = [
    { label: "Oscillator Source", value: familyClock.source },
    { label: "PLL Configuration", value: familyClock.pll },
    { label: "System Clock Speed", value: specs.speed },
  ];

  function toggleCategory(id: string) {
    if (expandedCategories.has(id)) {
      expandedCategories.delete(id);
    } else {
      expandedCategories.add(id);
    }
    expandedCategories = new Set(expandedCategories);
  }

  function togglePeripheral(id: string) {
    peripheralConfigs[id].enabled = !peripheralConfigs[id].enabled;
    peripheralConfigs = { ...peripheralConfigs };
  }

  function updateParam(id: string, key: string, value: string) {
    const curr = peripheralConfigs[id];
    if (key === "mode") curr.mode = value;
    else if (key === "speed") curr.speed = value;
    else if (key === "pullResistor") curr.pullResistor = value;
    else {
      if (!curr.params) curr.params = {};
      curr.params[key] = value;
    }
    peripheralConfigs = { ...peripheralConfigs };
  }

  function signalsForPin(pinName: string) {
    const meta = boardMeta?.pin_metadata?.find(
      (pin: any) => pin.name === pinName,
    );
    const signals =
      meta?.signals
        ?.map((signal: any) => ({ name: signal.name, af: signal.af ?? "-" }))
        ?.filter((signal: any) => signal.name && signal.name !== "GPIO") ?? [];
    return signals.length
      ? signals
      : [
          { name: "SPI1_SCK", af: "AF5" },
          { name: "SPI1_MISO", af: "AF5" },
          { name: "SPI1_MOSI", af: "AF5" },
          { name: "USART2_TX", af: "AF7" },
          { name: "USART2_RX", af: "AF7" },
          { name: "I2C1_SCL", af: "AF4" },
          { name: "I2C1_SDA", af: "AF4" },
        ];
  }

  // Interactive Pin Editor
  function openPinEditor(pin: PinConfig) {
    editingPin = pin;
    pinLabel = pin.label;
    pinMode = pin.mode;
    pinPull = pin.pull;
    pinSpeed = pin.speed;
    pinSignal = pin.signal;
    pinAf = pin.af;
    pinEnabled = pin.enabled;
  }

  function savePinConfig() {
    if (!editingPin) return;

    // Auto alternate function detection
    let af = pinAf;
    if (pinMode === "Alternate Function" && !af) {
      af =
        signalsForPin(editingPin.pin).find(
          (signal: any) => signal.name === pinSignal,
        )?.af ?? "-";
    }

    actions.updatePinConfig(editingPin.pin, {
      label: pinLabel,
      mode: pinMode,
      pull: pinPull,
      speed: pinSpeed,
      signal:
        pinSignal === "Unassigned" && pinMode !== "Input Floating"
          ? editingPin.pin + "_PIN"
          : pinSignal,
      af: pinMode === "Alternate Function" ? af : "-",
      enabled: pinEnabled,
    });

    // Also toggle peripheral state based on pinout change
    if (pinSignal.startsWith("SPI1") && pinEnabled) {
      peripheralConfigs.spi1.enabled = true;
    } else if (pinSignal.startsWith("USART2") && pinEnabled) {
      peripheralConfigs.usart2.enabled = true;
    } else if (pinSignal.startsWith("I2C1") && pinEnabled) {
      peripheralConfigs.i2c1.enabled = true;
    }
    peripheralConfigs = { ...peripheralConfigs };

    const pinName = editingPin?.pin || "";
    editingPin = null;
    actions.addBuildLog(
      `Reconfigured microcontroller PIN: ${pinName} -> ${pinSignal} (${pinMode})`,
    );
  }

  // Get color for pin state
  function getPinColor(pin: PinConfig) {
    if (!pin.enabled) return "var(--text-dark)";
    if (pin.mode.includes("Alternate")) return "var(--accent-violet)";
    if (pin.mode.includes("Analog")) return "var(--accent-cyan)";
    if (pin.mode.includes("Output")) return "var(--accent-success)";
    return "var(--accent-success-hover)";
  }

  $: filteredCategories = CATEGORIES.map((cat) => ({
    ...cat,
    children: searchQuery
      ? cat.children.filter(
          (c) =>
            c.label.toLowerCase().includes(searchQuery.toLowerCase()) ||
            c.description.toLowerCase().includes(searchQuery.toLowerCase()),
        )
      : cat.children,
  })).filter((cat) => !searchQuery || cat.children.length > 0);

  $: selectedConfig = peripheralConfigs[selectedPeripheral] ?? {
    name: selectedPeripheral.toUpperCase(),
    enabled: false,
  };
  // No 64-pin cap — LQFP144 boards (H5/F2/H7/L5/U5 Nucleo-144s) need all
  // their pins to show up, not just the first quarter of them. Sides are
  // split into even quarters at whatever the real pin count is; order
  // matches the physical top -> right -> bottom -> left walk the layout
  // below expects.
  $: chipPins = $workspaceStore.pins;
  $: chipPinsPerSide = Math.max(1, Math.ceil(chipPins.length / 4));
  $: chipPinsTop = chipPins.slice(0, chipPinsPerSide);
  $: chipPinsRight = chipPins.slice(chipPinsPerSide, chipPinsPerSide * 2);
  $: chipPinsBottom = chipPins.slice(chipPinsPerSide * 2, chipPinsPerSide * 3);
  $: chipPinsLeft = chipPins.slice(chipPinsPerSide * 3, chipPinsPerSide * 4);

  function makeFieldId(label: string, suffix = "field") {
    return `ec-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-${suffix}`;
  }

  // ── HAL Generation ────────────────────────────────────────────
  let isGenerating = false;
  let generateError: string | null = null;
  let generateSuccess = false;
  let generatedFileCount = 0;

  async function generateHALCode() {
    const enabledPeripherals = Object.entries(peripheralConfigs)
      .filter(([, cfg]) => cfg.enabled)
      .map(([id, cfg]) => ({
        id,
        label: cfg.name,
        mode: cfg.mode ?? "",
        params: cfg.params ?? {},
      }));

    if (enabledPeripherals.length === 0) {
      generateError = "Enable at least one peripheral before generating.";
      return;
    }

    const projectId = $workspaceStore.activeProjectId;
    if (!projectId) {
      generateError = "No active project. Open or create a project first.";
      return;
    }

    isGenerating = true;
    generateError = null;
    generateSuccess = false;

    try {
      const res = await authenticatedFetch("/api/generate-hal", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          project_id: projectId,
          board: selectedBoard,
          peripherals: enabledPeripherals,
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail ?? `Server error ${res.status}`);
      }

      const data: { files: { path: string; content: string }[] } =
        await res.json();

      if (!data.files?.length) {
        throw new Error("Backend returned no files — check server logs.");
      }

      generatedFileCount = data.files.length;
      generateSuccess = true;

      actions.addBuildLog(
        `[HAL] Generated ${data.files.length} file(s) for ${selectedBoard} ` +
          `(${enabledPeripherals.map((p) => p.id).join(", ")})`,
      );

      onFilesGenerated(data.files);
    } catch (e: any) {
      generateError = e.message ?? "Unknown error during HAL generation.";
      actions.addBuildLog(`[HAL] Generation failed: ${generateError}`);
    } finally {
      isGenerating = false;
    }
  }
</script>

<div class="ec-root">
  <!-- Header -->
  <div class="ec-header">
    <div class="ec-header-left">
      <Cpu size={13} style="color: var(--accent-violet);" />
      <span class="ec-header-title">Embedded Configurator</span>
      <span class="ec-board-chip">{boardDisplayLabel}</span>
    </div>
    <div class="ec-header-actions">
      <button
        class="ec-icon-btn"
        onclick={onDetach}
        title={isDetached ? "Dock panel" : "Detach panel"}
      >
        {#if isDetached}
          <Zap size={12} />
        {:else}
          <ExternalLink size={12} />
        {/if}
      </button>
      <button class="ec-icon-btn" title="Reset configuration">
        <RotateCcw size={12} />
      </button>
      <button class="ec-icon-btn ec-close-btn" onclick={onClose} title="Close">
        <X size={13} />
      </button>
    </div>
  </div>

  <!-- Tab Bar -->
  <div class="ec-tab-bar">
    {#each TABS as tab}
      <button
        class="ec-tab {activeTab === tab ? 'ec-tab-active' : ''}"
        onclick={() => (activeTab = tab)}
      >
        {tab}
      </button>
    {/each}
  </div>

  <!-- ── PINOUT TAB ── -->
  {#if activeTab === "Pinout"}
    <div class="ec-content ec-pinout-tab">
      {#if $workspaceStore.pins.length === 0}
        <div class="ec-pinout-unavailable">
          <AlertTriangle size={28} />
          <div class="ec-pinout-unavailable-title">
            {#if boardMeta?.package_pins}
              {boardMeta.package_pins}-pin package detected for {boardDisplayLabel}
            {:else}
              Pinout not verified for {boardDisplayLabel}
            {/if}
          </div>
          <p>
            We haven't hand-verified a physical pin map for this specific board
            yet, so we're not showing one rather than guessing wrong. Peripheral
            config below and HAL/clock generation still work normally — only the
            pin diagram is affected.
          </p>
        </div>
      {:else}
        <div class="ec-pinout-visual">
          <!-- Interactive Chip Map -->
          <div class="ec-chip-wrapper">
            <div
              class="ec-chip"
              style="--pin-side-count: {chipPinsPerSide}; --chip-size: {chipPinsPerSide >
              20
                ? '176px'
                : chipPinsPerSide > 12
                  ? '140px'
                  : '112px'}"
            >
              <div class="ec-chip-notch"></div>

              <!-- Top pins -->
              <div class="ec-chip-pins ec-pins-top">
                {#each chipPinsTop as pin}
                  <button
                    type="button"
                    class="ec-pin ec-pin-metal {pin.enabled
                      ? 'active-pin'
                      : ''}"
                    style="--pin-color: {getPinColor(pin)}"
                    onclick={() => openPinEditor(pin)}
                    aria-label="Configure {pin.pin}"
                    title="{pin.pin}: {pin.signal} ({pin.label})"
                  ></button>
                {/each}
              </div>

              <!-- Bottom pins -->
              <div class="ec-chip-pins ec-pins-bottom">
                {#each chipPinsBottom as pin}
                  <button
                    type="button"
                    class="ec-pin ec-pin-metal {pin.enabled
                      ? 'active-pin'
                      : ''}"
                    style="--pin-color: {getPinColor(pin)}"
                    onclick={() => openPinEditor(pin)}
                    aria-label="Configure {pin.pin}"
                    title="{pin.pin}: {pin.signal} ({pin.label})"
                  ></button>
                {/each}
              </div>

              <!-- Left pins -->
              <div class="ec-chip-pins ec-pins-left">
                {#each chipPinsLeft as pin}
                  <button
                    type="button"
                    class="ec-pin ec-pin-metal ec-pin-h {pin.enabled
                      ? 'active-pin'
                      : ''}"
                    style="--pin-color: {getPinColor(pin)}"
                    onclick={() => openPinEditor(pin)}
                    aria-label="Configure {pin.pin}"
                    title="{pin.pin}: {pin.signal} ({pin.label})"
                  ></button>
                {/each}
              </div>

              <!-- Right pins -->
              <div class="ec-chip-pins ec-pins-right">
                {#each chipPinsRight as pin}
                  <button
                    type="button"
                    class="ec-pin ec-pin-metal ec-pin-h {pin.enabled
                      ? 'active-pin'
                      : ''}"
                    style="--pin-color: {getPinColor(pin)}"
                    onclick={() => openPinEditor(pin)}
                    aria-label="Configure {pin.pin}"
                    title="{pin.pin}: {pin.signal} ({pin.label})"
                  ></button>
                {/each}
              </div>

              <div class="ec-chip-body">
                <div class="ec-brand">ST</div>
                <div class="ec-model">{boardModel}</div>
                <div class="ec-package">{specs.package}</div>
              </div>
            </div>
          </div>

          <div class="ec-pinout-legend">
            <div class="ec-legend-item">
              <span
                class="ec-legend-dot"
                style="background: var(--accent-violet);"
              ></span>Alternate
            </div>
            <div class="ec-legend-item">
              <span
                class="ec-legend-dot"
                style="background: var(--accent-cyan);"
              ></span>Analog
            </div>
            <div class="ec-legend-item">
              <span
                class="ec-legend-dot"
                style="background: var(--accent-success);"
              ></span>Output
            </div>
            <div class="ec-legend-item">
              <span class="ec-legend-dot" style="background: var(--text-dark);"
              ></span>Inactive
            </div>
          </div>

          <p
            class="ec-hint-txt"
            style="text-align: center; margin-top: 8px; font-size: 0.7rem; color: var(--text-muted);"
          >
            💡 Click on any metal pin on the microchip block above to configure
            its configuration parameters directly!
          </p>
        </div>

        <!-- Pinout Assignments Table -->
        <div class="ec-pinout-list">
          <div class="ec-section-title">Active Pin Mappings</div>
          <div class="ec-pins-table-header">
            <span>Pin</span>
            <span>Signal</span>
            <span>Mode</span>
            <span>Alt Func</span>
          </div>
          {#each $workspaceStore.pins as row}
            <!-- svelte-ignore a11y-click-events-have-key-events -->
            <!-- svelte-ignore a11y-no-static-element-interactions -->
            <div
              class="ec-pin-row {row.enabled ? 'assigned' : 'unassigned'}"
              onclick={() => openPinEditor(row)}
              title="Edit configuration for {row.pin}"
              style="cursor: pointer;"
            >
              <span
                class="ec-pin-id"
                style="border-left: 3px solid {getPinColor(
                  row,
                )}; padding-left: 6px;">{row.pin}</span
              >
              <span class="ec-pin-signal">{row.signal}</span>
              <span class="ec-pin-mode">{row.mode}</span>
              <span class="ec-pin-af">{row.af}</span>
            </div>
          {/each}
        </div>
      {/if}
    </div>
  {/if}

  <!-- ── CLOCK TAB ── -->
  {#if activeTab === "Clock"}
    <div class="ec-content ec-clock-tab">
      {#if isArduinoFramework || isEspIdfFramework}
        <div class="ec-pinout-unavailable">
          <AlertTriangle size={28} />
          <div class="ec-pinout-unavailable-title">
            No RCC/PLL tree for {boardDisplayLabel}
          </div>
          <p>
            {isEspIdfFramework ? "ESP-IDF" : "The Arduino framework"} configures the
            system clock for you at startup — there's no SystemClock_Config()-style
            RCC/PLL tree to expose here, the way there is for STM32Cube HAL boards.
            This board runs at a fixed <strong>{specs.speed}</strong> core clock
            set by the {archKind === "avr"
              ? "AVR"
              : archKind === "xtensa"
                ? "Espressif"
                : archKind === "arm-samd"
                  ? "SAMD"
                  : (boardMeta?.pio_platform ?? "Arduino")}
            board definition.
          </p>
        </div>
      {:else}
        <div class="ec-section-title">Clock Tree Configuration</div>
        <div class="ec-clock-tree">
          {#each clockTreeRows as row}
            <div class="ec-clock-row">
              <span class="ec-clock-src">{row.src}</span>
              <span class="ec-clock-arrow">{row.arrow}</span>
              <span class="ec-clock-node">{row.node}</span>
              <span class="ec-clock-result">{row.result}</span>
            </div>
          {/each}
        </div>
        <div class="ec-clock-note">
          Exact prescaler tree is family-specific — see the generated
          SystemClock_Config() in the Project tab for the full breakdown.
        </div>

        <div class="ec-section-title" style="margin-top: 16px;">
          Clock Source Frequencies
        </div>
        {#each clockSourceRows as row}
          <div class="ec-param-row">
            <label class="ec-param-label" for={makeFieldId(row.label)}
              >{row.label}</label
            >
            <input
              id={makeFieldId(row.label)}
              class="ec-param-input"
              value={row.value}
            />
          </div>
        {/each}
      {/if}
    </div>
  {/if}

  <!-- ── CONFIGURATION TAB ── -->
  {#if activeTab === "Configuration"}
    <div class="ec-content ec-config-tab">
      <!-- Left Sidebar: Peripheral Tree -->
      <div class="ec-cat-col">
        <div class="ec-search-box">
          <Search size={11} class="ec-search-icon" />
          <input
            type="text"
            placeholder="Search peripherals..."
            bind:value={searchQuery}
            class="ec-search-input"
          />
          {#if searchQuery}
            <button class="ec-search-clear" onclick={() => (searchQuery = "")}>
              <X size={10} />
            </button>
          {/if}
        </div>

        <div class="ec-cat-list">
          {#each filteredCategories as cat}
            <div class="ec-cat-group">
              <button
                class="ec-cat-header"
                onclick={() => toggleCategory(cat.id)}
              >
                <span class="ec-cat-icon"
                  ><svelte:component this={cat.icon} size={13} /></span
                >
                <span class="ec-cat-label">{cat.label}</span>
                {#if expandedCategories.has(cat.id)}
                  <ChevronDown size={11} class="ec-cat-arrow" />
                {:else}
                  <ChevronRight size={11} class="ec-cat-arrow" />
                {/if}
              </button>

              {#if expandedCategories.has(cat.id)}
                <div class="ec-cat-children">
                  {#each cat.children as child}
                    {@const cfg = peripheralConfigs[child.id]}
                    {@const isEnabled = cfg?.enabled ?? false}
                    <button
                      class="ec-child-item {selectedPeripheral === child.id
                        ? 'ec-child-active'
                        : ''}"
                      onclick={() => (selectedPeripheral = child.id)}
                    >
                      <span
                        class="ec-child-dot"
                        style="background: {isEnabled
                          ? 'var(--accent-success)'
                          : 'var(--border-color)'}"
                      ></span>
                      <span class="ec-child-label">{child.label}</span>
                      {#if isEnabled}
                        <span class="ec-enabled-badge">ON</span>
                      {/if}
                    </button>
                  {/each}
                </div>
              {/if}
            </div>
          {/each}
        </div>
      </div>

      <!-- Right Panel: Spec Sheet + Parameters Configuration -->
      <div class="ec-detail-col">
        <div class="ec-chip-and-specs">
          <!-- Static Chip display -->
          <div class="ec-chip-wrapper mini-chip">
            <div
              class="ec-chip"
              style="--pin-side-count: {chipPinsPerSide}; --chip-size: {chipPinsPerSide >
              20
                ? '176px'
                : chipPinsPerSide > 12
                  ? '140px'
                  : '112px'}"
            >
              <div class="ec-chip-notch"></div>
              <div class="ec-chip-pins ec-pins-top">
                {#each chipPinsTop as pin}
                  <button
                    type="button"
                    class="ec-pin ec-pin-metal {pin.enabled
                      ? 'active-pin'
                      : ''}"
                    style="--pin-color: {getPinColor(pin)}"
                    onclick={() => openPinEditor(pin)}
                    aria-label="Configure {pin.pin}"
                    title="{pin.pin}: {pin.signal} ({pin.label})"
                  ></button>
                {/each}
              </div>
              <div class="ec-chip-pins ec-pins-bottom">
                {#each chipPinsBottom as pin}
                  <button
                    type="button"
                    class="ec-pin ec-pin-metal {pin.enabled
                      ? 'active-pin'
                      : ''}"
                    style="--pin-color: {getPinColor(pin)}"
                    onclick={() => openPinEditor(pin)}
                    aria-label="Configure {pin.pin}"
                    title="{pin.pin}: {pin.signal} ({pin.label})"
                  ></button>
                {/each}
              </div>
              <div class="ec-chip-pins ec-pins-left">
                {#each chipPinsLeft as pin}
                  <button
                    type="button"
                    class="ec-pin ec-pin-metal ec-pin-h {pin.enabled
                      ? 'active-pin'
                      : ''}"
                    style="--pin-color: {getPinColor(pin)}"
                    onclick={() => openPinEditor(pin)}
                    aria-label="Configure {pin.pin}"
                    title="{pin.pin}: {pin.signal} ({pin.label})"
                  ></button>
                {/each}
              </div>
              <div class="ec-chip-pins ec-pins-right">
                {#each chipPinsRight as pin}
                  <button
                    type="button"
                    class="ec-pin ec-pin-metal ec-pin-h {pin.enabled
                      ? 'active-pin'
                      : ''}"
                    style="--pin-color: {getPinColor(pin)}"
                    onclick={() => openPinEditor(pin)}
                    aria-label="Configure {pin.pin}"
                    title="{pin.pin}: {pin.signal} ({pin.label})"
                  ></button>
                {/each}
              </div>
              <div class="ec-chip-body">
                <div class="ec-model" style="font-size: 8px;">
                  {selectedBoard}
                </div>
              </div>
            </div>
          </div>

          <div class="ec-spec-grid">
            <div class="ec-spec-item">
              <span class="ec-spec-lbl">Flash</span><span class="ec-spec-val"
                >{specs.flash}</span
              >
            </div>
            <div class="ec-spec-item">
              <span class="ec-spec-lbl">RAM</span><span class="ec-spec-val"
                >{specs.ram}</span
              >
            </div>
            <div class="ec-spec-item">
              <span class="ec-spec-lbl">Speed</span><span class="ec-spec-val"
                >{specs.speed}</span
              >
            </div>
            <div class="ec-spec-item">
              <span class="ec-spec-lbl">Core</span><span class="ec-spec-val"
                >{specs.core}</span
              >
            </div>
          </div>
        </div>

        <!-- Dynamic Peripheral Parameter Details -->
        <div class="ec-detail-panel">
          <div class="ec-detail-header">
            <div class="ec-detail-title">
              {#if selectedConfig.enabled}
                <CheckCircle size={14} style="color: var(--accent-success);" />
              {:else}
                <AlertTriangle size={14} style="color: var(--text-dark);" />
              {/if}
              <span>{selectedConfig.name} Configuration</span>
            </div>

            <!-- svelte-ignore a11y-label-has-associated-control -->
            <label
              class="ec-toggle-switch"
              title={selectedConfig.enabled
                ? "Disable Peripheral"
                : "Enable Peripheral"}
            >
              <input
                type="checkbox"
                checked={selectedConfig.enabled}
                onchange={() => togglePeripheral(selectedPeripheral)}
                style="display: none;"
              />
              <div class="ec-toggle-track {selectedConfig.enabled ? 'on' : ''}">
                <div class="ec-toggle-thumb"></div>
              </div>
            </label>
          </div>

          {#if selectedConfig.enabled}
            <div class="ec-detail-body">
              <div class="ec-param-row">
                <label
                  class="ec-param-label"
                  for={makeFieldId("Operating Mode")}>Operating Mode</label
                >
                <select
                  id={makeFieldId("Operating Mode")}
                  class="ec-param-select"
                  value={selectedConfig.mode ?? ""}
                  onchange={(e) =>
                    updateParam(
                      selectedPeripheral,
                      "mode",
                      e.currentTarget.value,
                    )}
                >
                  <option value={selectedConfig.mode ?? ""}
                    >{selectedConfig.mode ?? "Default Mode"}</option
                  >
                  <option value="Disabled">Disabled</option>
                </select>
              </div>

              {#if selectedConfig.speed}
                <div class="ec-param-row">
                  <label
                    class="ec-param-label"
                    for={makeFieldId("GPIO Pin Speed")}>GPIO Pin Speed</label
                  >
                  <select
                    id={makeFieldId("GPIO Pin Speed")}
                    class="ec-param-select"
                    value={selectedConfig.speed}
                    onchange={(e) =>
                      updateParam(
                        selectedPeripheral,
                        "speed",
                        e.currentTarget.value,
                      )}
                  >
                    {#each ["Low", "Medium", "High", "Very High"] as s}
                      <option value={s}>{s}</option>
                    {/each}
                  </select>
                </div>
              {/if}

              {#if selectedConfig.pullResistor}
                <div class="ec-param-row">
                  <label
                    class="ec-param-label"
                    for={makeFieldId("Internal Resistor")}
                    >Internal Resistor</label
                  >
                  <select
                    id={makeFieldId("Internal Resistor")}
                    class="ec-param-select"
                    value={selectedConfig.pullResistor}
                    onchange={(e) =>
                      updateParam(
                        selectedPeripheral,
                        "pullResistor",
                        e.currentTarget.value,
                      )}
                  >
                    {#each ["No pull-up/down", "Pull-up", "Pull-down"] as p}
                      <option value={p}>{p}</option>
                    {/each}
                  </select>
                </div>
              {/if}

              {#if selectedConfig.params}
                {#each Object.entries(selectedConfig.params) as [key, val]}
                  <div class="ec-param-row">
                    <label class="ec-param-label" for={makeFieldId(key)}
                      >{key}</label
                    >
                    <input
                      id={makeFieldId(key)}
                      class="ec-param-input"
                      value={val}
                      onchange={(e) =>
                        updateParam(
                          selectedPeripheral,
                          key,
                          e.currentTarget.value,
                        )}
                    />
                  </div>
                {/each}
              {/if}

              <div class="ec-detail-badge">
                ✓ {selectedConfig.name} hardware initialization code will be auto-generated.
              </div>
            </div>
          {:else}
            <div class="ec-disabled-msg">
              The {selectedConfig.name} channel is disabled. Toggle the switch in
              the header to activate and map this channel.
            </div>
          {/if}
        </div>
      </div>
    </div>
  {/if}

  <!-- ── PROJECT TAB ── -->
  {#if activeTab === "Project"}
    <div class="ec-content ec-project-tab">
      <div class="ec-section-title">Project Directives</div>
      {#each [{ label: "Firmware Project Name", value: projectName }, ...archProjectRows] as row}
        <div class="ec-param-row">
          <label class="ec-param-label" for={makeFieldId(row.label)}
            >{row.label}</label
          >
          <input
            id={makeFieldId(row.label)}
            class="ec-param-input"
            value={row.value}
          />
        </div>
      {/each}

      <div class="ec-section-title" style="margin-top: 16px;">
        Core Generated Source Layout
      </div>
      {#each isArduinoFramework ? ["src/main.cpp", "platformio.ini"] : isEspIdfFramework ? ["src/main.c", "platformio.ini"] : ["src/main.c", "src/hal/main_init.c", "src/hal/rcc_init.c", "platformio.ini"] as f}
        <div class="ec-file-row">
          <FileCode size={12} style="color: var(--accent-violet-hover);" />
          <span>{f}</span>
        </div>
      {/each}

      {#if generateError}
        <div class="ec-generate-error">{generateError}</div>
      {/if}
      {#if generateSuccess}
        <div class="ec-generate-success">
          ✓ {generatedFileCount} file(s) written — check the Explorer.
        </div>
      {/if}

      <button
        class="ec-generate-btn"
        disabled={isGenerating}
        onclick={generateHALCode}
      >
        <Zap size={13} />
        {isGenerating ? "Generating…" : "Generate Code HAL Files"}
      </button>
    </div>
  {/if}
</div>

<!-- Floating Interactive Pinout Configure Modal -->
{#if editingPin}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div class="ec-pin-modal-backdrop" onclick={() => (editingPin = null)}>
    <div class="ec-pin-modal" onclick={(e) => e.stopPropagation()}>
      <div class="ec-pin-modal-header">
        <div class="title-with-pin">
          <span
            class="modal-pin-dot"
            style="background: {getPinColor(editingPin)}"
          ></span>
          <h3>Configure Pin {editingPin.pin}</h3>
        </div>
        <button class="close-modal-btn" onclick={() => (editingPin = null)}>
          <X size={14} />
        </button>
      </div>

      <div class="ec-pin-modal-body">
        <div class="modal-param-group">
          <!-- svelte-ignore a11y-label-has-associated-control -->
          <label>Enable Pin Connection</label>
          <div style="display: flex; align-items: center; gap: 8px;">
            <input
              type="checkbox"
              bind:checked={pinEnabled}
              id="pin-enabled-chk"
            />
            <span style="font-size: 0.75rem; color: var(--text-muted);">
              {pinEnabled
                ? "Active pin (allocates hardware resource)"
                : "Disabled pin (floating high impedance)"}
            </span>
          </div>
        </div>

        {#if pinEnabled}
          <div class="modal-param-group">
            <!-- svelte-ignore a11y-label-has-associated-control -->
            <label>Pin Custom Label</label>
            <input
              type="text"
              class="modal-input"
              bind:value={pinLabel}
              placeholder="e.g. USER_LED"
            />
          </div>

          <div class="modal-param-group">
            <!-- svelte-ignore a11y-label-has-associated-control -->
            <label>Hardware I/O Mode</label>
            <select class="modal-select" bind:value={pinMode}>
              <option value="Input Floating">Input Floating</option>
              <option value="Output Push Pull">Output Push Pull</option>
              <option value="Alternate Function"
                >Alternate Function (SPI/USART/I2C)</option
              >
              <option value="Analog Mode">Analog Mode (ADC/DAC)</option>
            </select>
          </div>

          {#if pinMode === "Alternate Function"}
            <div class="modal-param-group">
              <!-- svelte-ignore a11y-label-has-associated-control -->
              <label>Alternate Signal Map</label>
              <select class="modal-select" bind:value={pinSignal}>
                {#each signalsForPin(editingPin.pin) as signal}
                  <option value={signal.name}>
                    {signal.name}{signal.af && signal.af !== "-"
                      ? ` (${signal.af})`
                      : ""}
                  </option>
                {/each}
              </select>
            </div>

            <div class="modal-param-group">
              <!-- svelte-ignore a11y-label-has-associated-control -->
              <label>Alternate Function Multiplexer</label>
              <select class="modal-select" bind:value={pinAf}>
                {#each Array.from(new Set(signalsForPin(editingPin.pin)
                      .map((signal: any) => signal.af)
                      .filter((af: string) => af && af !== "-"))) as af}
                  <option value={af}>{af}</option>
                {/each}
              </select>
            </div>
          {:else if pinMode === "Analog Mode"}
            <div class="modal-param-group">
              <!-- svelte-ignore a11y-label-has-associated-control -->
              <label>Analog Input Channel</label>
              <select class="modal-select" bind:value={pinSignal}>
                <option value="Analog_IN0">ADC1_IN0 (Analog Input 0)</option>
                <option value="Analog_IN1">ADC1_IN1 (Analog Input 1)</option>
                <option value="DAC_OUT1">DAC_OUT1 (Analog Output 1)</option>
                <option value="DAC_OUT2">DAC_OUT2 (Analog Output 2)</option>
              </select>
            </div>
          {:else}
            <div class="modal-param-group">
              <!-- svelte-ignore a11y-label-has-associated-control -->
              <label>GPIO Level Signal</label>
              <select class="modal-select" bind:value={pinSignal}>
                <option value="GPIO_Input">GPIO_Input</option>
                <option value="GPIO_Output">GPIO_Output</option>
              </select>
            </div>
          {/if}

          <div class="modal-param-group">
            <!-- svelte-ignore a11y-label-has-associated-control -->
            <label>Pull-Up/Pull-Down Resistor</label>
            <select class="modal-select" bind:value={pinPull}>
              <option value="No pull-up/down">No pull-up/down</option>
              <option value="Pull-up">Pull-up (Weak high)</option>
              <option value="Pull-down">Pull-down (Weak low)</option>
            </select>
          </div>

          <div class="modal-param-group">
            <!-- svelte-ignore a11y-label-has-associated-control -->
            <label>GPIO Drive Speed</label>
            <select class="modal-select" bind:value={pinSpeed}>
              <option value="Low">Low Speed (2 MHz)</option>
              <option value="Medium">Medium Speed (12.5 MHz)</option>
              <option value="High">High Speed (50 MHz)</option>
              <option value="Very High">Very High Speed (100 MHz)</option>
            </select>
          </div>
        {/if}
      </div>

      <div class="ec-pin-modal-footer">
        <button class="cancel-btn" onclick={() => (editingPin = null)}
          >Cancel</button
        >
        <button class="save-btn" onclick={savePinConfig}
          >Apply Configuration</button
        >
      </div>
    </div>
  </div>
{/if}

<style>
  /* Extra styling for floating interactive pin configure modal */
  .ec-generate-error {
    font-size: 0.7rem;
    color: #f87171;
    background: rgba(239, 68, 68, 0.1);
    border-radius: var(--radius-sm);
    padding: 5px 8px;
    margin-bottom: 6px;
  }
  .ec-generate-success {
    font-size: 0.7rem;
    color: #4ade80;
    background: rgba(34, 197, 94, 0.1);
    border-radius: var(--radius-sm);
    padding: 5px 8px;
    margin-bottom: 6px;
  }
  .ec-pin-modal-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    background: rgba(8, 8, 12, 0.7);
    backdrop-filter: blur(4px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 9999;
  }

  .ec-pin-modal {
    background: #0e0e14;
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    width: 380px;
    max-width: 90vw;
    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.6);
    display: flex;
    flex-direction: column;
  }

  .ec-pin-modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 16px;
    border-bottom: 1px solid var(--border-color);
  }

  .title-with-pin {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .modal-pin-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    box-shadow: 0 0 6px rgba(139, 92, 246, 0.4);
  }

  .ec-pin-modal-header h3 {
    margin: 0;
    font-size: 0.9rem;
    font-family: var(--font-sans);
    color: var(--text-bright);
    font-weight: 600;
  }

  .close-modal-btn {
    background: none;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    padding: 2px;
  }

  .close-modal-btn:hover {
    color: var(--text-bright);
  }

  .ec-pin-modal-body {
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    max-height: 60vh;
    overflow-y: auto;
  }

  .modal-param-group {
    display: flex;
    flex-direction: column;
    gap: 5px;
  }

  .modal-param-group label {
    font-size: 0.7rem;
    color: var(--text-muted);
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .modal-input,
  .modal-select {
    background: #14141e;
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    color: var(--text-bright);
    padding: 6px 10px;
    font-size: 0.75rem;
    font-family: var(--font-sans);
    width: 100%;
    outline: none;
  }

  .modal-input:focus,
  .modal-select:focus {
    border-color: var(--accent-violet);
  }

  .ec-pin-modal-footer {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 10px;
    padding: 12px 16px;
    border-top: 1px solid var(--border-color);
    background: #0b0b0f;
    border-bottom-left-radius: var(--radius-md);
    border-bottom-right-radius: var(--radius-md);
  }

  .cancel-btn {
    background: none;
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    font-size: 0.75rem;
    padding: 5px 12px;
    cursor: pointer;
  }

  .cancel-btn:hover {
    color: var(--text-bright);
    background: #161622;
  }

  .save-btn {
    background: var(--accent-violet);
    border: none;
    border-radius: var(--radius-sm);
    color: white;
    font-size: 0.75rem;
    padding: 5px 12px;
    cursor: pointer;
    font-weight: 500;
  }

  .save-btn:hover {
    background: var(--accent-violet-hover);
  }

  /* Chip animations */
  .active-pin {
    box-shadow: 0 0 6px rgba(0, 229, 255, 0.4);
    animation: pinGlow 2s infinite alternate;
  }

  @keyframes pinGlow {
    from {
      opacity: 0.8;
    }
    to {
      opacity: 1;
      filter: brightness(1.2);
    }
  }
</style>
