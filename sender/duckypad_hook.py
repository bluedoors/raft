#!/usr/bin/env python3
"""duckypad_hook.py — Claude Code hook bridge for the duckyPad status LEDs.

Invoked by Claude Code lifecycle hooks (SessionStart/UserPromptSubmit/
Notification/Stop/SessionEnd). Resolves the FIRING SESSION's own cmux workspace
ordinal (not the focused one) via `cmux identify`, then sets that workspace's
duckyPad key LED by sudo-ing the root-owned LED script.

  duckypad_hook.py <state>        # state: working|needs|done|failed|idle|off
  duckypad_hook.py notify         # Notification event: reads payload, picks needs vs idle
  duckypad_hook.py --resolve      # print resolved ordinal (debug), no LED
  duckypad_hook.py --fade <ord> <token>  # internal: delayed green->off fader (self-spawned)

Runs as the user (needs the cmux env that Claude Code hooks inherit); the LED
write happens as root inside duckypad_led.py. No-ops silently (exit 0) if cmux
or the pad is absent, so it's safe to wire into hooks unconditionally.
"""
import os
import sys
import json
import time
import subprocess
import datetime

LOG = "/tmp/duckypad_hook.log"


def _log(msg):
    try:
        with open(LOG, "a") as f:
            f.write(f"{datetime.datetime.now().isoformat()} {msg}\n")
    except Exception:
        pass

CMUX = os.environ.get("CMUX_BIN", "/Applications/cmux.app/Contents/Resources/bin/cmux")
LED_SCRIPT = "/usr/local/libexec/duckypad_led.py"
# Root-owned venv interpreter (pinned in /etc/sudoers.d/duckypad). Must match
# the sudoers entry exactly. Built on the system /usr/bin/python3 (root:wheel).
LED_PY = "/usr/local/libexec/duckypad-venv/bin/python3"
VALID_STATES = {"working", "needs", "done", "failed", "idle", "off"}

# ── Orca host: agent state → LED state ───────────────────────────────────────
# Orca's per-pane enum, in the order we resolve conflicts. A worktree can hold
# several agent panes; the highest-precedence one owns the key, because a pane
# that WANTS you outranks one that is merely busy or finished.
ORCA_PRECEDENCE = ("waiting", "blocked", "working", "done", "interrupted", "idle")
ORCA_TO_RAFT = {
    "waiting":     "needs",    # blue: wants you now
    "blocked":     "failed",   # red: can't proceed
    "working":     "working",  # amber
    "done":        "done",     # green (fades — see orca_led_state)
    "interrupted": "idle",     # dim purple
    "idle":        "idle",     # dim purple
}

# The "done" green is transient: hold it, then switch the WS LED to FADE_TO so a
# stale green doesn't linger. Implemented as a self-spawned detached fader (no
# daemon). Cancellation is token-based: every state change stamps a fresh token
# for the ordinal, and the fader only acts if the token is still current when it
# wakes — so a later working/needs/idle/off supersedes a pending fade.
FADE_STATE = "done"
FADE_TO = "off"
FADE_DELAY_SEC = int(os.environ.get("DUCKYPAD_FADE_SEC", "120"))
STATE_DIR = "/tmp/duckypad_state"

# Notification substate: split an idle "done, waiting for you" notice (-> idle,
# dim purple) from a real permission/approval prompt (-> needs, blue). Keyed off
# the payload's `notification_type` (the robust, documented field). The message
# text is only a fallback for older Claude Code builds that omit the type.
IDLE_NOTIFICATION_TYPES = ("idle_prompt", "agent_completed")
NEEDS_NOTIFICATION_TYPES = ("permission_prompt", "agent_needs_input", "elicitation_dialog")
# Fallback substrings (case-insensitive) — matches the real idle_prompt message
# "Claude is done and waiting for your next prompt." plus older phrasings.
IDLE_MESSAGE_MARKERS = ("waiting for your next prompt", "waiting for your input",
                        "is done and waiting")


def _cmux_json(args):
    env = {**os.environ, "CMUX_QUIET": "1"}
    out = subprocess.run([CMUX, *args], capture_output=True, text=True,
                         timeout=3, env=env).stdout
    return json.loads(out)


def resolve_ordinal():
    """Session's workspace ordinal (index+1, matches the Cmd-N jump), or None."""
    try:
        ident = _cmux_json(["identify", "--json"])
        ref = ident["caller"]["workspace_ref"]
        wl = _cmux_json(["workspace", "list", "--json"])
        for w in wl.get("workspaces", []):
            if w.get("ref") == ref:
                return int(w["index"]) + 1
    except Exception:
        return None
    return None


