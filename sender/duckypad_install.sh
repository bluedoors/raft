#!/bin/bash
# Installs the duckyPad LED sender behind NOPASSWD sudo (plan §6-A).
# Run once with interactive sudo:   sudo bash duckypad_install.sh
#
# Creates a ROOT-OWNED venv (on the root-owned system python) with hidapi, installs
# the LED script root:wheel + non-user-writable, and adds a tightly-scoped sudoers
# entry so Claude Code hooks can set LEDs without a password. Teardown: see TEARDOWN.md.
set -euo pipefail

LIBEXEC=/usr/local/libexec
VENV="$LIBEXEC/duckypad-venv"
SRC="$(cd "$(dirname "$0")" && pwd)/duckypad_led.py"
TARGET="$LIBEXEC/duckypad_led.py"
SUDOERS=/etc/sudoers.d/duckypad
RUN_USER="${SUDO_USER:?run with sudo}"

[ "$(id -u)" -eq 0 ] || { echo "must run as root (use sudo)"; exit 1; }
[ -f "$SRC" ] || { echo "source not found: $SRC"; exit 1; }

echo "==> creating root-owned venv at $VENV"
mkdir -p "$LIBEXEC"
/usr/bin/python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --disable-pip-version-check hidapi

echo "==> installing LED script root:wheel, mode 755"
install -o root -g wheel -m 755 "$SRC" "$TARGET"

echo "==> locking down venv ownership (root:wheel, no group/other write)"
chown -R root:wheel "$VENV"
chmod -R go-w "$VENV"

echo "==> writing sudoers entry $SUDOERS for user '$RUN_USER'"
umask 337
cat > "$SUDOERS" <<EOF
# Allow $RUN_USER to set duckyPad LEDs (Claude Code status hooks) without a password.
# Interpreter + script are both root-owned and non-user-writable.
$RUN_USER ALL=(root) NOPASSWD: $VENV/bin/python3 $TARGET *
EOF
chown root:wheel "$SUDOERS"
chmod 440 "$SUDOERS"

echo "==> validating sudoers syntax"
visudo -c -f "$SUDOERS"

echo "==> smoke test: exercise the NOPASSWD rule AS $RUN_USER (set WS1=done, then off)"
# Drop to the user, then have THAT user sudo -n — this actually tests the sudoers entry.
sudo -u "$RUN_USER" sudo -n "$VENV/bin/python3" "$TARGET" 1 done \
  && echo "   NOPASSWD sudo works ✅" || echo "   NOPASSWD sudo FAILED ❌"
sleep 1
sudo -u "$RUN_USER" sudo -n "$VENV/bin/python3" "$TARGET" --all-off || true

echo "INSTALL OK"
