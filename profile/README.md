# Profile — the `cmux` duckyPad profile

The Raft duckyPad profile is **generated from code**, not hand-clicked in the
Configurator GUI. The scripts here compile duckyScript to byte-exact `.dsb`
files using the Configurator's *own* compiler modules, then push the whole
profile to the pad over HID.

## Files

| File | Role |
|---|---|
| `duckypad_compile.py` | Compiles a duckyScript source string → `.dsb` bytes using the Configurator's `dsvm_*` modules. Byte-exact with what the GUI produces. |
| `duckypad_build_profile.py` | Defines the `cmux` profile (key labels, scripts, colors) and writes `profile_cmux/` (config.txt + key*.txt + key*.dsb). |
| `duckypad_push_profile.py` | Pushes `profile_cmux/` to the duckyPad over HID (file-access commands), the same way the Configurator does. |
| `profile_cmux/` | The generated profile (checked in for convenience). |

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
  found automatically.)

## Build & push

```bash
# 1. compile duckyScript → .dsb and regenerate profile_cmux/
python3 duckypad_build_profile.py

# 2. (optional) self-check the compiler is byte-exact against a known profile
RAFT_SELFTEST_DIR=/path/to/a/profile/dir python3 duckypad_compile.py --selftest

# 3. push to the pad over HID  (CLOSE the Configurator first; needs root)
sudo python3 duckypad_push_profile.py
```

After the push the pad reboots; select the **`cmux`** profile with the +/-
buttons.

## Key map

The profile is laid out for **landscape orientation, USB at top-left**. Labels
are ≤7 characters (duckyPad limit).

| Row | Keys | Purpose |
|---|---|---|
| **Top** | `WS1`–`WS5` (⌘1–⌘5) | Jump to cmux workspace 1–5. These are also the **status LEDs** — the hook overrides their color live (amber = working, blue = needs you, green = done). |
| **Middle** | Unread, New WS, Next WS, Plan, Intrpt | Navigation / mode: `⌘⇧U`, `⌘N`, `⌃⌘]`, `⇧⇥` (plan mode), `Esc` (interrupt). |
| **Bottom** | Yes, No, /clear, compact, Rewind | Claude Code actions: Enter, Escape, `/clear`↵, `/compact`↵, Esc Esc. |

The exact scripts and colors live in the `KEYS` mapping in
`duckypad_build_profile.py`. See [`../docs/calibration.md`](../docs/calibration.md)
for how physical keys map to LED indices.
