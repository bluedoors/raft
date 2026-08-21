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

| `--out <dir>` | `profile_<host>/` | Where to write. |

The generator reads **no** board file: the top row is five fixed keystrokes on both hosts, so the profile is a constant.

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
| **Top** (status LEDs) | `1`–`5` → `⌘1`–`⌘5` | `1`–`5` → `⌘1`–`⌘5` (identical) |
| **Middle** | Unread `⌘⇧U`, New WS `⌘N`, Next WS `⌃⌘]`, Rewind `Esc Esc`, Intrpt `Esc` | Jump `⌘J`, New WT `⌘N`, Next WT `⌘⇧↓`, Rewind `Esc Esc`, Intrpt `Esc` |
| **Bottom** | Yes `yes`↵, No `no`↵, /clear, compact, Auto/Pl `⇧⇥` | identical |

The shared keys live in `COMMON_KEYS`, the per-host middle row in `HOST_KEYS`,
and the top row is computed by `top_row_keys(host, slots)`. See
[`../docs/calibration.md`](../docs/calibration.md) for how physical keys map to
LED indices.

## Why the top row is positional on both hosts

`⌘1`–`⌘5`. On cmux that selects workspace N; on Orca it selects the Nth worktree
row in the sidebar. One keystroke, no timing, no text.

Raft's Orca top row used to type a uniqueness-checked query into the `⌘J`
palette, because Orca has no per-worktree keybinding and its row order looked
unknowable. That worked, and it cost:

- **~900 ms per press**, nearly all of it waiting — 500 ms for the palette to
  take focus, 400 ms for its filter debounce.
- **A prompt-injection hazard.** On a *cold* palette open the keystrokes arrived
  before focus moved, so the query typed into whatever pane was focused. It leaked
  `raf` into a live agent's prompt once; had the palette not opened at all, the
  trailing `ENTER` would have submitted that text as a prompt.
- **A create hazard.** Orca's palette offers "create a worktree" when a query
  matches nothing, and that offer is a selectable row — so a query gone stale
  (a renamed branch, a deleted worktree) meant a keypress *made* a worktree.
  This fired for real: two keys went stale within a day of being configured.

Positional addressing removes all three. "Go to row 3" needs no delay, types
nothing, and cannot create anything. The trade is that row order must be stable,
which means **Orca's worktree sidebar sort must be set to Manual** — its default
(`smart`) re-sorts by agent state, so rows move while you work.

Two limits worth knowing:

- **Only rows 1–9 are addressable**, and the pad uses 1–5. A worktree below row 5
  has no key; below row 9, no keystroke can reach it at all. The `Jump` key
  (`⌘J`) remains as the escape hatch.
- **A collapsed group's worktrees are not rows**, so collapsing hides them from
  the count and shifts everything below.

Labels are `1`–`5` rather than project names on purpose: which worktree a row
holds is decided in Orca, so a baked-in name would go stale the moment you
rearrange. The LED mapping lives in `~/.config/raft/board.json` and is updated
with `scripts/raft_board_init.py --rows …` — no regeneration, no push.
