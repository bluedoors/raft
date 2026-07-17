#!/usr/bin/env python3
"""duckypad_hook.py — Claude Code hook bridge for the duckyPad status LEDs.

Invoked by Claude Code lifecycle hooks (SessionStart/UserPromptSubmit/
Notification/Stop/SessionEnd). Resolves the FIRING SESSION's own cmux workspace
ordinal (not the focused one) via `cmux identify`, then sets that workspace's
duckyPad key LED by sudo-ing the root-owned LED script.

  duckypad_hook.py <state>        # state: working|needs|done|off
  duckypad_hook.py --resolve      # print resolved ordinal (debug), no LED

Runs as the user (needs the cmux env that Claude Code hooks inherit); the LED
write happens as root inside duckypad_led.py. No-ops silently (exit 0) if cmux
or the pad is absent, so it's safe to wire into hooks unconditionally.
"""
import os
import sys
import json
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
VALID_STATES = {"working", "needs", "done", "off"}


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


def main(argv):
    # Drain stdin (hooks pipe JSON); we don't need it — cmux identify is the key.
    try:
        if not sys.stdin.isatty():
            sys.stdin.read()
    except Exception:
        pass

    if not argv:
        return 0

    if argv[0] == "--resolve":
        print(resolve_ordinal())
        return 0

    state = argv[0].lower()
    if state not in VALID_STATES:
        _log(f"FIRED state={argv[0]!r} INVALID_STATE")
        return 0

    ordinal = resolve_ordinal()
    if ordinal is None:
        _log(f"FIRED state={state} ordinal=None (no cmux workspace resolved)")
        return 0                      # not in a cmux workspace → nothing to light

    try:
        r = subprocess.run(["sudo", "-n", LED_PY, LED_SCRIPT, str(ordinal), state],
                           timeout=5, capture_output=True, text=True)
        _log(f"FIRED state={state} ordinal={ordinal} sudo_rc={r.returncode} "
             f"stderr={r.stderr.strip()!r}")
    except Exception as e:
        _log(f"FIRED state={state} ordinal={ordinal} EXC={e!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
