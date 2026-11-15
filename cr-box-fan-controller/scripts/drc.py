#!/usr/bin/python3
"""Run KiCad DRC on the board and print a short summary."""
import collections
import json
import os
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
out = os.path.join(ROOT, "build", "drc.json")
subprocess.run(["kicad-cli", "pcb", "drc", "--severity-all", "--format", "json", "-o", out,
                os.path.join(ROOT, "cr-box-fan-controller.kicad_pcb")], capture_output=True)
d = json.load(open(out))
quiet = set(sys.argv[1:])
for key in ("violations", "unconnected_items"):
    v = d.get(key, [])
    print(key, len(v), dict(collections.Counter((x["type"], x["severity"]) for x in v)))
for x in d.get("unconnected_items", []):
    print("  UNCONNECTED", [i["description"] for i in x["items"]])
for x in d["violations"]:
    if x["type"] in quiet:
        continue
    if x["severity"] == "error" or not x["type"].startswith(("silk", "text")):
        print("  ", x["severity"], x["type"], "|", x["description"], "|",
              [(i["description"], round(i["pos"]["x"], 2), round(i["pos"]["y"], 2)) for i in x["items"]][:2])