def _agent_state(agent):
    """The precedence key for one pane. `interrupted` overrides the report."""
    if agent.get("interrupted"):
        return "interrupted"
    state = (agent.get("state") or "").lower()
    return state if state in ORCA_TO_RAFT else None


def orca_led_state(agents, now_ms=None, fade_sec=None):
    """Aggregate one worktree's agent panes into a single LED state.

    A `done` older than the fade window resolves to "off" here rather than being
    remembered somewhere: the mapping is a pure function of Orca's truth plus the
    clock, so any repaint lands in the right place without bookkeeping.
    """
    if not agents:
        return "off"
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    if fade_sec is None:
        fade_sec = FADE_DELAY_SEC

    best = None
    for agent in agents:
        state = _agent_state(agent)
        if state is None:
            continue
        if state == "done":
            updated = agent.get("updatedAt")
            if isinstance(updated, int) and now_ms - updated >= fade_sec * 1000:
                continue                      # stale green: as good as no pane
        if best is None or ORCA_PRECEDENCE.index(state) < ORCA_PRECEDENCE.index(best):
            best = state
    return ORCA_TO_RAFT[best] if best else "off"


def fade_deadline_ms(agents, fade_sec=None):
    """Epoch ms at which the earliest live `done` in this list turns off."""
    if fade_sec is None:
        fade_sec = FADE_DELAY_SEC
    stamps = [a.get("updatedAt") for a in (agents or [])
              if _agent_state(a) == "done" and isinstance(a.get("updatedAt"), int)]
    return min(stamps) + fade_sec * 1000 if stamps else None


def detect(env=None, cmux_probe=None):
    """Which host owns this session? Resolved from the FIRING session's env.

    Orca is checked before cmux and short-circuits it: `cmux identify` reports a
    caller, but a stale or fallback answer would silently light the wrong key, and
    an Orca session is unambiguous.
    """
    env = os.environ if env is None else env
    forced = (env.get("RAFT_HOST") or "").lower()
    if forced == "off":
        return None
    if forced in ("orca", "cmux"):
        return forced
    if env.get("ORCA_WORKTREE_ID"):
        return "orca"
    probe = cmux_probe or resolve_ordinal
    try:
        if probe():
            return "cmux"
    except Exception:
        pass
    return None


# ── Orca host: the board ─────────────────────────────────────────────────────
# Orca's ⌘N indexes visible worktree rows in a project→repo→worktree tree, and
# neither that order nor the collapse state is readable from its CLI, so Raft
# owns the key→worktree mapping instead of mirroring the sidebar.
BOARD_PATH = os.path.expanduser("~/.config/raft/board.json")
MAX_SLOTS = 5


def load_board(path=None):
    """Read the Orca board. Returns [] on anything unexpected — never raises."""
    try:
        with open(path or BOARD_PATH) as f:
            doc = json.load(f)
        if (doc.get("host") or "").lower() != "orca":
            return []                      # not ours: a stray or half-migrated file
        slots = []
        for entry in doc.get("slots") or []:
            wt = entry.get("worktree")
            if not wt:
                continue                   # a slot with no worktree can't be lit
            slots.append({"label": entry.get("label") or "",
                          "worktree": wt,
                          "query": entry.get("query") or ""})
        return slots[:MAX_SLOTS]
    except Exception:
        return []


def resolve_slot(board, worktree_id, ps_by_id):
    """1-based ordinal for worktree_id, walking parents; None if off-board."""
    index = {slot["worktree"]: i + 1 for i, slot in enumerate(board)}
    seen = set()
    current = worktree_id
    while current and current not in seen:
        if current in index:
            return index[current]
        seen.add(current)
        current = (ps_by_id.get(current) or {}).get("parentWorktreeId")
    return None


def orca_board(board, ps_worktrees, firing_id=None, firing_state=None, now_ms=None):
    """{ordinal: led_state} for every slot.

    Orca's runtime may not have applied the firing session's change yet (our hook
    and Orca's own hook are siblings on the same event), so the firing worktree's
    state comes from the hook payload and everyone else's from `worktree ps`.
    """
    if not board:
        return {}
    ps_by_id = {w.get("worktreeId"): w for w in ps_worktrees or []}
    result = {}
    for ordinal, slot in enumerate(board, start=1):
        entry = ps_by_id.get(slot["worktree"])
        result[ordinal] = orca_led_state((entry or {}).get("agents"), now_ms=now_ms)
    if firing_id and firing_state:
        own = resolve_slot(board, firing_id, ps_by_id)
        if own is not None:
            result[own] = firing_state
    return result


def _tok_path(ordinal):
    return os.path.join(STATE_DIR, f"{ordinal}.tok")


