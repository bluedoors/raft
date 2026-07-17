#!/usr/bin/env python3
"""Test the sleep-safe host-LED fix WITHOUT waiting for the sleep timeout.

Sets a few workspace keys to status colours, then sends goto_profile(current)
over HID — the same profile reload+repaint that wake-from-sleep performs. If the
host-override layer works, the colours survive the reload.

Run under sudo (CLOSE the Configurator first); needs 'pip install hidapi':
  sudo python3 duckypad_test_wake.py
"""
import sys, time, hid

VID, PID, CFG_USAGE, CFG_PAGE = 0x0483, 0xD11C, 0x3A, 0x0001

path = None
for d in hid.enumerate(VID, PID):
    if d.get("usage") == CFG_USAGE and d.get("usage_page") == CFG_PAGE:
        path = d["path"]; break
if not path:
    print("config interface not found (Configurator still open?)"); sys.exit(1)
h = hid.device(); h.open_path(path); h.set_nonblocking(0)

def buf(cmd): b=[0]*64; b[0]=5; b[2]=cmd; return b
def txrx(b): h.write(b); return h.read(64, timeout_ms=500)

# current profile number
r = txrx(buf(0x00)); cur = r[11] if r else 0
print(f"current profile = {cur}")

# set the 5 top-row workspace LEDs to distinct colours (idx 2,5,8,11,14)
top = {2:(255,0,0),5:(255,140,0),8:(0,120,255),11:(0,255,0),14:(160,0,255)}
for idx,(rr,gg,bb) in top.items():
    b=buf(0x04); b[3]=idx; b[4],b[5],b[6]=rr,gg,bb; txrx(b)
print("set top row to R / amber / blue / green / purple. LOOK NOW (5s)...")
time.sleep(5)

print(f"sending goto_profile({cur}) — simulates wake-from-sleep reload+repaint...")
b=buf(0x01); b[3]=cur; txrx(b)
time.sleep(1)
print("Did the top-row colours SURVIVE the reload? (fix works = yes; broken = reverted to profile)")
h.close()
