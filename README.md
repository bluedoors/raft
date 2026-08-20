# 🦆 Raft

**A [duckyPad](https://github.com/dekuNukem/duckyPad) turned into a live status + control surface for a *raft* of [Claude Code](https://www.anthropic.com/claude-code) agents — running in [cmux](https://github.com/manaflow-ai/cmux) or [Orca](https://www.onorca.dev).**

![Raft — an original duckyPad in landscape, its keys lit to show live Claude Code agent status per workspace](media/raft-hero.jpeg)

> *A group of ducks resting on the water is called a **raft**. This is your control raft: one physical key per workspace, its LED showing what that agent is doing right now, and a press to jump straight to it — plus a row of Claude Code action macros.*

The top row is per-workspace keys whose **LEDs show live agent status** (amber = working, blue = needs you, green = done, red = failed) and whose **presses jump to that workspace**. The lower rows are Claude Code + host action macros (new workspace, next workspace, jump/unread, plan mode, interrupt, yes/no, `/clear`, `/compact`, rewind).

**Two hosts, one board.** cmux and Orca are both supported, and the hook picks the right one from the firing session's own environment — no flag, no config. Which host owns the LEDs at any moment is decided by the profile loaded on the pad, so having both installed is fine. Each host gets its own generated profile: `profile_cmux/` and `profile_orca/`.

Inspired by **[OpenAI's Codex Micro](https://mashable.com/tech/openai-first-physical-release-is-micro-keyboard)** — OpenAI's first physical product, a Work Louder × OpenAI Supply macropad whose dedicated keys light up to show your coding agents' status. Raft reproduces the useful 80% — glanceable per-agent status + command keys — on an original (2020) duckyPad you may already own. (That's a Claude keycap on the *Yes* key in the photo.)

Raft is **built for Claude Code** — the status LEDs are driven by Claude Code lifecycle hooks and the action keys are Claude Code + host commands. But the firmware, LED protocol, and layout are **agent-agnostic**: point the hooks at another agent's events and swap the macro keys, and the same board works for Codex or anything else that can run a hook on start/stop/idle.

---

## The catch (and why this repo exists)

The obvious way to build this — have Claude Code hooks send the duckyPad's documented "Set RGB Single" HID command (`0x04`) to color each key — **does not work on stock firmware.** On the original duckyPad, that command is *defined in the firmware header and documented in the HID protocol, but never actually implemented*: the dispatcher has no branch for it, so it returns `UNKNOWN_CMD` (status 6) and nothing lights up. No stock OG-duckyPad firmware (v1.3.0 or the latest v3.0.4) can set a key's color from the host.

**Raft fixes that with a tiny custom firmware patch** that wires up the reserved command (plus keypress-persistence and a sleep-safe host-override layer), cross-compiled on macOS with a hand-rolled GNU toolchain setup. The minimal version of the patch is also being submitted upstream.

So the interesting half of this project is firmware; the rest is a small, no-daemon glue layer.

---

## How it works

Two independent channels, exactly like the Codex Micro's frosted status keys:

```
        ┌────────────────────────────── inbound (status) ──────────────────────────────┐
 Claude Code ── hook ──> duckypad_hook.py ──┬─ cmux:  cmux identify        ──> sudo duckypad_led.py <ws> <state>
 (SessionStart/            (detect host from │        (firing session → ordinal)         │
  Stop/Notification…)       the session env) └─ orca:  $ORCA_WORKTREE_ID               HID 0x04 → key LED
                                                      + orca worktree ps  ──> sudo duckypad_led.py --board 1:working 2:needs …
                                                       (repaints all five keys)

        └───────────────────────────── outbound (control) ─────────────────────────────┘
 duckyPad key ── USB HID keystroke ──> cmux (⌘1–5 jump) / Orca (⌘J + type a query + ⏎) / Claude Code (Esc, /clear, …)
```

- **Outbound** is just a normal USB-HID keyboard profile — no special software. On cmux the top row sends `⌘1`–`⌘5` to jump workspaces; on Orca it opens the ⌘J switch palette, types that slot's saved query, and presses ⏎. Other keys send Claude Code / host shortcuts.
- **Inbound, cmux**: the hook resolves *which workspace the firing session belongs to* via `cmux identify` (not the focused one — a background agent finishing still lights its own key) and sets that one key.
- **Inbound, Orca**: `worktree ps` is the source of truth, and the hook is only a trigger. On each event Raft reads every worktree's agent state and repaints **all five** keys in one batched write, so keys track agents Raft never saw start — including Codex or Gemini panes, which never fire a Claude hook. The firing session's own state comes from the hook payload rather than `ps`, because Orca installs a sibling hook on the same events and its own state write may not have landed yet.
- Either way, opening the HID interface needs root on macOS, so the LED writer runs behind a locked-down NOPASSWD-sudo helper. Each call opens/closes the device (no daemon, no persistent handle), and no-ops silently when the pad is unplugged.

---

## Key layout — the `cmux` profile

Held in **landscape with the USB cable at top-left** (this is the default profile in
[`profile/profile_cmux/`](profile/profile_cmux); edit [`profile/duckypad_build_profile.py`](profile/duckypad_build_profile.py) to change it). The Orca profile differs in three keys — see [below](#key-layout--the-orca-profile).

```
┌────────┬────────┬────────┬────────┬────────┐
│  WS1   │  WS2   │  WS3   │  WS4   │  WS5   │  ← workspace status LEDs + jump (⌘1–5)
├────────┼────────┼────────┼────────┼────────┤
│ Unread │ New WS │ Next WS│ Rewind │ Intrpt │  ← navigation / actions
├────────┼────────┼────────┼────────┼────────┤
│  Yes   │   No   │ /clear │compact │ Auto/Pl│  ← Claude Code actions
└────────┴────────┴────────┴────────┴────────┘
```

| Key | Sends | Does | LED |
|---|---|---|---|
| **WS1–WS5** (top row) | `⌘1`–`⌘5` | Jump to cmux workspace 1–5 | **live agent status** — amber = working, blue = needs you, green = done (fades to off after 2 min), red = failed |
| Unread | `⌘⇧U` | Jump to most-recent unread workspace | static |
| New WS | `⌘N` | New cmux workspace | static |
| Next WS | `⌃⌘]` | Next workspace | static |
| Rewind | `Esc` `Esc` | Open the rewind / checkpoint picker | static |
| Intrpt | `Esc` | Interrupt Claude | static |
| Yes | types `yes` ⏎ | Confirm a prompt | static |
| No | types `no` ⏎ | Decline a prompt | static |
| /clear | `/clear` ⏎ | Clear the conversation | static |
| /compact | `/compact` ⏎ | Compact the conversation | static |
| Auto/Pl | `⇧Tab` | Cycle Claude Code permission mode (normal → auto-accept → plan) | static |

The top row is the heart of it: each key both **shows** a workspace's agent status (its LED) and **jumps** to it (its keystroke). The lower rows only depend on which workspace you just focused — jump with the top row, then act.

> **Physical-key mapping:** in this landscape orientation the profile files map by physical key number — top row = `key3/6/9/12/15`, middle = `key2/5/8/11/14`, bottom = `key1/4/7/10/13` — and LED index = key-file number − 1. See [`docs/calibration.md`](docs/calibration.md).

---

## Key layout — the `orca` profile

The bottom row (Claude Code actions) and `New WS` / `Rewind` / `Intrpt` are identical. Three keys differ, because Orca cannot be addressed positionally:

| Key | Sends | Does | LED |
|---|---|---|---|
| **top row** | `⌘J`, then types the slot's query, then ⏎ | Switch to the worktree that query uniquely matches | **live agent status**, same colors, plus dim purple = idle |
| Jump (was Unread) | `⌘J` | Open the switch palette and leave it open — Orca has no jump-to-unread | static |
| Next WT (was Next WS) | `⌘⇧↓` | Next worktree | static |

Top-row **labels come from your board**, not from the code: each key is named after the worktree you assigned to it, truncated to the pad's 7-character limit. Unassigned slots are inert and unlabelled (`--`).

The board is five lines of JSON at `~/.config/raft/board.json` — Raft's own ordering, deliberately not Orca's:

```json
{ "host": "orca",
  "slots": [ { "label": "raft",   "worktree": "<worktreeId>", "query": "raft" },
             { "label": "gateway","worktree": "<worktreeId>", "query": "fix/vpc-reuse" } ] }
```

`query` is what the pad types into the palette; `worktree` is the composite id that `orca worktree ps --json` reports, which is how the LED for that slot is resolved. Generate the file with [`scripts/raft_board_init.py`](scripts/raft_board_init.py) rather than hand-writing ids.

> **Why type a name instead of pressing ⌘2?** Orca's `⌘1`–`⌘9` select the *n*-th visible row of a project→repo→worktree tree, so the target depends on scroll position, which groups are collapsed, and an internal `sortOrder` that Orca renumbers on its own (observed twice in half an hour, unprompted). A name-addressed board is stable across all of that; a positional one silently drifts.

---

## What you need

- An **original duckyPad (2020)** — STM32F072, 15 keys, per-key RGB. (Not the Pro; that's a different MCU/flow.)
- **macOS** (the sender/hooks assume it; the firmware is cross-platform).
- **cmux** *or* **Orca** with Claude Code sessions. (Both installed is fine — see [Known limitations](#known-limitations).)
- Toolchain: `brew install --cask gcc-arm-embedded`, `brew install dfu-util`, and a Python 3.10+ with `pip install hidapi`.

---

## Reproduce it

Four stages — each directory has its own README with exact commands.

1. **Firmware** → [`firmware/README.md`](firmware/README.md)
   Clone `dekuNukem/duckyPad` (base commit `46dffb33`), copy in the GCC build files, apply [`firmware/raft-firmware.patch`](firmware/raft-firmware.patch), `make`, and DFU-flash. This gives you host-controllable per-key LEDs.

2. **Sender + hooks** → [`sender/README.md`](sender/README.md)
   `sudo bash sender/duckypad_install.sh` installs the root-owned LED writer + a tightly-scoped `/etc/sudoers.d/duckypad`. Then merge [`hooks/settings.snippet.json`](hooks/settings.snippet.json) into `~/.claude/settings.json`.

3. **Profile** → [`profile/README.md`](profile/README.md)
   Generate the 15-key profile from source (no GUI clicking) — duckyScript is compiled to `.dsb` byte-for-byte with the Configurator's own compiler — and push it over HID. `--host cmux` (default) or `--host orca`; you can push both and switch with the pad's +/- buttons.

4. **Calibrate & test** → [`docs/calibration.md`](docs/calibration.md)
   Confirm the LED→key map for your orientation, then run parallel Claude sessions and watch the raft light up.

### Extra step for Orca: declare your board

Orca has no stable positional addressing, so you tell Raft which five worktrees the top row owns. This is the only host-specific setup.

```bash
# 1. see what Orca currently has, with a suggested unique query per worktree
python3 scripts/raft_board_init.py --list

# 2. write ~/.config/raft/board.json (up to 5 selectors, left→right)
python3 scripts/raft_board_init.py --slots raft fix/vpc-reuse sa-assist radar

# 3. generate + push the Orca profile (labels and macros come from the board)
RAFT_CONFIG_SRC=/path/to/duckyPad-Configurator/src \
  python3 profile/duckypad_build_profile.py --host orca
sudo python3 profile/duckypad_push_profile.py --profile orca

# 4. select the 'orca' profile on the pad, then fill the board in immediately
python3 scripts/duckypad_repaint.py
```

`raft_board_init.py` **refuses** any selector that matches more than one worktree, because an ambiguous query is not merely imprecise — see the create hazard below. Re-run [`scripts/raft_board_verify.py`](scripts/raft_board_verify.py) whenever you rename a branch or reshape the board; it exits non-zero and names the problem. Editing `board.json` by hand is fine (the `label` in particular — it is only cosmetic), but rebuild and re-push the profile afterwards so the pad's macros match.

---

## Layout

```
firmware/   raft-firmware.patch + GNU build (Makefile.gcc, linker script, GCC startup)
sender/     duckypad_led.py (LED writer), duckypad_hook.py (host→LED bridge), duckypad_install.sh
profile/    build/compile/push scripts + the generated profile_cmux/ and profile_orca/
hooks/      settings.snippet.json (the Claude Code hook block to merge)
scripts/    raft_board_*.py (Orca board), duckypad_repaint.py, probe / status / led-test diagnostics
tests/      stdlib unittest suite — python3 -m unittest discover -s tests
docs/       calibration, teardown, superpowers/ (design + implementation plan)
```

---

## Known limitations

- **OLED stays portrait.** The firmware has no 90° OLED rotation, so held in landscape the OLED text reads sideways. The keys and LEDs are laid out for landscape; the OLED is a secondary channel (blank keycaps + LED color are the real interface).
- **Uses flash beyond the datasheet spec.** The GCC/newlib image (~76 KB) exceeds the STM32F072C8's 64 KB spec. This die physically exposes 128 KB (the DFU descriptor reports it) and it's readback-verified on the test unit — but it's *technically out-of-spec*, so verify the readback on your own device. Fully recoverable: DFU is always available.
- **Interrupt leaves it amber (cmux).** Claude Code fires no hook when you interrupt a turn, so an interrupted session stays "working" until your next prompt (then self-corrects). Accepted, not worked around. On Orca this self-heals on the next event from *any* session, because `worktree ps` reports `interrupted` and every event repaints the whole board — an interrupted worktree shows dim purple.
- **One key, several panes: the loudest state wins.** An Orca worktree can hold several agent panes, but it has only one LED, so Raft reduces them by precedence — `waiting` → `blocked` → `working` → `done` → `interrupted` → `idle`. Note `done` outranks `interrupted`: interrupt one pane while a sibling pane has just finished, and the key stays green until that green goes stale, rather than turning purple. Single-pane worktrees, which is the normal case, are unaffected.
- **Green auto-fades to off.** A finished (green) LED switches itself off 2 min after the turn ends (`DUCKYPAD_FADE_SEC` to tune), so stale green doesn't linger. Red (failed) does **not** fade; it stays lit until the next state. cmux does this with a detached, token-cancelled fader — any newer state supersedes the pending fade. Orca needs no such bookkeeping: staleness is a pure function of `ps` output plus the clock, so the hook just schedules an idempotent repaint for when the oldest green expires.
- **cmux only: requires `reorderOnNotification` off.** On cmux both channels address workspaces by *sidebar position* — the LED writer via `index+1` and the ⌘1–5 jump via cmux's "select workspace N". cmux's `app.reorderOnNotification` (default **on**) bubbles a workspace to the top when it needs attention, which renumbers positions and desyncs the physical board. Set `"app": { "reorderOnNotification": false }` in `~/.config/cmux/cmux.json` and `cmux reload-config`. Raft's status LEDs replace what bubbling gave you. (Positions still shift if you *close* a middle workspace or drag rows — inherent to positional addressing.) **Orca needs none of this**, because its board is name-addressed.
- **Orca is addressed by name, not position.** `⌘1`–`⌘9` index the *visible* rows of a project→repo→worktree tree, and neither the row order, the collapse state, nor the `sortOrder` Orca renumbers on its own is exposed by its CLI — so there is nothing stable to count. Hence `board.json` and the typed-query macros.
- **A stale Orca board query can *create* a worktree.** Orca's ⌘J palette offers "create a worktree" when a query matches nothing, and it is a plain list row — so the pad's ⏎ can select it. Renaming a branch is enough to break a query. Re-run `python3 scripts/raft_board_verify.py` after any rename; if a key does create one, `orca worktree rm` it and regenerate the profile with `--no-enter` for a deliberate two-press variant.
- **Ambiguous Orca queries are non-stationary.** With a query, Orca ranks matches by field tier (title, then branch/secondary text, then repo/workspace) and match position, breaking ties by most-recently-visited. So an ambiguous query's *winner changes with your browsing history* — which is why `raft_board_init.py` refuses ambiguity rather than warning about it. Unique queries are immune. `raft_board_verify.py` models the tiers Orca exposes but not its type aliases, so treat it as a strong check, not a proof.
- **Leave Orca's `terminalShortcutPolicy` on its default `orca-first`.** Set to terminal-first, ⌘J is delivered to the focused pane instead of Orca and the top row stops working from inside a session — exactly where you press it. Expect a cosmetic "Terminal shortcut handled by Orca" toast when you do; it dismisses itself.
- **The pad's loaded profile decides who owns the board.** With both hosts installed, the LED writer reads the pad's current profile over HID and refuses writes from the other host, so a cmux session cannot repaint your Orca board. Profiles Raft did not push are treated as unowned and allowed, so a hand-made profile never locks you out.
- **Orca ships its own Claude Code hook** on the same lifecycle events, as a sibling entry in the same `~/.claude/settings.json`. Raft's entry survived the 1.4.184 → 1.4.185 upgrade here, but after any Orca upgrade run the one-liner in [`docs/calibration.md`](docs/calibration.md#after-an-orca-upgrade) to confirm it is still there.
- **Sleep.** Set the pad's sleep to a long value or Never — waking reloads the profile; the firmware's host-override layer re-asserts status colors on same-profile wake, but Never avoids the whole question.

---

## Credits

- [duckyPad](https://github.com/dekuNukem/duckyPad) by dekuNukem — the hardware and firmware this builds on (MIT).
- [cmux](https://github.com/manaflow-ai/cmux) and [Orca](https://www.onorca.dev) — the workspace/worktree managers Raft reads status from.
- Concept inspiration: [OpenAI's Codex Micro](https://mashable.com/tech/openai-first-physical-release-is-micro-keyboard) (Work Louder × OpenAI Supply) — OpenAI's first physical product.

## License

MIT — see [LICENSE](LICENSE). The firmware patch applies on top of dekuNukem/duckyPad (also MIT).
