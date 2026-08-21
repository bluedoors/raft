# LED calibration — index vs. physical key

The firmware addresses each key LED by a flat **LED index** `0–14` (via the
firmware's `pixel_map`). The host sends "set LED index N to color", but *which
physical key* index N lights up depends on how you are physically holding the
pad. This doc explains the default calibration and how to redo it for a
different orientation.

## Default orientation: landscape, USB at top-left

Everything in Raft (the `WS_LED_INDEX` map in `sender/duckypad_led.py`, the
`COMMON_KEYS` / `HOST_KEYS` / `top_row_keys()` layout in
`profile/duckypad_build_profile.py`) is calibrated for the pad held in
**landscape** with the **USB cable exiting at the top-left** (i.e. the physical
portrait pad rotated 90° counter-clockwise).

In that orientation the LED indices fall on the 3×5 grid like this:

```
        col1 col2 col3 col4 col5
 top:     2    5    8   11   14      <- workspace status row (WS1..WS5)
 mid:     1    4    7   10   13
 bot:     0    3    6    9   12
```

So the top-row workspace status LEDs are indices **2, 5, 8, 11, 14**, which is
exactly `WS_LED_INDEX = {1: 2, 2: 5, 3: 8, 4: 11, 5: 14}`. Only 5 keys are in
the top row, so workspaces 6+ get no status LED in this layout — on cmux that
means workspace 6 onward is invisible, and on Orca it means your
`~/.config/raft/board.json` may declare at most five slots.

## Key-file numbering vs. LED index

The profile stores per-key files as `keyN.txt` / `keyN.dsb`, numbered `1–15`
(the duckyPad's 1-based key numbering). These are offset by one from the
0-based LED index:

> **key-file N  ⟷  LED index N − 1**

For example, key-file `key3` is LED index `2` (top-left workspace key, `WS1`).
`profile/duckypad_build_profile.py` uses this relationship directly (see the
grid in its docstring).

## Re-calibrating for a different orientation

If you mount the pad differently (portrait, USB at bottom, etc.), the physical
position of each LED index changes and you must remap.

1. **Light every LED with a distinct color and print a legend:**

   ```bash
   sudo /usr/local/libexec/duckypad_led.py --calibrate
   # or, before install:
   sudo python3 sender/duckypad_led.py --calibrate
   ```

   This lights all 15 keys and prints `index N = COLOR`. It also works as a
   raw single-LED test:

   ```bash
   sudo python3 sender/duckypad_led.py --index <0-14> <R> <G> <B>
   ```

   (`scripts/duckypad_ledtest.py` is a similar hold-test that keeps colors on
   for several seconds.)

2. **Hold the pad in your chosen orientation** and write down the color grid
   left→right, top→bottom, noting which edge the USB cable is on. Convert each
   color back to its index using the printed legend. That gives you the LED
   index at each physical position.

3. **Update `WS_LED_INDEX`** in `sender/duckypad_led.py` so ordinal 1 maps to
   the top-left status key's index in *your* grid, ordinal 2 to the next, etc.

4. **Update the profile layout** in `profile/duckypad_build_profile.py` if you
   want the key labels/actions to follow the same physical arrangement, then
   rebuild and re-push (see [`../profile/README.md`](../profile/README.md)).

---

## Orca row order — the one setting Raft needs

The LED map is hardware calibration. Orca needs one setting instead, because the
top row addresses worktrees by **position**: `⌘1`–`⌘5` select the Nth worktree row
in the sidebar.

**Set the worktree sidebar sort to `Manual`.** Orca's full set of modes, read out
of its bundle:

| Mode | Sorts by | Stable for Raft? |
|---|---|---|
| `smart` (default) | agent-state class → attention → activity → name | **No** — rows move as agents work |
| `recent` | last activity → name | No |
| `name` | alphabetical | Yes, until you rename or add |
| `repo` | repo name → name | Yes, same caveat |
| `manual` | `manualOrder ?? sortOrder` → name | **Yes — use this** |

On `smart`, key 3 stops meaning what it meant a minute ago, because a worktree
that needs attention is promoted. On `manual`, order is what you dragged and
agent state is ignored entirely.

Then tell Raft which worktree each row holds, by reading your own sidebar top to
bottom:

```bash
python3 scripts/raft_board_init.py --list          # what exists
python3 scripts/raft_board_init.py --rows raft radar billing-api
python3 scripts/raft_board_verify.py               # every row still alive?
```

This costs no profile rebuild and no push — the pad's keys are fixed keystrokes.

**Do not try to derive the row order from Orca's own files.** We tried, three
times, and got it wrong each time: `orca worktree list --json` and `worktree ps`
each return their own unrelated order, and the persisted fields (`projectGroups[].tabOrder`,
`repos[].projectGroupOrder`, `worktreeMeta[].manualOrder`) did not reproduce the
observed rows. If you need ground truth, measure it instead — press `⌘1`…`⌘n` and
read the visit timestamps Orca writes:

```bash
python3 -c "
import json, os
p = os.path.expanduser('~/Library/Application Support/Orca/profiles/local-default/orca-data.json')
v = json.load(open(p))['workspaceSession']['lastVisitedAtByWorktreeId']
for wid, ts in sorted(v.items(), key=lambda kv: kv[1])[-9:]:
    print(ts, wid.split('::')[-1])
"
```

The last N lines, in order, are the rows you just pressed. That trick is how the
row order in this doc was established, and it survives any change to Orca's
internal sorting because it observes the result rather than modelling the cause.

## After an Orca upgrade

Orca installs its **own** Claude Code hook, as a sibling entry on the same
lifecycle events Raft uses, in the same `~/.claude/settings.json`. That is fine —
both run — but an upgrade that rewrites the hooks block could drop Raft's entry.
Check with:

```bash
python3 -c "
import json, os
hooks = json.load(open(os.path.expanduser('~/.claude/settings.json')))['hooks']
for event, entries in hooks.items():
    raft = sum('duckypad_hook.py' in h.get('command','')
               for e in entries for h in e.get('hooks', []))
    orca = sum('orca/agent-hooks' in h.get('command','')
               for e in entries for h in e.get('hooks', []))
    print(f'{event:20} raft={raft} orca={orca}')
"
```

Expected: `raft=1` on every event Raft wires (SessionStart, UserPromptSubmit,
Notification, Stop, StopFailure, SessionEnd). A `raft=0` means the block was
replaced — re-merge [`../hooks/settings.snippet.json`](../hooks/settings.snippet.json).
Raft's entry survived 1.4.184 → 1.4.185 here, so this is a precaution, not a
known failure.

`raft=1` only proves an entry *exists*. If your settings point at a copy of
`duckypad_hook.py` rather than the one in your checkout, that copy can be
arbitrarily old and will fail silently — see
[Keep the wired hook in sync](../sender/README.md#keep-the-wired-hook-in-sync)
for the version check.

While you are there, confirm Orca's `terminalShortcutPolicy` is still its
default `orca-first`. On `terminal-first`, ⌘J is delivered to the focused
terminal pane instead of Orca, and the entire top row stops working from inside
a session — which is the only place you press it.
