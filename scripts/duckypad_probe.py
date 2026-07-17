#!/usr/bin/env python3
"""duckyPad HID probe — reads firmware version and blinks keys 0-4.
Run with:  sudo python3 duckypad_probe.py   (needs 'pip install hidapi')
Purpose: determine whether opening the duckyPad HID config interface requires root on macOS.
Read-only except a brief LED blink that is restored afterward."""
import hid, time, sys

VID, PID, CFG_USAGE, CFG_PAGE = 0x0483, 0xd11c, 0x3a, 0x0001

path = None
for d in hid.enumerate(VID, PID):
    if d.get('usage') == CFG_USAGE and d.get('usage_page') == CFG_PAGE:
        path = d['path']; break
if not path:
    print("FAIL: no config interface (usage 0x3A) enumerated"); sys.exit(1)

def buf64(cmd):
    b = [0] * 64; b[0] = 0x05; b[2] = cmd; return b

h = hid.device()
try:
    h.open_path(path)
except Exception as e:
    print(f"OPEN FAILED even under this context: {e}")
    print(">> If this ran under sudo and still failed, root alone is NOT the fix.")
    sys.exit(2)

h.set_nonblocking(0)
h.write(buf64(0x00))
r = h.read(64, timeout_ms=500)
if not r or r[0] != 0x04:
    print("OPEN OK but no valid query-info response:", list(r)[:8] if r else r); h.close(); sys.exit(3)

status, fw, hwrev, cur = r[2], f"{r[3]}.{r[4]}.{r[5]}", r[6], r[11]
print(f"OPEN OK  ✅   status={status}   firmware=v{fw}   hw_rev={hwrev}   current_profile={cur}")

def set_led(idx, rgb):
    b = buf64(0x04); b[3] = idx; b[4], b[5], b[6] = rgb; h.write(b); h.read(64, timeout_ms=200)
def goto_profile(n):
    b = buf64(0x01); b[3] = n; h.write(b); h.read(64, timeout_ms=200)

colors = [(255, 0, 0), (255, 140, 0), (0, 180, 255), (0, 255, 0), (160, 0, 255)]
print("blinking keys 0-4 twice ...")
for _ in range(2):
    for i, c in enumerate(colors): set_led(i, c)
    time.sleep(0.45)
    for i in range(5): set_led(i, (0, 0, 0))
    time.sleep(0.2)
goto_profile(cur)              # restore profile default backlight
print(f"restored profile {cur} — done")
h.close()
