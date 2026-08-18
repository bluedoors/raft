# Raft on Orca — host-agnostic status + control

**Status:** approved design, not yet implemented
**Date:** 2026-08-18
**Branch:** `orca-host-support`

## Goal

Make Raft drive the duckyPad from Orca as well as cmux, without regressing the cmux path. Orca becomes a second *host* — the thing that owns
workspaces, gives them positions, and jumps between them — behind a small adapter seam.

Non-goals:

- No firmware change. The Orca path uses the same `0x04` LED command and the same six colors.
- No daemon. Status still arrives on Claude Code lifecycle hooks.
- No sudoers change. The existing rule is `… python3 $TARGET *`, so new argument shapes are
  already permitted.
- Not supporting cmux and Orca driving the LEDs *simultaneously*. The pad has one active
  profile; see [Board ownership](#board-ownership).

## Why Orca is different from cmux

| | cmux | Orca |
|---|---|---|
| Unit of work | workspace | worktree (git worktree, grouped by repo) |
| Identity of the firing session | `cmux identify --json` → `caller.workspace_ref` | `$ORCA_WORKTREE_ID` in the hook's inherited env |
| Jump to Nth | `⌘1`–`⌘5` ("select workspace N") | `⌘1`–`⌘9` (`workspace.selectByIndex`) |
| Position stability | `app.reorderOnNotification` bubbles on attention (must be disabled) | explicit `sortOrder` (drag order); not activity-derived |
| Agent status available to us | only what our hook carries | `orca worktree ps --json` → per-worktree `agents[]` with `state`, `interrupted`, `agentType` |

Two facts verified on Orca 1.4.184:

1. `$ORCA_WORKTREE_ID` is set in the agent pane's environment and its value is **exactly** the
   composite `worktreeId` used by `orca worktree list/ps` (`<repoId>::<path>`). No lookup needed
   to identify the firing session — a direct key match.
2. `terminalShortcutPolicy` defaults to `"orca-first"`, so `⌘1`–`⌘9` reach Orca even while an
   agent pane has keyboard focus. A user who sets `terminal-first` breaks the jump keys unless
   they double-tap the modifier; documented as a caveat.

## Architecture

One new concept in `sender/duckypad_hook.py`: a **host adapter** exposing a single call.

```
adapter.board(hook_state) -> {ordinal: led_state, ...}
```

- **cmux adapter** — today's behaviour verbatim: `{resolve_ordinal(): hook_state}`, one key.
- **orca adapter** — the whole board (see below).

`detect()` chooses by the *firing session's environment*, never by what is installed:

1. `$RAFT_HOST` (`orca` | `cmux` | `off`) wins if set — escape hatch for testing and for users
   whose environment confuses the sniffers.
2. `$ORCA_WORKTREE_ID` present → orca.
3. `cmux identify --json` yields a `caller.workspace_ref` → cmux.
4. Otherwise → no-op, exit 0 (unchanged behaviour when neither host is present).

Order matters: Orca is checked before cmux and short-circuits it, so a session running under
Orca can never be misattributed to a cmux workspace even with cmux running.

Both adapters live *in* `duckypad_hook.py`. The hook is installed as a standalone file
(`~/claude/duckypad_hook.py` in the current setup), so a sibling-module import would add a new
failure mode to save ~120 lines. `duckypad_led.py` learns nothing about hosts beyond the
ownership gate.

### Files touched

| File | Change |
|---|---|
| `sender/duckypad_hook.py` | adapter seam, `detect()`, orca board computation, generalised fader |
| `sender/duckypad_led.py` | `--board` batch mode, `--host` ownership gate, `flock` |
| `profile/duckypad_build_profile.py` | host-parameterised key table; emits `profile_cmux/` and `profile_orca/` |
| `profile/duckypad_push_profile.py` | `--profile <name>`; records the assigned profile number → host map |
| `scripts/duckypad_repaint.py` | new: recompute and repaint the whole board on demand |
| `hooks/settings.snippet.json` | unchanged event wiring; comment mentions both hosts |
| `README.md`, `profile/README.md`, `docs/calibration.md` | host-agnostic framing, Orca setup, new caveats |
| `tests/` | new: unit tests over captured `orca worktree ps` fixtures |

## Status model

### The race, and the merge rule that avoids it

Orca installs its own Claude Code hook (`~/.orca/agent-hooks/claude-hook.sh`, which POSTs the
payload to the Orca runtime) as a **sibling entry on the same events** as Raft's hook — Raft at
index 0, Orca at index 1. So at the moment Raft's hook runs, the runtime may not yet have
applied the state change Orca is being told about. Querying `orca worktree ps` alone would paint
the *previous* state for the very session that just fired.

The orca adapter therefore merges two sources:

- **The firing worktree** (`$ORCA_WORKTREE_ID`) → the state the hook carried. Authoritative,
  zero-latency, immune to the race.
- **Every other key on the board** → `orca worktree ps --json` (~250 ms measured), Orca's own
  truth.

This is what buys the things pure hooks cannot: worktrees running Codex/Gemini/Droid panes light
up too, and an interrupted turn self-corrects on the next hook from *any* session instead of
staying amber forever.

### Orca agent state → LED

Orca's agent state enum is `["waiting", "blocked", "interrupted", "working", "done", "idle"]`.
It maps onto Raft's six existing colors with no palette change:

| Orca | Raft state | Color |
|---|---|---|
| `waiting` | `needs` | blue |
| `blocked` | `failed` | red |
| `working` | `working` | amber |
| `done` | `done` | green (fades to off) |
| `interrupted`, `idle` | `idle` | dim purple |
| no agent panes | `off` | unlit |

Two refinements:

- A worktree can hold several agent panes in different states (observed: one `done` and one
  `waiting` in the same worktree). Aggregate by **precedence in the order of the table above** —
  `waiting` outranks everything, because it is the only state that wants you *now*.
- `agents[].interrupted == true` maps to `idle` regardless of the reported `state`.

### Fade

The `done` → `off` fade survives, but shrinks. A repaint is idempotent and derived from truth, so
the per-ordinal token bookkeeping is no longer load-bearing on the Orca path: the fader becomes a
single detached "repaint the board again in N seconds" sleeper. `agents[].updatedAt` /
`stateStartedAt` let the repaint compute the remaining fade window rather than remember it, so a
board painted mid-fade lands in the right place.

The cmux path keeps the existing token/fader machinery unchanged.

## Board addressing

Keys 1–5 are Orca's **pinned** worktrees (`isPinned == true`, excluding `isArchived`), ordered by
`sortOrder`, truncated to 5. Pinning in Orca *is* how you program the board — durable, explicit,
and unaffected by creating or archiving unrelated worktrees.

- **Nothing pinned** (the state of a fresh Orca install — and of this machine today, with 10
  worktrees and 0 pinned): fall back to the first five unarchived worktrees by `sortOrder`, and
  log that the fallback was used. The board works before you have pinned anything.
- **More than 5 pinned:** the first five by `sortOrder` get keys; log the remainder. Only nine
  are addressable by `⌘N` at all, so pinning is the documented answer to a large worktree list.
- **The firing worktree is not on the board** (unpinned, or beyond the fifth): walk
  `parentWorktreeId` up to the nearest board member and attribute the state there — this makes
  child worktrees spawned by Orca's orchestration light their parent's key. If no ancestor is on
  the board, repaint the other keys and skip this one. Never guess a key.

**Assumption to verify before implementing:** that `⌘1`–`⌘9` indexes the flat visible sidebar
list with pinned rows first, so key *N* jumps to the same worktree the LED describes. The bundle
references `workspace.selectByIndex` from the jump-palette module and exposes
`visibleWorktreeIds` / `visibleWorktreeGroups`, but which flat list wins is unconfirmed. See
[Verification](#verification-before-implementing). If pinned-first turns out to be wrong, the
fallback is name-based macros — each top-row key sends `⌘J`, types the worktree name, `⏎` — which
changes only the profile generator, not the status pipeline.

## Board ownership

The duckyPad has one active profile, and the cmux and Orca profiles differ in their keystrokes
(`⌘J` vs `⌘⇧U`, `⌘⇧↓` vs `⌃⌘]`). So the board can only serve one host at a time, and if both
hosts' hooks write LEDs the board lies — the one thing Raft must not do.

Resolution: **the pad's loaded profile is the declaration of which host owns the board.**

- HID command `0x00` already returns `current_profile` in response byte 11 (see
  `scripts/duckypad_probe.py`). `duckypad_led.py` reads it inside the device open it already
  performs — effectively free.
- `duckypad_push_profile.py` already maintains `/profile_info.txt` as `<number> <name>` lines. It
  gains the job of recording the number it assigned into a root-owned
  `/usr/local/libexec/duckypad_profiles.json` (`{"1": "cmux", "2": "orca"}`), so the mapping is
  generated rather than hand-maintained. `duckypad_led.py` falls back to a built-in default map
  if the file is absent.
- The hook passes its host: `duckypad_led.py --host orca --board 1:working 2:idle …`. If the
  loaded profile belongs to the other host, the write is **refused** and logged. The losing
  host's sessions simply don't light anything.
- An **unknown** profile number (a user's own hand-made profile) is *allowed* and logged. Single
  host users — the common case — never trip the gate; dual-host users get the two generated
  profiles and correct gating.
- Switching profiles on the pad hands the raft over cleanly: the firmware patch already drops
  host LED overrides on profile switch (while preserving them on same-profile reload), so no
  stale colors survive the handover. The newly-owning host's keys stay dark until its next hook
  fires, which is honest; `scripts/duckypad_repaint.py` exists to fill them in immediately.

## Batch LED write

Repainting five keys as five `sudo` + Python + HID-open round trips is wasteful and racy. So
`duckypad_led.py` gains:

```
duckypad_led.py --host <orca|cmux> --board 1:working 2:done 3:off 4:off 5:off
```

One device open, one profile check, up to five `0x04` packets. The whole board is written every
time — unconditional and idempotent, which is what makes it self-healing after an unplug, a
sleep, or a missed event.

Two sessions finishing at once produce two overlapping repaints, so the write is wrapped in an
`flock` on a lock file. Both boards derive from nearly identical truth, so the worst case was
always a transient, but the lock makes it deterministic and costs nothing.

The single-key form (`duckypad_led.py 2 working`) stays for the cmux path and takes the same
optional `--host` gate, so cmux cannot paint over an Orca-owned board either. The calibration
forms (`--index`, `--all-off`) bypass the gate — they are deliberate manual operations.

## Key layout

Ten of the fifteen keys talk to *Claude*, not the host, and are untouched: `Yes`, `No`, `/clear`,
`/compact`, `⇧Tab`, `Esc` (interrupt), `Esc Esc` (rewind). `New WS` is already `⌘N` on both
hosts. `profile_orca/` differs from `profile_cmux/` in exactly two keys:

| Key | cmux | Orca | Orca command |
|---|---|---|---|
| Unread / Jump | `⌘⇧U` | `⌘J` | `worktree.palette` — Orca has no jump-to-unread, so this becomes the switcher |
| Next WS | `⌃⌘]` | `⌘⇧↓` | `worktree.navigateDown` |

The generator becomes host-parameterised (a shared key table plus a per-host overlay of those two
entries) rather than growing a second copy of the table.

## Edge cases

| Case | Behaviour |
|---|---|
| Both hosts installed, session in one | `detect()` resolves from the firing session's env; Orca short-circuits before cmux |
| Both hosts running, sessions in both | Profile gate: only the host matching the pad's loaded profile writes; the other logs and no-ops |
| `$RAFT_HOST=off` | Hook exits 0 without touching anything |
| Neither host | Unchanged: exit 0 silently |
| Orca app quit / runtime unreachable | `orca worktree ps` fails or times out (3 s) → paint only the firing worktree using the last cached board mapping (`/tmp/duckypad_state/board.json`); if no cache, no-op |
| Orca CLI slow under load | Hooks are `async: true`, so latency is invisible to the session; the 3 s timeout bounds it |
| Firing worktree not on the board | Walk `parentWorktreeId` to the nearest board member; else skip that key, still repaint the rest |
| Several agent panes in one worktree | Precedence: `waiting` > `blocked` > `working` > `done` > `interrupted`/`idle` |
| Agent interrupted | `interrupted == true` → dim purple, and no longer waits for the next prompt to self-correct |
| Non-Claude agents (Codex, Gemini, Droid) | Lit from `worktree ps`; they never fire *our* hook, so their key updates on the next repaint any session triggers |
| Nothing pinned | Fall back to first five unarchived by `sortOrder`, log it |
| More than 5 pinned / more than 9 worktrees | First five get keys; log the rest; README documents pinning as the answer |
| Worktree archived or dragged while lit | Next repaint recomputes positions from scratch; stale keys go `off` |
| Remote / federated Orca hosts (`hostId != "local"`) | Included — they appear in the sidebar and `⌘N` addresses them |
| Two sessions repaint simultaneously | `flock` serialises the writes |
| Orca rewrites `~/.claude/settings.json` | Raft's entry sits at index 0 and coexists with Orca's today; a doctor check in `docs/` tells the user how to confirm after an Orca upgrade |
| Pad unplugged | Unchanged: `duckypad_led.py` no-ops silently, exit 0 |

## Verification before implementing

Three unknowns, each with a decided fallback so none of them blocks the design:

1. **What `⌘1`–`⌘9` indexes.** Probe: press `⌘2`, then read which worktree has `isActive: true`
   in `orca worktree ps --json`; repeat with a pinned worktree to test pinned-first, and with
   Orca's "sleeping workspaces" filter toggled to see whether hidden rows consume an index.
   *Fallback if pinned-first is wrong:* name-based macros (`⌘J` + typed name + `⏎`); sections
   above are unaffected.
2. **Does Orca regenerate the `hooks` block on upgrade?** Raft's and Orca's entries coexist
   today. *Fallback:* a documented check, plus a note to re-merge `hooks/settings.snippet.json`.
3. **Sleeping / archived rows in the visible order.** Folded into probe 1.

## Testing

The repo has no test suite today; this adds a proportionate one, because the interesting logic is
pure and hardware-free:

- Capture real `orca worktree ps --json` and `orca worktree list --json` output as fixtures
  (scrubbed of prompts and assistant messages, which are large and private).
- Unit tests, stdlib `unittest`, no hardware: state precedence and aggregation; board computation
  from pinned / unpinned / >5-pinned / archived fixtures; parent walk-up for off-board worktrees;
  `detect()` under each environment combination; fade-window arithmetic.
- Manual, on hardware: `scripts/duckypad_repaint.py` paints the expected board; profile gate
  refuses the wrong host; profile switch clears colors; unplugged pad no-ops; a parallel
  Claude-in-Orca run lights the right keys.

## Documentation

`README.md` moves from "Claude Code in cmux" to "Claude Code in cmux **or** Orca", with a host
table, the Orca-specific setup (pin your worktrees, push `profile_orca`), and new caveats:
`terminalShortcutPolicy` must stay `orca-first`; only nine worktrees are `⌘N`-addressable; the pad
profile decides which host owns the board. The cmux `reorderOnNotification` caveat stays, scoped
to cmux — Orca does not need it.
