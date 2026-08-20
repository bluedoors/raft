# Profile — the `cmux` and `orca` duckyPad profiles

The Raft duckyPad profiles are **generated from code**, not hand-clicked in the
Configurator GUI. The scripts here compile duckyScript to byte-exact `.dsb`
files using the Configurator's *own* compiler modules, then push a whole
profile to the pad over HID.

One profile per host. Both can live on the pad at once; the +/- buttons pick
which is loaded, and the loaded one also decides which host is allowed to paint
the status LEDs (see [Ownership](#ownership-the-loaded-profile-decides)).

## Files

| File | Role |
|---|---|
| `duckypad_compile.py` | Compiles a duckyScript source string → `.dsb` bytes using the Configurator's `dsvm_*` modules. Byte-exact with what the GUI produces. |
| `duckypad_build_profile.py` | Defines the key labels, scripts, and colors for one host and writes `profile_<host>/` (config.txt + key*.txt + key*.dsb). |
| `duckypad_push_profile.py` | Pushes one `profile_<host>/` to the duckyPad over HID (file-access commands), the same way the Configurator does. |
| `profile_cmux/`, `profile_orca/` | The generated profiles (checked in for convenience). |

## Prerequisites

- Python **3.10+** (the Configurator source uses 3.10+ syntax).
- For pushing: `pip install hidapi`.
- The **duckyPad Configurator SOURCE** (not the app). Download the
  `*_source.zip` asset from
  <https://github.com/duckyPad/duckyPad-Configurator/releases>, unzip it, and
  point `RAFT_CONFIG_SRC` at the folder containing `dsvm_common.py`,
  `dsvm_preprocessor.py`, and `dsvm_make_bytecode.py`:

  ```bash
  export RAFT_CONFIG_SRC=/path/to/duckyPad-Configurator/src
  ```

  (If you place that folder as `duckypad_config_src/` next to this repo, it is
  found automatically.) Only `build()` needs it — the key tables and their
  tests import fine without it.

## Build & push

```bash
# 1. compile duckyScript → .dsb and regenerate a profile
python3 duckypad_build_profile.py --host cmux     # writes profile_cmux/ (default)
python3 duckypad_build_profile.py --host orca     # writes profile_orca/

# 2. (optional) self-check the compiler is byte-exact against a known profile
RAFT_SELFTEST_DIR=/path/to/a/profile/dir python3 duckypad_compile.py --selftest

# 3. push to the pad over HID  (CLOSE the Configurator first; needs root)
sudo python3 duckypad_push_profile.py --profile cmux
sudo python3 duckypad_push_profile.py --profile orca
```

After each push the pad reboots; select the profile with the +/- buttons.

> **If LEDs stop responding after a push, replug the USB cable.** The push ends
> with a soft reset (`C_SW_RESET`) so the pad reloads its profiles, and that
> reset can bring the device back **powered but not re-enumerated**: keys, LEDs
> and OLED all look normal, while the host no longer sees the pad on the USB bus
> at all. Every LED write then becomes a silent no-op, because the writer treats
> an absent pad as "nothing to do" rather than an error. Measured on this
> hardware: `hid.enumerate()` listed 30 devices and *zero* from STMicro
> (`0x0483`) while the pad sat there lit, showing its profile name. A physical
> replug restores all five interfaces including the config one (`usage=0x3A`).
>
> To tell this state apart from a working pad — both are silent — check
> enumeration directly:
>
> ```bash
> /usr/local/libexec/duckypad-venv/bin/python3 -c \
>   "import hid; print(len(hid.enumerate(0x0483, 0xD11C)), 'interfaces')"
> ```
>
> Expect `5 interfaces`. `0` means replug.

`--profile` reuses that name's existing slot in `/profile_info.txt` if it is
already listed, so re-pushing overwrites in place rather than piling up
duplicates.

### `duckypad_build_profile.py` options

| Flag | Default | Meaning |
|---|---|---|
| `--host {cmux,orca}` | `cmux` | Which host's middle row and top row to generate. |
| `--board <path>` | `~/.config/raft/board.json` | Orca only: where the five top-row slots come from. Missing or unreadable → the top row is generated inert, with a pointer to `raft_board_init.py`. |
| `--out <dir>` | `profile_<host>/` | Where to write. |
| `--no-enter` | off | Orca only: type the palette query but **do not** send ⏎, so switching is a deliberate two-press action. Use this if a key ever creates a worktree. |

## Ownership: the loaded profile decides

`duckypad_push_profile.py` records `profile number → host` in
`/usr/local/libexec/duckypad_profiles.json`. `sender/duckypad_led.py` reads the
pad's currently-loaded profile over HID and refuses `--board` writes that come
from a different host, so a cmux session cannot repaint your Orca board.

Two consequences worth knowing:

- The map is only written for profiles pushed by *these* scripts. A profile Raft
  never pushed is treated as unowned and writes are allowed — deliberately
  fail-open, so a hand-made profile can't lock you out.
- Only the host you have actually pushed appears in the map. Push both to arm
  the gate in both directions.

## Key map

Both profiles are laid out for **landscape orientation, USB at top-left**.
Labels are ≤7 characters (duckyPad limit) — longer ones are truncated, not
rejected.

| Row | `cmux` | `orca` |
|---|---|---|
| **Top** (status LEDs) | `WS1`–`WS5` → `⌘1`–`⌘5` | your board's labels → `⌘J` + query + ⏎ |
| **Middle** | Unread `⌘⇧U`, New WS `⌘N`, Next WS `⌃⌘]`, Rewind `Esc Esc`, Intrpt `Esc` | Jump `⌘J`, New WS `⌘N`, Next WT `⌘⇧↓`, Rewind `Esc Esc`, Intrpt `Esc` |
| **Bottom** | Yes `yes`↵, No `no`↵, /clear, compact, Auto/Pl `⇧⇥` | identical |

The shared keys live in `COMMON_KEYS`, the per-host middle row in `HOST_KEYS`,
and the top row is computed by `top_row_keys(host, slots)`. See
[`../docs/calibration.md`](../docs/calibration.md) for how physical keys map to
LED indices.

## The Orca top-row macro, and why it has delays

Each Orca top-row key is four or five duckyScript lines:

```
GUI j            # open the ⌘J worktree switch palette
DELAY 500        # wait for the palette to actually take focus
STRING fix/vpc-reuse-and-multideploy-safety
DELAY 400        # wait out the palette's ~300ms filter debounce
ENTER            # select the top match
```

Neither delay is padding, and both were set by measurement rather than taste:

- **`PALETTE_OPEN_DELAY_MS = 500`.** A *warm* ⌘J focuses the palette in well
  under 150 ms, which is exactly what makes a small value dangerous — it works
  until it doesn't. On a **cold** open (first jump after the app has been idle)
  150 ms was not enough: `STRING` began typing into the focused pane instead,
  leaking `raf` into a live agent's prompt, and the palette caught only the
  trailing `t`. Worse, had the palette not opened at all, the `ENTER` would have
  **submitted** the leaked text to that agent. 500 ms costs nothing perceptible
  and removes the class of failure.
- **`PALETTE_FILTER_DELAY_MS = 400`.** The palette debounces filtering by about
  300 ms. Press ⏎ before the list has re-filtered and you select whatever was
  highlighted for the *previous* query. Verified on hardware with a
  34-character query.

If a key ever lands on the wrong worktree or leaves the palette open, raise
`PALETTE_FILTER_DELAY_MS` by 200 and regenerate; record the working values in
[`../docs/calibration.md`](../docs/calibration.md#orca-palette-macro-timing).

**The queries themselves must be unique.** A query matching nothing makes
Orca's palette offer to *create* a worktree — and that offer is a selectable
row, so ⏎ takes it. A query matching several is worse than it looks: Orca ranks
matches by field tier then by most-recently-visited, so the winner changes as
you browse. `scripts/raft_board_init.py` refuses non-unique selectors outright
and `scripts/raft_board_verify.py` re-checks an existing board against live
Orca. Run verify after renaming a branch.
