# Firmware — custom duckyPad evo build

Raft needs a small firmware change on the duckyPad so the **host** can drive
individual key LEDs. This directory holds everything you need to reproduce the
build on macOS/Linux with the GNU Arm toolchain and flash it over USB DFU.

## Why custom firmware?

The stock duckyPad evo firmware has **no host command to set a per-key LED
color**. HID command `4` (`SET_LED_SINGLE`) was reserved in the protocol but
left unimplemented — sending it to a stock pad returns status `6`
(`UNKNOWN_CMD`). Raft's status-LED feature depends on that command, so the
patch here implements it, plus a small "host override" layer that keeps the
host-set colors alive across a keypress and across sleep/wake (they are cleared
only on a profile switch).

## Why a 128K linker script?

The duckyPad evo uses an **STM32F072C8T6**. Its datasheet specifies **64K** of
flash, but the C8 die is actually the same 128K die (`STM32F072xB`) as the
CB variant with the top half untested/unspecified. The GCC + newlib image built
here is roughly **76K** — it does not fit in the datasheet-spec 64K.

Two linker scripts are provided:

| Script | Flash size | Meaning |
|---|---|---|
| `STM32F072C8Tx_FLASH.ld` | 64K | Spec-safe (matches the datasheet). The GCC build will **not** fit — link fails with a region-overflow error. Kept for reference. |
| `STM32F072xB_128K.ld` | 128K | What we actually flash. Uses the full die. |

Flashing the 128K image is **technically out of datasheet spec**, but it has
been verified working on this die by reading the flash back after programming
(readback matches the written image, and the firmware runs). If your unit
behaves oddly, that is the first thing to suspect.

## Prerequisites (macOS)

```bash
brew install --cask gcc-arm-embedded   # arm-none-eabi toolchain
brew install dfu-util                  # USB DFU flasher
```

## Build steps

1. Clone the upstream duckyPad source at the base commit Raft was built on:

   ```bash
   git clone https://github.com/dekuNukem/duckyPad.git
   cd duckyPad
   git checkout 46dffb33          # default branch is 'master'
   ```

2. Copy the GCC build files from this directory into the firmware tree
   (`firmware/evo/` inside the clone):

   ```bash
   cp /path/to/raft/firmware/Makefile.gcc                firmware/evo/
   cp /path/to/raft/firmware/STM32F072xB_128K.ld         firmware/evo/
   cp /path/to/raft/firmware/startup_stm32f072xb_gcc.s   firmware/evo/
   ```

3. Apply the Raft firmware patch (paths in the patch are relative to the clone
   **root**, so run `git apply` from there):

   ```bash
   git apply /path/to/raft/firmware/raft-firmware.patch
   ```

4. Build with the 128K linker script:

   ```bash
   cd firmware/evo
   make -f Makefile.gcc LDSCRIPT=STM32F072xB_128K.ld
   ```

   The output is `build/duckypad_evo.bin` (and `.elf` / `.hex`).

## Flash over DFU

1. **Hold the DFU button while plugging in** the duckyPad's USB cable to enter
   the STM32 bootloader.
2. Flash the binary to the start of flash:

   ```bash
   dfu-util --device ,0483:df11 -a 0 -s 0x08000000 -D build/duckypad_evo.bin
   ```

3. **Press RESET** (or replug) to boot the new firmware.

Verify with `python3 ../../scripts/duckypad_status.py` (HID interface present)
and `sudo python3 ../../scripts/duckypad_probe.py` (reads firmware version and
blinks keys 0-4).