def _write_token(ordinal):
    """Stamp a fresh token for this ordinal; returns it (invalidates any pending fade)."""
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        tok = f"{time.time_ns()}-{os.getpid()}"
        with open(_tok_path(ordinal), "w") as f:
            f.write(tok)
        return tok
    except Exception:
        return None


def _read_token(ordinal):
    try:
        with open(_tok_path(ordinal)) as f:
            return f.read().strip()
    except Exception:
        return None


def _set_led(ordinal, state):
    """Root LED write via the pinned NOPASSWD-sudo helper. Returns rc or None."""
    try:
        r = subprocess.run(["sudo", "-n", LED_PY, LED_SCRIPT, str(ordinal), state],
                           timeout=5, capture_output=True, text=True)
        return r
    except Exception as e:
        _log(f"SET_LED ordinal={ordinal} state={state} EXC={e!r}")
        return None


def _spawn_fader(ordinal, token):
    """Detached child that waits, then fades if its token is still current."""
    try:
        subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "--fade", str(ordinal), token],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True,
        )
    except Exception as e:
        _log(f"FADE spawn EXC={e!r}")


def run_fader(ordinal, token):
    """Wait FADE_DELAY_SEC, then switch ordinal to FADE_TO iff token is unchanged."""
    time.sleep(FADE_DELAY_SEC)
    cur = _read_token(ordinal)
    if cur != token:
        _log(f"FADE ordinal={ordinal} superseded (token {token!r} != {cur!r}) — skip")
        return
    r = _set_led(ordinal, FADE_TO)
    rc = getattr(r, "returncode", None)
    _log(f"FADE ordinal={ordinal} -> {FADE_TO} sudo_rc={rc}")


def main(argv):
    # Internal self-spawned fader: waits, then fades one ordinal. No payload/LED
    # resolution needed; handled before anything else.
    if argv and argv[0] == "--fade":
        if len(argv) >= 3:
            try:
                run_fader(int(argv[1]), argv[2])
            except Exception as e:
                _log(f"FADE EXC={e!r}")
        return 0

    # Read the hook payload (JSON on stdin). Needed for the Notification event to
    # tell an idle "waiting for input" notice from a real permission prompt.
    payload = ""
    try:
        if not sys.stdin.isatty():
            payload = sys.stdin.read()
    except Exception:
        pass

    if not argv:
        return 0

    if argv[0] == "--resolve":
        print(resolve_ordinal())
        return 0

    mode = argv[0].lower()
    if mode == "notify":
        # Prefer the documented `notification_type`; fall back to message text
        # only when it's absent (older Claude Code). idle_prompt -> idle (purple),
        # permission_prompt -> needs (blue), other known attention types -> needs.
        ntype, msg = "", ""
        try:
            p = json.loads(payload)
            ntype = (p.get("notification_type") or "").lower()
            msg = (p.get("message") or "").lower()
        except Exception:
            pass
        if ntype in IDLE_NOTIFICATION_TYPES:
            state = "idle"
        elif ntype in NEEDS_NOTIFICATION_TYPES:
            state = "needs"
        elif ntype:
            # A typed notification we don't specifically map (auth_success, etc.).
            # Default to needs (attention) — harmless over-signal, self-corrects.
            state = "needs"
        else:
            # No type on the payload: fall back to the message-text heuristic.
            state = "idle" if any(m in msg for m in IDLE_MESSAGE_MARKERS) else "needs"
        _log(f"NOTIFY type={ntype!r} msg={msg[:120]!r} -> {state}")
    else:
        state = mode

    if state not in VALID_STATES:
        _log(f"FIRED state={argv[0]!r} INVALID_STATE")
        return 0

    ordinal = resolve_ordinal()
    if ordinal is None:
        _log(f"FIRED state={state} ordinal=None (no cmux workspace resolved)")
        return 0                      # not in a cmux workspace → nothing to light

    # Stamp a fresh token BEFORE writing: this supersedes any fader still pending
    # for this ordinal (e.g. a new prompt cancelling a prior done's fade-to-off).
    token = _write_token(ordinal)

    r = _set_led(ordinal, state)
    rc, err = getattr(r, "returncode", None), getattr(r, "stderr", "") or ""
    _log(f"FIRED state={state} ordinal={ordinal} sudo_rc={rc} stderr={err.strip()!r}")

    # Green is transient: schedule the delayed switch to FADE_TO.
    if state == FADE_STATE and token is not None:
        _spawn_fader(ordinal, token)
        _log(f"FADE scheduled ordinal={ordinal} in {FADE_DELAY_SEC}s -> {FADE_TO}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
