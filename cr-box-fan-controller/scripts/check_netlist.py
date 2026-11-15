#!/usr/bin/python3.12
"""Cross-check: schematic netlist == design.py == nets on the PCB pads."""
import os
import re
import subprocess
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(__file__))
import design as D

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
NAME = "cr-box-fan-controller"

want = {}
for ref, part in D.PARTS.items():
    for pad, net in part[3].items():
        want.setdefault(net, set()).add((ref, pad))

# schematic
out = os.path.join(ROOT, "build", NAME + ".net")
subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format", "kicadsexpr", "-o", out,
                os.path.join(ROOT, NAME + ".kicad_sch")], capture_output=True)
txt = open(out).read()
sch = {}
for m in re.finditer(r'\(net \(code "?\d+"?\) \(name "([^"]+)"\)(.*?)(?=\(net \(code|\Z)', txt, re.S):
    name = m.group(1).lstrip("/")
    nodes = set(re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', m.group(2)))
    sch[name] = nodes
sch = {k: v for k, v in sch.items() if not k.startswith("unconnected-")}

# pcb
board = pcbnew.LoadBoard(os.path.join(ROOT, NAME + ".kicad_pcb"))
pcb = {}
for fp in board.GetFootprints():
    for pad in fp.Pads():
        if pad.GetNetname() and pad.GetNumber():
            pcb.setdefault(pad.GetNetname(), set()).add((fp.GetReference(), pad.GetNumber()))

ok = True
for label, got in (("schematic", sch), ("pcb", pcb)):
    if got == want:
        print("%-9s matches design.py: %d nets, %d pins" % (label, len(got), sum(map(len, got.values()))))
        continue
    ok = False
    for net in sorted(set(got) | set(want)):
        a, b = got.get(net, set()), want.get(net, set())
        if a != b:
            print("  %s net %s: extra %s missing %s" % (label, net, sorted(a - b), sorted(b - a)))
sys.exit(0 if ok else 1)
