# Sender — host-side LED driver + Claude Code hook

This is the piece that lights up duckyPad keys from your Mac to show the live
state of each Claude Code session. It requires the [custom firmware](../firmware/README.md).

## Files

| File | Role |
|---|---|
| `duckypad_led.py` | The low-level LED setter. Opens the duckyPad HID config interface and sends the custom `SET_LED_SINGLE` (command `0x04`) packet. Maps an ordinal + state (`working`/`needs`/`done`/`failed`/`idle`/`off`) to a physical LED index and color. Opens/closes the device per call and **no-ops silently** if the pad is absent. Takes one key at a time (`<ordinal> <state>`) or the whole board in one locked, batched write (`--board 1:working 2:needs …`). |
| `duckypad_hook.py` | The Claude Code hook bridge. Fires on session lifecycle events, works out which host the firing session belongs to, resolves that session's own key, and invokes `duckypad_led.py` via `sudo -n`. On **cmux** it asks `cmux identify` for a workspace ordinal and sets that one key; on **Orca** it reads `$ORCA_WORKTREE_ID` plus `orca worktree ps` and repaints all five. Standalone and stdlib-only by design — it is copied into hook configs, not imported. |
| `duckypad_install.sh` | One-time installer (see below). |

## Why root / NOPASSWD sudo?

On macOS, opening the duckyPad HID **config** interface requires **root**. So
the LED script must run as root. To let Claude Code hooks (which run as your
user) do this without a password prompt on every event, `duckypad_install.sh`
sets up a tightly-scoped `NOPASSWD` sudoers rule pinned to a root-owned
interpreter and a root-owned copy of the script (neither user-writable).

## Install flow

Run once, with interactive sudo, from this directory:

```bash
sudo bash duckypad_install.sh
```

This will:

1. Create a **root-owned** venv at `/usr/local/libexec/duckypad-venv` (built on
   the system `/usr/bin/python3`) and `pip install hidapi` into it.
2. Install `duckypad_led.py` to `/usr/local/libexec/duckypad_led.py`
   (`root:wheel`, mode `755`) — copied **from this repo**.
3. Write `/etc/sudoers.d/duckypad` allowing your user to run *only* that
   interpreter + script via `NOPASSWD` sudo, and validate it with `visudo -c`.
4. Smoke-test the rule as your user.

The installer requires `sudo` (it reads `$SUDO_USER` for the sudoers entry and
exits if run without sudo).

To wire the hook into Claude Code, see the settings snippet at the repo root
(`hooks/settings.snippet.json`). The same hook command serves both hosts — it
detects cmux vs Orca from the firing session's environment. Set `RAFT_HOST` to
`cmux`, `orca`, or `off` to override the detection (e.g. `off` in a session you
don't want on the board).

## Host detection and board ownership

`duckypad_hook.py` resolves the host from the **firing session**, not the focused
window: `$ORCA_WORKTREE_ID` present ⇒ Orca, else a successful `cmux identify` ⇒
cmux, else do nothing. So with both installed, each session lights the board it
actually belongs to.

Which host may *paint* is a separate question, answered by the pad itself:
`duckypad_led.py` reads the currently-loaded profile number over HID (`0x00`
query-info) and compares it against `/usr/local/libexec/duckypad_profiles.json`,
written by `profile/duckypad_push_profile.py`. A `--board` write from a host that
doesn't own the loaded profile is refused, so a cmux session cannot repaint an
Orca board. Unknown profiles are allowed — fail-open, so a hand-made profile
can't lock you out. `--index` and `--all-off` bypass the gate deliberately, since
they're calibration and cleanup tools.

Because the sudoers rule pins the *interpreter and script path* (not the
arguments), `--board` and `--host` need no installer or sudoers change.

## LED index calibration

`WS_LED_INDEX` in `duckypad_led.py` maps workspace ordinal → physical LED index.
The shipped values are **calibrated for landscape orientation with the USB
cable at the top-left**. If you mount the pad in any other orientation, the
index→physical-key mapping changes and you must re-calibrate:

```bash
sudo python3 ../scripts/duckypad_ledtest.py      # hold-test known indices
sudo /usr/local/libexec/duckypad_led.py --calibrate   # light all 15 + legend
```

See [`../docs/calibration.md`](../docs/calibration.md) for the full procedure
and the index→physical-key grid.
