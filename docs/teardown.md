# Teardown / uninstall

Everything Raft adds, and how to remove it.

## Host software (macOS)

```bash
# privileged LED path (installed by sender/duckypad_install.sh)
sudo rm -f /etc/sudoers.d/duckypad
sudo rm -f /usr/local/libexec/duckypad_led.py
sudo rm -rf /usr/local/libexec/duckypad-venv
```

Then remove the Raft hook entries from `~/.claude/settings.json` — the
`duckypad_hook.py` commands under `SessionStart`, `UserPromptSubmit`,
`Notification`, `Stop`, `StopFailure`, and `SessionEnd` (leave any other hooks
you have intact).

## Toolchain (only if you installed it for this)

```bash
brew uninstall --cask gcc-arm-embedded
brew uninstall dfu-util          # if you don't use it elsewhere
```

## Firmware

Reflash the stock duckyPad firmware to fully revert the device. Download the
official `.dfu` from the [duckyPad firmware history](https://github.com/dekuNukem/duckyPad/blob/master/firmware_updates_and_version_history.md),
enter DFU mode (hold the DFU button while plugging in), then:

```bash
dfu-util --device ,0483:df11 -a 0 -D duckypad_vX.Y.Z.dfu
```

The profile files Raft pushed live on the microSD and are harmless; delete the
`/profile_cmux` directory and the `cmux` line from `/profile_info.txt` via the
Configurator (or by editing the SD) if you want them gone.

## Device settings

If you changed the pad's Sleep timeout for Raft, set it back via the on-device
Settings menu (long-press a +/− button) or the Configurator.
