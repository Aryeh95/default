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

from paths import ROOT, NAME, PCB, SCH

FAB = os.path.join(ROOT, "fab")
GERB = os.path.join(FAB, "gerbers")

# JLCPCB's part orientation differs from KiCad's for some packages.  These are
# the commonly used corrections; always confirm in JLCPCB's placement preview.
ROT_FIX = [(r"^SOT-23", 180), (r"^TSOT-23", 270), (r"^SSOP-", 270), (r"^FanPinHeader", 180)]


# alternative fan-header parts quoted at JLCPCB (fitted by JLCPCB, Economic PCBA)
FAN_HEADER_OPTIONS = [("C19795120", "Molex 470533000"), ("C2847671", "2510-4A 4-pin header 2.54mm")]


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
        groups = {}
        for ref in refs:
            fpid, value, _pos, _nets, lcsc, _smt, _sym = D.PARTS[ref]
            groups.setdefault((value, fpid[1], lcsc), []).append(ref)
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

    # default order: SMT only (Economic PCBA); the -with-tht pair is for comparing prices
    write_bom_cpl("", False)
    write_bom_cpl("-with-tht", True)
    # the same with-headers files, with other JLCPCB part numbers for the fan headers
    for lcsc, comment in FAN_HEADER_OPTIONS:
        src = os.path.join(FAB, NAME + "-bom-jlcpcb-with-tht.csv")
        rows = list(csv.reader(open(src, newline="")))
        for r in rows:
            if r[1] == "J2,J3":
                r[0], r[3] = comment, lcsc
        with open(os.path.join(FAB, NAME + "-bom-jlcpcb-fanhdr-%s.csv" % lcsc), "w", newline="") as f:
            csv.writer(f).writerows(rows)
        shutil.copy(os.path.join(FAB, NAME + "-cpl-jlcpcb-with-tht.csv"),
                    os.path.join(FAB, NAME + "-cpl-jlcpcb-fanhdr-%s.csv" % lcsc))

    # parts you solder yourself (for the default order)
    with open(os.path.join(FAB, NAME + "-bom-hand-solder.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Qty per board", "Part", "Footprint", "LCSC Part #"])
        for ref, (fpid, value, _pos, _nets, lcsc, smt, _sym) in D.PARTS.items():
            if not smt and not ref.startswith("TP"):
                w.writerow([ref, 1, value, fpid[1], lcsc])
        w.writerow(["(XIAO)", 1, "Seeed XIAO ESP32-C6, bare (no headers fitted)", "plugs into J6/J7", ""])
        w.writerow(["(XIAO pins)", 2, "1x7 male pin header, 2.54 mm, short (about 7.5 mm overall)",
                    "solder to the XIAO", ""])

    os.makedirs(os.path.join(ROOT, "docs"), exist_ok=True)
    run("kicad-cli", "sch", "export", "pdf", "-o", os.path.join(ROOT, "docs", "schematic.pdf"), SCH)
    print("fab files:", sorted(os.listdir(FAB)))
    print("gerbers:", sorted(os.listdir(GERB)))


if __name__ == "__main__":
    main()
