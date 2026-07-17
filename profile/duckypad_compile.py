#!/usr/bin/env python3
"""Compile duckyScript 3 source -> .dsb bytes using the duckyPad Configurator's
own compiler modules (no GUI). Lets us build profiles by editing files directly
instead of clicking through the Configurator.

Needs a Python 3.10+ (the Configurator source uses 3.10+ syntax):
  python3 duckypad_compile.py --selftest

Requires the duckyPad Configurator SOURCE (see RAFT_CONFIG_SRC below).
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))


def _resolve_config_src():
    """Locate the duckyPad Configurator source dir (has dsvm_*.py)."""
    env = os.environ.get("RAFT_CONFIG_SRC")
    if env:
        return env
    # default: a sibling/child 'duckypad_config_src' near this script or repo
    for cand in (os.path.join(_HERE, "duckypad_config_src"),
                 os.path.join(os.path.dirname(_HERE), "duckypad_config_src")):
        if os.path.isdir(cand):
            return cand
    return os.path.join(_HERE, "duckypad_config_src")


SRC = _resolve_config_src()
if not os.path.isdir(SRC):
    sys.exit(
        "ERROR: duckyPad Configurator source not found at:\n"
        "    %s\n\n"
        "This script compiles duckyScript using the Configurator's own modules.\n"
        "Download the Configurator SOURCE zip (the '*_source.zip' asset, NOT the\n"
        "app) from:\n"
        "    https://github.com/duckyPad/duckyPad-Configurator/releases\n"
        "unzip it, and point RAFT_CONFIG_SRC at the folder containing\n"
        "dsvm_common.py / dsvm_preprocessor.py / dsvm_make_bytecode.py, e.g.:\n"
        "    export RAFT_CONFIG_SRC=/path/to/duckyPad-Configurator/src\n"
        % SRC
    )
sys.path.insert(0, SRC)

import dsvm_common
import dsvm_preprocessor
import dsvm_make_bytecode


def compile_ds(script_text):
    """Return compiled .dsb bytes for a duckyScript source string."""
    lines = script_text.split("\n")
    obj_list = dsvm_common.make_list_of_ds_line_obj_from_str_listing(lines)
    import_dict = dsvm_preprocessor.preprocess_import_str_dict(
        {"USE_UH": [], "USE_STDLIB": []})
    res = dsvm_make_bytecode.make_dsb_with_exception(
        obj_list, import_name_to_line_obj_dict=import_dict)
    # comp_result exposes .is_success / .bin_array (see compile_all_scripts)
    ok = getattr(res, "is_success", None)
    if ok is None and isinstance(res, dict):
        ok = res.get("is_success")
        bin_array = res.get("bin_array") or res.get("bin_array")
    else:
        bin_array = res.bin_array
    if ok is False:
        raise ValueError(f"compile failed: {res}")
    return bytes(bin_array)


def _selftest():
    known = os.environ.get("RAFT_SELFTEST_DIR")
    if not known or not os.path.isfile(os.path.join(known, "key1.txt")):
        print("selftest skipped: set RAFT_SELFTEST_DIR to a profile dir with "
              "key1.txt/key1.dsb")
        return True
    with open(known + "/key1.txt") as f:
        src = f.read()
    with open(known + "/key1.dsb", "rb") as f:
        expected = f.read()
    got = compile_ds(src)
    print(f"source: {src!r}")
    print(f"expected .dsb: {expected.hex()}")
    print(f"our      .dsb: {got.hex()}")
    print("MATCH ✅" if got == expected else "MISMATCH ❌")
    return got == expected


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(0 if _selftest() else 1)
    # else: compile stdin -> stdout(hex)
    print(compile_ds(sys.stdin.read()).hex())
