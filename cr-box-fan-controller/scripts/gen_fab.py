#!/usr/bin/python3.12
"""Produce the JLCPCB order files in fab/: Gerber zip, BOM and CPL (placement)."""
import csv
import os
import re
import shutil
import subprocess
import sys
import zipfile

import pcbnew

sys.path.insert(0, os.path.dirname(__file__))
import design as D

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
NAME = "cr-box-fan-controller"
PCB = os.path.join(ROOT, NAME + ".kicad_pcb")
FAB = os.path.join(ROOT, "fab")
GERB = os.path.join(FAB, "gerbers")

# JLCPCB's part orientation differs from KiCad's for some packages.  These are
# the commonly used corrections; always confirm in JLCPCB's placement preview.
ROT_FIX = [(r"^SOT-23", 180), (r"^TSOT-23", 270), (r"^SSOP-", 270), (r"^FanPinHeader", 180)]


# Through-hole parts are soldered by hand to keep the assembly fee and tariff down.
# Set True to have JLCPCB fit the XIAO sockets as well.
ASSEMBLE_XIAO_SOCKETS = False

# Sockets for the XIAO, in the U3 holes.  They have no
# footprint of their own, so they only appear in the BOM and CPL.
# (designator, x, y, rotation)
XIAO_SOCKETS = [("J6", 34.0 - 7.62, 11.5, 90), ("J7", 34.0 + 7.62, 11.5, 90)]
XIAO_SOCKET_PART = ("1x7 female header 2.54mm, 5.0mm high", "PinSocket_1x07_P2.54mm_Vertical", "C27985232")


def run(*args):
    r = subprocess.run(list(args), capture_output=True, text=True)
    if r.returncode:
        print(r.stdout, r.stderr)
        raise SystemExit(1)


def main():
    shutil.rmtree(FAB, ignore_errors=True)
    os.makedirs(GERB)
    run("kicad-cli", "pcb", "export", "gerbers", "-o", GERB + "/",
        "--layers", "F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts",
        "--subtract-soldermask", "--no-x2", "--no-netlist", PCB)
    run("kicad-cli", "pcb", "export", "drill", "-o", GERB + "/", "--format", "excellon",
        "--excellon-units", "mm", "--excellon-separate-th", "--excellon-zeros-format", "decimal", PCB)
    for f in os.listdir(GERB):
        if f.endswith(".gbrjob"):
            os.remove(os.path.join(GERB, f))
    with zipfile.ZipFile(os.path.join(FAB, NAME + "-gerbers.zip"), "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(GERB)):
            z.write(os.path.join(GERB, f), f)

    board = pcbnew.LoadBoard(PCB)
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}

    key = lambda r: (re.sub(r"\d", "", r), int(re.sub(r"\D", "", r)))

    def write_bom_cpl(suffix, with_tht):
        """with_tht: also have JLCPCB fit the through-hole parts that have an LCSC number."""
        refs = [r for r, p in D.PARTS.items() if p[5] or (with_tht and p[4])]
        sockets = XIAO_SOCKETS if (with_tht or ASSEMBLE_XIAO_SOCKETS) else []
        groups = {}
        for ref in refs:
            fpid, value, _pos, _nets, lcsc, _smt, _sym = D.PARTS[ref]
            groups.setdefault((value, fpid[1], lcsc), []).append(ref)
        if sockets:
            groups[XIAO_SOCKET_PART] = [d for d, _x, _y, _r in sockets]
        with open(os.path.join(FAB, NAME + "-bom-jlcpcb" + suffix + ".csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
            for (value, fp, lcsc), rs in sorted(groups.items(), key=lambda kv: key(sorted(kv[1], key=key)[0])):
                w.writerow([value, ",".join(sorted(rs, key=key)), fp, lcsc])
        with open(os.path.join(FAB, NAME + "-cpl-jlcpcb" + suffix + ".csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
            for ref in sorted(refs, key=key):
                fp = fps[ref]
                pos = fp.GetPosition()
                if fp.HasThroughHolePads():
                    # KiCad puts the origin of these footprints on pin 1 (or, for the
                    # USB-C socket, the body); JLCPCB places them by the centre of the pads
                    pads = [p.GetPosition() for p in fp.Pads() if p.GetNumber()]
                    pos = pcbnew.VECTOR2I((min(p.x for p in pads) + max(p.x for p in pads)) // 2,
                                          (min(p.y for p in pads) + max(p.y for p in pads)) // 2)
                rot = fp.GetOrientationDegrees()
                for pat, fix in ROT_FIX:
                    if re.match(pat, D.PARTS[ref][0][1]):
                        rot += fix
                w.writerow([ref, "%.3fmm" % pcbnew.ToMM(pos.x), "%.3fmm" % -pcbnew.ToMM(pos.y), "Top",
                            "%d" % (rot % 360)])
            for d, x, y, rot in sockets:
                w.writerow([d, "%.3fmm" % x, "%.3fmm" % -y, "Top", "%d" % rot])

    # default order: SMT only (Economic PCBA); the -with-tht pair is for comparing prices
    write_bom_cpl("", False)
    write_bom_cpl("-with-tht", True)

    # parts you solder yourself (for the default order)
    with open(os.path.join(FAB, NAME + "-bom-hand-solder.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Qty per board", "Part", "Footprint", "LCSC Part #"])
        for ref, (fpid, value, _pos, _nets, lcsc, smt, _sym) in D.PARTS.items():
            if not smt:
                w.writerow([ref, 1, value, fpid[1], lcsc])
        if not ASSEMBLE_XIAO_SOCKETS:
            w.writerow([",".join(d for d, *_ in XIAO_SOCKETS), len(XIAO_SOCKETS), *XIAO_SOCKET_PART])

    run("kicad-cli", "sch", "export", "pdf", "-o", os.path.join(ROOT, "docs", "schematic.pdf"),
        os.path.join(ROOT, NAME + ".kicad_sch"))
    print("fab files:", sorted(os.listdir(FAB)))
    print("gerbers:", sorted(os.listdir(GERB)))


if __name__ == "__main__":
    main()
