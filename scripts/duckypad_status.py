#!/usr/bin/env python3
"""Report duckyPad USB/HID presence: HID interfaces (VID 0x0483) and DFU state.
Read-only, no sudo needed. Needs 'pip install hidapi'. Run:
  python3 duckypad_status.py"""
import subprocess
import hid

ds = list(hid.enumerate(0x0483, 0))
print(f"0483 HID interfaces: {len(ds)}")
for d in ds:
    print("  PID=0x%04x usage_page=0x%04x usage=0x%02x  product=%r" % (
        d.get("product_id", 0), d.get("usage_page", 0), d.get("usage", 0),
        d.get("product_string")))

print("--- DFU (dfu-util -l) ---")
out = subprocess.run(["/opt/homebrew/bin/dfu-util", "-l"],
                     capture_output=True, text=True).stdout
dfu = [ln for ln in out.splitlines() if "0483" in ln]
print("\n".join(dfu) if dfu else "(no 0483 DFU device)")
