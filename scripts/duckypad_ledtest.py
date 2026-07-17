#!/usr/bin/env python3
"""duckyPad LED hold-test — sets colors and HOLDS them (no restore) so a
blink-too-fast explanation is ruled out. Needs 'pip install hidapi'. Run under sudo:
  sudo python3 duckypad_ledtest.py"""
import hid, time, sys

VID, PID, CFG_USAGE, CFG_PAGE = 0x0483, 0xd11c, 0x3a, 0x0001

path = None
for d in hid.enumerate(VID, PID):
    if d.get('usage') == CFG_USAGE and d.get('usage_page') == CFG_PAGE:
        path = d['path']; break
if not path:
    print("FAIL: no config interface (usage 0x3A)"); sys.exit(1)

h = hid.device(); h.open_path(path); h.set_nonblocking(0)

def buf64(cmd):
    b = [0]*64; b[0]=0x05; b[2]=cmd; return b
def set_led(idx, r, g, b):
    p = buf64(0x04); p[3]=idx; p[4],p[5],p[6]=r,g,b
    h.write(p); resp = h.read(64, timeout_ms=200)
    return resp[2] if resp else None

print("STEP A: key index 0 -> bright WHITE, holding 6s. LOOK NOW.")
st = set_led(0, 255, 255, 255)
print(f"  0x04 status for key0 = {st} (0=ok)")
time.sleep(6)

print("STEP B: ALL 15 keys -> GREEN, holding 6s. LOOK NOW.")
for i in range(15):
    set_led(i, 0, 255, 0)
time.sleep(6)

print("STEP C: clearing all to off.")
for i in range(15):
    set_led(i, 0, 0, 0)
h.close()
print("done. Report: did you see WHITE key0 (A), then all-GREEN (B)?")
