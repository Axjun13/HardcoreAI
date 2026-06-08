# Vendored flash toolchain

This directory holds the bundled tools the app shells out to for **flashing** and
**device detection**, so the shipped application needs no manual user install.

## OpenOCD (ST-Link detection + SWD flashing)

Expected layout (resolved by `backend/services/hardware.py: openocd_bin()`):

```
backend/vendor/openocd/<platform>/bin/openocd        # linux | macos | windows
backend/vendor/openocd/<platform>/openocd/scripts/   # interface/target .cfg files
```

Populate it with:

```bash
node scripts/fetch-tools.mjs          # current platform
node scripts/fetch-tools.mjs --force  # re-download
```

The release packager (`scripts/release.mjs`) copies `backend/vendor/` into the
archive when present, so the flash binary ships with the app.

## Resolution order / overrides

`hardware.py` resolves OpenOCD as: `$OPENOCD_BIN` env override → this vendored
path → `openocd` on `PATH`. So system-installed OpenOCD also works for dev.

## Building (PlatformIO)

The **build** toolchain (ARM GCC + STM32 framework) is **not** vendored here — it
is app-managed by PlatformIO, which auto-provisions into `backend/data/penv` on
first build (see `ensure_platformio()` in `hardware.py`). Nothing to place here
for builds.

> The binaries themselves are gitignored (large, OS-specific). Only this README
> is tracked.
