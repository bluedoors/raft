#!/usr/bin/env python3
"""Push the generated 'cmux' profile to the duckyPad over HID (file-access
commands), the same way the Configurator does. No SD removal, no GUI.

CLOSE the Configurator first (it holds the HID interface). Run under sudo
(opening the config HID needs root); needs Python 3 with the 'hidapi' package
(pip install hidapi):

  sudo python3 duckypad_push_profile.py

Steps: create /profile_cmux, write config.txt + key*.{txt,dsb}, append
'<n> cmux' to /profile_info.txt (read-modify-write), then soft-reset to reload.
"""
import os
import sys
import time
import hid

VID, PID, CFG_USAGE, CFG_PAGE = 0x0483, 0xD11C, 0x3A, 0x0001
_HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.join(_HERE, "profile_cmux")
PROFILE_NAME = "cmux"

# HID command numbers (firmware/evo/Inc/hid_task.h)
C_READ_FILE = 11
C_OPEN_WRITE = 14
C_WRITE_FILE = 15
C_CLOSE_FILE = 16
C_CREATE_DIR = 18
C_SW_RESET = 20
C_OPEN_READ = 33
CHUNK = 60


def open_dev():
    path = None
    for d in hid.enumerate(VID, PID):
        if d.get("usage") == CFG_USAGE and d.get("usage_page") == CFG_PAGE:
            path = d["path"]; break
    if not path:
        print("FAIL: duckyPad config interface not found (is the Configurator still open?)")
        sys.exit(1)
    h = hid.device(); h.open_path(path); h.set_nonblocking(0)
    return h


def buf(cmd):
    b = [0] * 64; b[0] = 5; b[2] = cmd; return b


def txrx(h, b):
    h.write(b)
    return h.read(64, timeout_ms=800)


def put_str(b, s, off=3):
    for i, c in enumerate(s):
        b[off + i] = ord(c)


def mkdir(h, path):
    b = buf(C_CREATE_DIR); put_str(b, path)
    r = txrx(h, b)
    print(f"  mkdir {path} -> status {r[2] if r else '?'}")


def write_file(h, dev_path, data: bytes):
    b = buf(C_OPEN_WRITE); put_str(b, dev_path); txrx(h, b)
    for i in range(0, len(data), CHUNK):
        chunk = data[i:i + CHUNK]
        cb = buf(C_WRITE_FILE); cb[1] = len(chunk)
        for j, v in enumerate(chunk):
            cb[3 + j] = v
        txrx(h, cb)
    txrx(h, buf(C_CLOSE_FILE))
    print(f"  wrote {dev_path} ({len(data)} B)")


def read_file(h, dev_path):
    b = buf(C_OPEN_READ); put_str(b, dev_path)
    r = txrx(h, b)
    if not r or r[2] != 0:
        return None  # open failed (e.g. file missing)
    out = bytearray()
    while True:
        r = txrx(h, buf(C_READ_FILE))
        n = r[2] if r else 0
        if not n:
            break
        out += bytes(r[3:3 + n])
    return bytes(out)


def main():
    h = open_dev()
    try:
        # 1. read current profile_info.txt, append cmux if absent
        info = read_file(h, "/profile_info.txt")
        info_txt = info.decode("utf-8", "replace") if info else ""
        lines = [l for l in info_txt.splitlines() if l.strip()]
        if any(l.split(maxsplit=1)[-1].strip() == PROFILE_NAME for l in lines):
            print(f"profile '{PROFILE_NAME}' already listed; will overwrite its files")
            nums = [int(l.split()[0]) for l in lines]
        else:
            nextnum = (max((int(l.split()[0]) for l in lines), default=0) + 1)
            lines.append(f"{nextnum} {PROFILE_NAME}")
            print(f"adding profile #{nextnum} {PROFILE_NAME}")
        new_info = ("\n".join(lines) + "\n").encode()

        # 2. create dir + push files
        mkdir(h, f"/profile_{PROFILE_NAME}")
        for fn in sorted(os.listdir(LOCAL)):
            with open(os.path.join(LOCAL, fn), "rb") as f:
                write_file(h, f"/profile_{PROFILE_NAME}/{fn}", f.read())

        # 3. write updated profile_info.txt
        write_file(h, "/profile_info.txt", new_info)
        print("profile_info.txt updated:\n" + new_info.decode())

        # 4. soft-reset to leave file-access mode and reload profiles
        print("resetting device to reload...")
        h.write(buf(C_SW_RESET))
        time.sleep(0.3)
    finally:
        try:
            h.close()
        except Exception:
            pass
    print("DONE. Device should reboot; select the 'cmux' profile with the +/- buttons.")


if __name__ == "__main__":
    main()
