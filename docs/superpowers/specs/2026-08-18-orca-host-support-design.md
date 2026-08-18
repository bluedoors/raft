# Raft on Orca — host-agnostic status + control

**Status:** approved design, not yet implemented
**Date:** 2026-08-18
**Branch:** `orca-host-support`

## Goal

Make Raft drive the duckyPad from Orca as well as cmux, without regressing the cmux path. Orca
becomes a second *host* — the thing that owns workspaces and jumps between them — behind a small
adapter seam.

Non-goals:

- No firmware change. The Orca path uses the same `0x04` LED command and the same six colors.
- No daemon. Status still arrives on Claude Code lifecycle hooks.
- No sudoers change. The existing rule is `… python3 $TARGET *`, so new argument shapes are
  already permitted.
- Not supporting cmux and Orca driving the LEDs *simultaneously*. The pad has one active profile;
  see [Board ownership](#board-ownership).

## Probe log — what Orca actually does

Measured against Orca 1.4.184 on 2026-08-18. These results killed the first draft's positional
addressing, so they are recorded here rather than summarised.

1. **`$ORCA_WORKTREE_ID` is set in the agent pane's environment**, and its value is *exactly* the
   composite `worktreeId` used by `orca worktree list/ps` (`<repoId>::<path>`). Identifying the
   firing session is a direct key match — no `cmux identify` equivalent needed.
2. **`⌘1`–`⌘9` (`workspace.selectByIndex`) indexes visible *worktree rows* in the sidebar's
   project → repo → worktree tree.** Pressing `⌘2` selected the worktree whose breadcrumb is
   `Territory-Management → sa-assist → main`, which is the second *worktree* row in the tree, and
   is row 6 of `worktree list` (and row 5 by most-recent-activity). Collapsed repos contribute no
   rows, so the index also depends on expand/collapse state. **Neither the tree order nor the
   collapse state is exposed by the CLI**, so the index is not reproducible from data Raft can
   read.
3. **`sortOrder` is not a stable drag order.** It renumbered twice in half an hour with no user
   action (`…375907` → `…893194` → `…447024`, always contiguous +1000 steps), and the relative
   order of two `anthropic-on-aws` worktrees swapped between reads. Positional addressing is
   therefore unsafe even ignoring finding 2.
4. **`worktree ps`'s `isActive` does not track UI selection** — it stayed on `raft` across a `⌘2`
   jump. `--worktree active` resolves by *current directory*, not app focus. There is no CLI
   readout of the focused worktree.
5. **`terminalShortcutPolicy` defaults to `"orca-first"`**, so app shortcuts reach Orca even while
   an agent pane has keyboard focus. A user who sets `terminal-first` breaks them unless they
   double-tap the modifier. Caveat, not a blocker.
6. **Orca's agent state enum is `["waiting","blocked","interrupted","working","done","idle"]`**,
   exposed per pane via `orca worktree ps --json` → `agents[]`, alongside `agentType`,
   `interrupted`, `updatedAt`, and `stateStartedAt`. A single worktree can hold panes in different
   states (observed: one `done` and one `waiting`).
7. **`orca worktree ps --json` costs ~210–270 ms.** No `--watch`/`--follow`; no stream or
   subscribe command anywhere in the 228-command schema.
8. **Computer-use can read but not type.** Accessibility and screenshots are granted, and
   screenshots are how findings 2 and 3 were confirmed, but Orca is Electron so its AX tree
   exposes only window chrome (5 nodes), and every keystroke path — `computer hotkey`,
   `press-key`, `--window-id`, `--restore-window`, `osascript … activate` — is refused with
   `window_not_focused` (`windows.focus: false`). Keystroke-level verification needs a human at
   the keyboard.
9. **The jump palette can create worktrees.** `showCreateAction` is true for *any* non-empty
   query, and the no-match row is `Create worktree "<query>"` with the target repo auto-resolved
   from `eligibleRepos`/`activeRepoId`. A blind `⏎` after a query that matches nothing can create
   a worktree and branch. This shapes the outbound design below.
10. **Palette behaviour, observed directly** (screenshot burst while a human typed; no `⏎` pressed):
    - **Unique query** (`orca-host`): the palette renders a `WORKTREES` section *first*, the single
      match (`orca-host-support`, badged with its repo) is the **highlighted** row, and
      `Create worktree "orca-host"` is present but **last and unselected**. Footer: `Enter → Open`.
      The query matched a substring of a longer display name, which is what the generator relies on.
    - **Ambiguous query** (`main`): five worktree rows, identical names, distinguished only by a
      repo badge; the highlighted row was `sa-assist`, an order matching neither the sidebar nor
      alphabetical — the matcher's own ranking. Unpredictable, hence build-time uniqueness.
    - **No-match query** (`zzqq`): exactly one row, `Create worktree "zzqq"`, **highlighted**.
      Hazard confirmed, not theoretical.
    - The palette also matches **open-tab content**, including agent message text, and
      `ACTIONS & SETTINGS` entries. Ranking is `WORKTREES` → `OPEN TABS` → `ACTIONS & SETTINGS` →
      create, so a worktree match always outranks the rest; a stale query that still matches a tab
      or setting jumps somewhere harmless rather than creating anything.
11. **`⌘J` from a focused terminal pane pops a toast** — "Terminal shortcut handled — Switch
    worktree (⌘J)" — because `orca-first` policy reports shortcuts it captures from the terminal.
    Cosmetic, dismissible, but it will appear on jumps; worth a README note.

## Why Orca differs from cmux

| | cmux | Orca |
|---|---|---|
| Unit of work | workspace | worktree (git worktree, grouped repo → project) |
| Identity of the firing session | `cmux identify --json` → `caller.workspace_ref` | `$ORCA_WORKTREE_ID` from the inherited env |
| Addressing | sidebar position, `⌘1`–`⌘5` | **not positional** — tree index, unreadable from the CLI (probe 2, 3) |
| Agent status available to us | only what our hook carries | `orca worktree ps --json`, all agent types |

## Architecture

One new concept in `sender/duckypad_hook.py`: a **host adapter** exposing a single call.

```
adapter.board(hook_state) -> {ordinal: led_state, ...}
```

- **cmux adapter** — today's behaviour verbatim: `{resolve_ordinal(): hook_state}`, one key.
- **orca adapter** — the whole board, from the config plus `worktree ps`.

`detect()` chooses by the *firing session's environment*, never by what is installed:

1. `$RAFT_HOST` (`orca` | `cmux` | `off`) wins if set — escape hatch for testing.
2. `$ORCA_WORKTREE_ID` present → orca.
3. `cmux identify --json` yields a `caller.workspace_ref` → cmux.
4. Otherwise → no-op, exit 0 (unchanged when neither host is present).

Order matters: Orca is checked before cmux and short-circuits it, so a session running under Orca
can never be misattributed to a cmux workspace even with cmux running.

Both adapters live *in* `duckypad_hook.py`. The hook is installed as a standalone file
(`~/claude/duckypad_hook.py` today), so a sibling-module import would add a new failure mode to
save ~120 lines. `duckypad_led.py` learns nothing about hosts beyond the ownership gate.

### Files touched

| File | Change |
|---|---|
| `sender/duckypad_hook.py` | adapter seam, `detect()`, orca board computation, generalised fader |
| `sender/duckypad_led.py` | `--board` batch mode, `--host` ownership gate, `flock` |
| `scripts/raft_board.py` | new: query-uniqueness matching, shared by the init and verify scripts. The hook does *not* import it — reading `board.json` is a `json.load` plus a dict lookup, and the hook must stay a standalone file |
| `scripts/raft_board_init.py` | new: pick five worktrees from live Orca, compute unique palette queries, write `board.json` |
| `scripts/raft_board_verify.py` | new: re-check all five queries against live Orca; non-zero exit on ambiguity or no-match |
| `scripts/duckypad_repaint.py` | new: recompute and repaint the whole board on demand |
| `profile/duckypad_build_profile.py` | host-parameterised key table; emits `profile_cmux/` and `profile_orca/`, top row generated from `board.json` |
| `profile/duckypad_push_profile.py` | `--profile <name>`; records the assigned profile number → host map |
| `hooks/settings.snippet.json` | unchanged event wiring; comment mentions both hosts |
| `README.md`, `profile/README.md`, `docs/calibration.md` | host-agnostic framing, Orca setup, new caveats |
| `tests/` | new: unit tests over captured `orca worktree ps` fixtures |

## The board is Raft-owned

Because Orca's positions are unreadable (probe 2, 3), Raft stops mirroring Orca's sidebar and owns
its own five-slot board: `~/.config/raft/board.json`.

```json
{
  "host": "orca",
  "slots": [
    {"label": "raft",   "worktree": "…::/Users/awsbryn/code/bluedoors/raft", "query": "orca-host-support"},
    {"label": "gateway","worktree": "…::/Users/…/anthropic-on-aws-vpc-reuse", "query": "vpc-reuse"}
  ]
}
```

- `worktree` — the composite worktreeId (`<repoId>::<path>`), used for **status** matching. Exact,
  and directly comparable to `$ORCA_WORKTREE_ID`. If a worktree's path is gone at repaint time,
  its key goes `off`.
- `query` — the string typed into the jump palette for **outbound** jumping.
- `label` — the ≤7-character keycap label (duckyPad limit), also used in logs.

Slot order is key order: slot 1 → LED index 2 → key3. Fewer than five slots is fine; unlisted keys
stay dark.

`board.json` is **Orca-only** — the cmux path stays positional and reads no board file. The `host`
field exists so a stray or half-migrated file can be recognised and ignored rather than
misapplied.

One config, three consumers: the hook (status), the profile generator (macros), and the verifier.

## Outbound — palette macros

Each top-row key sends: `⌘J`, a settling delay, the slot's `query`, a second delay, `⏎`.

```
GUI j
DELAY 150
STRING orca-host-support
DELAY 400
ENTER
```

Sending `⏎` is justified by probe 10: for a unique query the highlighted row *is* the target
worktree, because the `WORKTREES` section ranks above tabs, settings, and the create row.

Both delays are load-bearing. The palette debounces its filtering (a 300 ms constant appears in
the palette module), so pressing `⏎` too early can act on the pre-filter row list — and per probes
9 and 10 that could be `Create worktree "<query>"`. `DELAY 400` is 300 ms plus margin; the exact
values get tuned on hardware and recorded in `docs/calibration.md`.

Because a query that matches nothing can *create* a worktree, uniqueness is enforced at two
points:

- **Build time** — `raft_board_init.py` computes each `query` and refuses to emit a board where a
  query matches zero or multiple worktrees.
- **Check time** — `raft_board_verify.py` re-runs that check against live Orca (~250 ms) and exits
  non-zero with a readable diff. Run it after renaming a branch or reshaping the board; it is also
  cheap enough to wire into `SessionStart` if the user wants the board self-policing.

Matching is approximated as a case-insensitive substring test over the fields Orca's palette
searches (worktree name, workspace label, repo name), which is *not* a perfect replica of Orca's
fuzzy matcher — hence the verifier existing at all rather than the generator being trusted.

The `⌘J` palette also honours `⌘1`–`⌘9` for its own visible rows, but those are the palette's rows,
not the sidebar's, and are subject to the same debounce race. Not used.

## Status model

### The race, and the merge rule that avoids it

Orca installs its own Claude Code hook (`~/.orca/agent-hooks/claude-hook.sh`, which POSTs the
payload to the Orca runtime) as a **sibling entry on the same events** as Raft's hook — Raft at
index 0, Orca at index 1. When Raft's hook runs, the runtime may not yet have applied the state
change Orca is being told about, so querying `worktree ps` alone would paint the *previous* state
for the session that just fired.

The orca adapter therefore merges two sources:

- **The firing worktree** (`$ORCA_WORKTREE_ID`) → the state the hook carried. Authoritative,
  zero-latency, immune to the race.
- **Every other slot** → `orca worktree ps --json`, Orca's own truth.

This is what buys the things pure hooks cannot: slots running Codex/Gemini/Droid panes light up
too, and an interrupted turn self-corrects on the next hook from *any* session instead of staying
amber forever.

### Orca agent state → LED

| Orca | Raft state | Color |
|---|---|---|
| `waiting` | `needs` | blue |
| `blocked` | `failed` | red |
| `working` | `working` | amber |
| `done` | `done` | green (fades to off) |
| `interrupted`, `idle` | `idle` | dim purple |
| no agent panes, or worktree missing | `off` | unlit |

- A worktree with several panes aggregates by **precedence in that table order** — `waiting`
  outranks everything, because it is the only state that wants you *now*.
- `agents[].interrupted == true` maps to `idle` regardless of reported `state`.
- A firing worktree that isn't a slot walks `parentWorktreeId` up to the nearest slot and lands
  there, so orchestration children light their parent's key. No ancestor on the board → repaint
  the other slots and skip it. Never guess a key.

### Fade

`done` → `off` survives but shrinks. A repaint is idempotent and derived from truth, so the
per-ordinal token bookkeeping stops being load-bearing on the Orca path: the fader becomes a
single detached "repaint the board again in N seconds" sleeper, and `agents[].updatedAt` lets a
repaint compute the remaining window rather than remember it. The cmux path keeps today's
token/fader machinery unchanged.

## Board ownership

The pad has one active profile, and the cmux and Orca profiles differ in their keystrokes. So the
board can only serve one host at a time, and if both hosts' hooks write LEDs the board lies — the
one thing Raft must not do.

**The pad's loaded profile is the declaration of which host owns the board.**

- HID command `0x00` already returns `current_profile` in response byte 11 (see
  `scripts/duckypad_probe.py`). `duckypad_led.py` reads it inside the device open it already
  performs — effectively free.
- `duckypad_push_profile.py` already maintains `/profile_info.txt` as `<number> <name>`. It gains
  the job of recording the number it assigned into a root-owned
  `/usr/local/libexec/duckypad_profiles.json` (`{"1": "cmux", "2": "orca"}`), so the mapping is
  generated rather than hand-maintained; `duckypad_led.py` falls back to a built-in default map if
  the file is absent.
- The hook passes its host: `duckypad_led.py --host orca --board 1:working 2:idle …`. If the
  loaded profile belongs to the other host, the write is **refused** and logged.
- An **unknown** profile number (a hand-made profile) is *allowed* and logged. Single-host users
  never trip the gate; dual-host users get the two generated profiles and correct gating.
- Switching profiles hands the raft over cleanly: the firmware patch already drops host LED
  overrides on profile switch while preserving them on same-profile reload, so no stale colors
  survive. The new owner's keys stay dark until its next hook fires — honest, and
  `scripts/duckypad_repaint.py` fills them in immediately.

## Batch LED write

```
duckypad_led.py --host <orca|cmux> --board 1:working 2:done 3:off 4:off 5:off
```

One device open, one profile check, up to five `0x04` packets. The whole board is written every
time — unconditional and idempotent, which is what makes it self-healing after an unplug, a sleep,
or a missed event. The write is wrapped in an `flock` so two sessions finishing at once can't
interleave two boards.

The single-key form (`duckypad_led.py 2 working`) stays for the cmux path and takes the same
optional `--host` gate. The calibration forms (`--index`, `--all-off`) bypass the gate — they are
deliberate manual operations.

## Key layout

Ten of fifteen keys talk to *Claude*, not the host, and are untouched: `Yes`, `No`, `/clear`,
`/compact`, `⇧Tab`, `Esc` (interrupt), `Esc Esc` (rewind). `profile_orca/` differs from
`profile_cmux/` in the top row plus two middle keys:

| Key | cmux | Orca |
|---|---|---|
| Top row ×5 | `⌘1`–`⌘5` | `⌘J` + `STRING <query>` + `⏎` (per slot, generated from `board.json`) |
| Unread / Jump | `⌘⇧U` | `⌘J` — Orca has no jump-to-unread, so this becomes the bare switcher |
| Next WS | `⌃⌘]` | `⌘⇧↓` (`worktree.navigateDown`) |
| New WS | `⌘N` | `⌘N` — same on both |

The generator becomes host-parameterised: a shared key table, a per-host overlay for those two
middle keys, and a top row generated per host (static `GUI <n>` for cmux, palette macro for orca).

## Edge cases

| Case | Behaviour |
|---|---|
| Both hosts installed, session in one | `detect()` resolves from the firing session's env; Orca short-circuits before cmux |
| Both hosts running, sessions in both | Profile gate: only the host matching the pad's loaded profile writes; the other logs and no-ops |
| `$RAFT_HOST=off` | Hook exits 0 without touching anything |
| Neither host | Unchanged: exit 0 silently |
| Orca app quit / runtime unreachable | `worktree ps` fails or times out (3 s) → paint only the firing worktree from its `board.json` slot; other slots left as-is |
| Orca CLI slow under load | Hooks are `async: true`, so latency is invisible; the 3 s timeout bounds it |
| Firing worktree not a slot | Walk `parentWorktreeId` to the nearest slot; else skip that key, still repaint the rest |
| Several agent panes in one worktree | Precedence: `waiting` > `blocked` > `working` > `done` > `interrupted`/`idle` |
| Agent interrupted | `interrupted == true` → dim purple, without waiting for the next prompt |
| Non-Claude agents (Codex, Gemini, Droid) | Lit from `worktree ps`; they never fire *our* hook, so their key updates on the next repaint any session triggers |
| Slot's worktree deleted or renamed | Status: key goes `off`. Outbound: `raft_board_verify.py` exits non-zero; until re-generated, that key's `⏎` could hit "Create worktree" (probe 9) |
| Orca reshuffles `sortOrder` or the sidebar tree | No effect — nothing in the design reads position any more |
| Board has fewer than 5 slots | Unlisted keys stay dark and send nothing |
| Two sessions repaint simultaneously | `flock` serialises the writes |
| Orca rewrites `~/.claude/settings.json` | Raft's entry sits at index 0 and coexists with Orca's today; a doctor check in `docs/` says how to confirm after an Orca upgrade |
| `terminalShortcutPolicy: terminal-first` | `⌘J` stops reaching Orca from a focused pane; documented as a requirement to leave it `orca-first` |
| Pad unplugged | Unchanged: `duckypad_led.py` no-ops silently, exit 0 |

## Still unverified

1. **Palette macro timing at machine speed.** The *semantics* are settled (probe 10): a unique
   query highlights its worktree, so `⏎` is safe for a verified board. What remains is timing — a
   human types slowly, whereas the pad emits `STRING` in milliseconds, so the `DELAY` values must
   be confirmed against the real debounce on hardware before the top row is trusted. Until then
   the two-press variant (type, don't send `⏎`) remains a one-line change in the generator.

   Residual risk, accepted: between a branch rename and the next `raft_board_verify.py` run, a key
   press can create a worktree named after the stale query. Recovery is `orca worktree rm`, so the
   severity is low; the README says to re-verify after renaming.
2. **Does Orca regenerate the `hooks` block on upgrade?** Raft's and Orca's entries coexist today.
   *Fallback:* documented check plus re-merging `hooks/settings.snippet.json`.
3. **Orca plugin API.** If plugins can register commands bound to keys (the keybinding validator
   accepts `plugin:<name>/<command>` ids), a small Orca plugin exposing "focus worktree X" would
   beat palette macros outright: one press, no debounce race, no create hazard. No plugin-authoring
   guide ships with the CLI, so this is parked, not dismissed.

## Testing

The repo has no test suite today; this adds a proportionate one, because the interesting logic is
pure and hardware-free:

- Capture real `orca worktree ps --json` / `worktree list --json` as fixtures, scrubbed of prompts
  and assistant messages (large and private).
- Unit tests, stdlib `unittest`: state precedence and aggregation; board resolution from
  `board.json` against fixtures; parent walk-up for off-board worktrees; `detect()` under each
  environment combination; fade-window arithmetic; query-uniqueness checking, including the
  ambiguous and no-match cases that must fail closed.
- Manual, on hardware: each top-row key lands on its worktree; a deliberately stale query is
  caught by `raft_board_verify.py` *before* it can create anything; the profile gate refuses the
  wrong host; profile switch clears colors; unplugged pad no-ops; parallel Claude-in-Orca sessions
  light the right keys.

## Documentation

`README.md` moves from "Claude Code in cmux" to "Claude Code in cmux **or** Orca", with a host
table, Orca setup (define your board, push `profile_orca`), and the honest statement that Orca
addressing is name-based because its sidebar index is neither positional nor readable. New
caveats: leave `terminalShortcutPolicy` on `orca-first`; re-run `raft_board_verify.py` after
renaming branches. The cmux `reorderOnNotification` caveat stays, scoped to cmux.
