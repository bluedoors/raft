#!/usr/bin/env python3
"""Push a generated profile to the duckyPad over HID (file-access commands), the
same way the Configurator does. No SD removal, no GUI.

CLOSE the Configurator first (it holds the HID interface). Run under sudo
(opening the config HID needs root); needs Python 3 with the 'hidapi' package
(pip install hidapi):

  sudo python3 duckypad_push_profile.py --profile cmux
  sudo python3 duckypad_push_profile.py --profile orca

Steps: create /profile_<name>, write config.txt + key*.{txt,dsb}, append
'<n> <name>' to /profile_info.txt (read-modify-write), soft-reset to reload, then
record <n> -> host in /usr/local/libexec/duckypad_profiles.json so the LED writer
knows which host owns the board while that profile is loaded.
"""
import os
import sys
import time
import json
import argparse
import hid

VID, PID, CFG_USAGE, CFG_PAGE = 0x0483, 0xD11C, 0x3A, 0x0001
_HERE = os.path.dirname(os.path.abspath(__file__))

PROFILE_MAP_PATH = "/usr/local/libexec/duckypad_profiles.json"


def record_profile_host(number, name):
    """Tell the LED writer which host owns which pad profile.

    duckypad_led.py refuses to paint when another host's profile is loaded; this
    is where that mapping comes from, so it is generated rather than hand-edited.
    """
    if name not in ("cmux", "orca"):
        return                      # only Raft's own profiles participate
    try:
        try:
            with open(PROFILE_MAP_PATH) as f:
                mapping = json.load(f)
        except Exception:
            mapping = {}
        mapping = {k: v for k, v in mapping.items() if v != name}   # drop stale entry
        mapping[str(number)] = name
        os.makedirs(os.path.dirname(PROFILE_MAP_PATH), exist_ok=True)
        with open(PROFILE_MAP_PATH, "w") as f:
            json.dump(mapping, f, indent=2)
        os.chmod(PROFILE_MAP_PATH, 0o644)
        print(f"recorded profile {number} -> host {name} in {PROFILE_MAP_PATH}")
    except PermissionError:
        print(f"WARNING: could not write {PROFILE_MAP_PATH} (need sudo). The LED "
              f"writer will fall back to its built-in default map {{1: cmux, 2: orca}}.")

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
    ap = argparse.ArgumentParser(description="Push a generated profile to the duckyPad.")
    ap.add_argument("--profile", default="cmux", choices=("cmux", "orca"),
                    help="which generated profile_<name>/ directory to push")
    args = ap.parse_args()
    profile_name = args.profile
    local = os.path.join(_HERE, f"profile_{profile_name}")
    if not os.path.isdir(local):
        print(f"no generated profile at {local} — run "
              f"duckypad_build_profile.py --host {profile_name} first", file=sys.stderr)
        return 2

    h = open_dev()
    try:
        # 1. read profile_info.txt; reuse this profile's number or assign the next
        info = read_file(h, "/profile_info.txt")
        info_txt = info.decode("utf-8", "replace") if info else ""
        lines = [l for l in info_txt.splitlines() if l.strip()]
        existing = [l for l in lines if l.split(maxsplit=1)[-1].strip() == profile_name]
        if existing:
            assigned = int(existing[0].split()[0])
            print(f"profile '{profile_name}' already listed as #{assigned}; "
                  f"overwriting its files")
        else:
            assigned = max((int(l.split()[0]) for l in lines), default=0) + 1
            lines.append(f"{assigned} {profile_name}")
            print(f"adding profile #{assigned} {profile_name}")
        new_info = ("\n".join(lines) + "\n").encode()

        # 2. create dir + push files
        mkdir(h, f"/profile_{profile_name}")
        for fn in sorted(os.listdir(local)):
            with open(os.path.join(local, fn), "rb") as f:
                write_file(h, f"/profile_{profile_name}/{fn}", f.read())

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

    record_profile_host(assigned, profile_name)
    print(f"DONE. Device should reboot; select the '{profile_name}' profile "
          f"with the +/- buttons.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
