# Characterization / contract test suite

These tests lock down the **observable behavior** of the two services the Python
backend depends on. They began life as a regression gate for the **Go → Python
port** (the Go services are now deleted), and remain the contract gate for the
Python implementations:

- **Emulator service** (`backend/emulator/`) — a FastAPI server on `:62019`
  (build / flash / QEMU / GDB debug).
- **RAG engine** (`backend/rag/`) — an in-process Python library (LlamaIndex +
  Chroma + fastembed) consumed directly by the backend; no longer a CLI.

These tests treat each component as a black box and assert on the *contract* the
backend actually consumes (HTTP response shape, status codes; for RAG the
query() output markers and persistent-store behavior) — not on internal details.

> We deliberately do **not** assert on internal details (chunk boundaries, exact
> rerank scores, register values). Those are implementation details a correct
> implementation may legitimately differ on. We assert on the *contract*:
> response shape, status codes, output markers.

## Layout

```text
tests/
  conftest.py            # shared fixtures: boots the emulator service + drives the RAG engine
  test_emulator_contract.py
  test_rag_contract.py
  README.md
```

## Prerequisites (already installed on the dev machine)

- `qemu-system-arm`, `arm-none-eabi-gcc`, `arm-none-eabi-gdb` (emulator e2e)
- PlatformIO (`~/.platformio/penv/bin/pio`) — first build downloads the STM32 toolchain
- A prebuilt firmware ELF at
  `backend/emulator/Blinky/.pio/build/genericSTM32F405RG/firmware.elf`
  (build once with `pio run -d backend/emulator/Blinky`)
- The **backend venv** (`backend/.venv`), which carries fastapi/uvicorn/pygdbmi
  for the emulator service and llama-index/chroma/fastembed for the RAG engine.

## Running

The suite now needs the backend's dependencies (RAG libs + the emulator's
fastapi/pygdbmi), so run it with the **backend venv**:

```bash
# from repo root
backend/.venv/bin/python -m pytest tests/ -v

# just the emulator contract
backend/.venv/bin/python -m pytest tests/test_emulator_contract.py -v

# just the rag contract
backend/.venv/bin/python -m pytest tests/test_rag_contract.py -v
```

Tests that require a tool which is absent (e.g. `arm-none-eabi-gdb`) **skip** with
a clear reason rather than failing, so the suite is honest on a partially
provisioned machine.
