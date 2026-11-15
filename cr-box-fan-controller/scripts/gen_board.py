#!/usr/bin/python3.12
"""Build the PCB from design.py.

  gen_board.py place  -> unrouted board (footprints, outline, zones)
  route.py then adds tracks, silkscreen and fills the ground pours
"""
import json
import os
import sys

import pcbnew
from pcbnew import FromMM, VECTOR2I

sys.path.insert(0, os.path.dirname(__file__))
import design as D

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
NAME = "cr-box-fan-controller"
PCB = os.path.join(ROOT, NAME + ".kicad_pcb")
PRO = os.path.join(ROOT, NAME + ".kicad_pro")
BUILD = os.path.join(ROOT, "build")


def P(x, y):
    return VECTOR2I(FromMM(x), FromMM(y))


def write_project():
    classes = []
    for name, (w, cl, vd, vh) in D.CLASSES.items():
        classes.append({
            "name": name, "clearance": cl, "track_width": w,
            "via_diameter": vd, "via_drill": vh,
            "microvia_diameter": 0.3, "microvia_drill": 0.1,
            "diff_pair_gap": 0.25, "diff_pair_width": 0.2, "diff_pair_via_gap": 0.25,
            "bus_width": 12, "wire_width": 6, "line_style": 0,
            "pcb_color": "rgba(0, 0, 0, 0.000)", "schematic_color": "rgba(0, 0, 0, 0.000)",
            "priority": 2147483647 if name == "Default" else 0,
        })
    patterns = [{"netclass": "Power", "pattern": n} for n in D.POWER_NETS]
    patterns += [{"netclass": "Mid", "pattern": n} for n in D.MID_NETS]
    pro = {
        "board": {"design_settings": {
            "rules": {
                "min_clearance": 0.15, "min_track_width": 0.15,
                "min_via_diameter": 0.6, "min_via_annular_width": 0.13,
                "min_through_hole_diameter": 0.3, "min_hole_to_hole": 0.5,
                "min_copper_edge_clearance": 0.3, "min_hole_clearance": 0.25,
                "min_silk_clearance": 0.0, "min_text_height": 0.8,
                "min_text_thickness": 0.12, "solder_mask_to_copper_clearance": 0.0,
            },
            "rule_severities": {"lib_footprint_issues": "ignore",
                                "lib_footprint_mismatch": "ignore"},
            "track_widths": [0.0, 0.25, 0.5, 0.8],
            "via_dimensions": [{"diameter": 0.0, "drill": 0.0},
                               {"diameter": 0.7, "drill": 0.3},
                               {"diameter": 0.9, "drill": 0.5}],
        }},
        "meta": {"filename": NAME + ".kicad_pro", "version": 3},
        "net_settings": {"classes": classes, "meta": {"version": 4},
                         "netclass_patterns": patterns},
    }
    with open(PRO, "w") as f:
        json.dump(pro, f, indent=2)


def xiao_footprint(board):
    """Through-hole footprint for a Seeed XIAO (two 1x7 rows, 15.24 mm apart)."""
    fp = pcbnew.FOOTPRINT(board)
    for i in range(14):
        pad = pcbnew.PAD(fp)
        pad.SetNumber(str(i + 1))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT if i == 0 else pcbnew.PAD_SHAPE_OVAL)
        pad.SetSize(VECTOR2I(FromMM(1.9), FromMM(1.6)))
        pad.SetDrillSize(VECTOR2I(FromMM(1.0), FromMM(1.0)))
        pad.SetLayerSet(pcbnew.PAD.PTHMask())
        if i < 7:
            x, y = -7.62, -7.62 + 2.54 * i
        else:
            x, y = 7.62, 7.62 - 2.54 * (i - 7)
        pad.SetFPRelativePosition(P(x, y))
        fp.Add(pad)

    def line(layer, x0, y0, x1, y1, w=0.12):
        s = pcbnew.PCB_SHAPE(fp)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetLayer(layer)
        s.SetStart(P(x0, y0))
        s.SetEnd(P(x1, y1))
        s.SetWidth(FromMM(w))
        fp.Add(s)

    hw, hh = 8.9, 10.5
    for layer, grow in ((pcbnew.F_SilkS, 0.15), (pcbnew.F_Fab, 0.0), (pcbnew.F_CrtYd, 0.4)):
        w = 0.05 if layer == pcbnew.F_CrtYd else 0.12
        a, b = hw + grow, hh + grow
        if layer == pcbnew.F_SilkS:
            # leave the pad columns open on silk
            for sx in (-1, 1):
                line(layer, sx * a, -b, sx * a, -9.0, w)
                line(layer, sx * a, 9.0, sx * a, b, w)
            line(layer, -a, -b, a, -b, w)
            line(layer, -a, b, a, b, w)
        else:
            line(layer, -a, -b, a, -b, w)
            line(layer, a, -b, a, b, w)
            line(layer, a, b, -a, b, w)
            line(layer, -a, b, -a, -b, w)
    # USB connector marker
    for x0, y0, x1, y1 in ((-4.5, -10.5, -4.5, -5.0), (4.5, -10.5, 4.5, -5.0), (-4.5, -5.0, 4.5, -5.0)):
        line(pcbnew.F_SilkS, x0, y0, x1, y1)
    fp.SetAttributes(pcbnew.FP_THROUGH_HOLE | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
    fp.SetFPID(pcbnew.LIB_ID("custom", "XIAO_THT"))
    return fp


def text(board, s, x, y, size=1.0, rot=0, layer=pcbnew.F_SilkS, just=None):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetLayer(layer)
    t.SetPosition(P(x, y))
    t.SetTextSize(VECTOR2I(FromMM(size), FromMM(size)))
    t.SetTextThickness(FromMM(max(0.15, size * 0.15)))
    t.SetTextAngle(pcbnew.EDA_ANGLE(rot, pcbnew.DEGREES_T))
    if just == "L":
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
    if just == "R":
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_RIGHT)
    if layer == pcbnew.B_SilkS:
        t.SetMirrored(True)
    board.Add(t)


def place():
    write_project()
    if os.path.exists(PCB):
        os.remove(PCB)
    board = pcbnew.NewBoard(PCB)
    board.SetCopperLayerCount(2)

    nets = {}

    def net(name):
        if name not in nets:
            n = pcbnew.NETINFO_ITEM(board, name)
            board.Add(n)
            nets[name] = n
        return nets[name]

    # outline with rounded corners
    r = 2.0
    W, H = D.BOARD_W, D.BOARD_H
    segs = [((r, 0), (W - r, 0)), ((W, r), (W, H - r)), ((W - r, H), (r, H)), ((0, H - r), (0, r))]
    for a, b in segs:
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetStart(P(*a)); s.SetEnd(P(*b)); s.SetWidth(FromMM(0.1))
        board.Add(s)
    for cx, cy, sx, sy, ex, ey in ((r, r, 0, r, r, 0), (W - r, r, W - r, 0, W, r),
                                   (W - r, H - r, W, H - r, W - r, H), (r, H - r, r, H, 0, H - r)):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_ARC)
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetCenter(P(cx, cy)); s.SetStart(P(sx, sy))
        s.SetArcAngleAndEnd(pcbnew.EDA_ANGLE(90, pcbnew.DEGREES_T), True)
        s.SetWidth(FromMM(0.1))
        board.Add(s)

    for ref, (fpid, value, (x, y, rot), padnets, lcsc, smt, _sym) in D.PARTS.items():
        if fpid[0] == "custom":
            fp = xiao_footprint(board)
        else:
            fp = pcbnew.FootprintLoad(D.FP + fpid[0] + ".pretty", fpid[1])
        fp.SetReference(ref)
        fp.SetValue(value)
        fp.Value().SetVisible(False)
        if lcsc:
            fp.SetField("LCSC", lcsc)
            fp.GetFieldByName("LCSC").SetVisible(False)
        board.Add(fp)
        fp.SetPosition(P(x, y))
        fp.SetOrientationDegrees(rot)
        for pad in fp.Pads():
            n = padnets.get(pad.GetNumber())
            if n:
                pad.SetNet(net(n))
        # shrink reference text
        fp.Reference().SetTextSize(VECTOR2I(FromMM(0.8), FromMM(0.8)))
        fp.Reference().SetTextThickness(FromMM(0.12))
        # reference designators live on the fab layer; the silkscreen only
        # carries the labels a user needs (see finish_silk)
        fp.Reference().SetLayer(pcbnew.F_Fab)
        if ref == "J1":
            # drop silkscreen that would fall off the board edge
            for g in list(fp.GraphicalItems()):
                if g.GetLayer() == pcbnew.F_SilkS:
                    fp.Remove(g)

    for i, (x, y) in enumerate(D.HOLES):
        fp = pcbnew.FootprintLoad(D.FP + "MountingHole.pretty", "MountingHole_3.2mm_M3")
        fp.SetReference("H%d" % (i + 1))
        fp.Reference().SetVisible(False)
        fp.Value().SetVisible(False)
        fp.SetAttributes(fp.GetAttributes() | pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
        board.Add(fp)
        fp.SetPosition(P(x, y))

    # antenna keep-out (no copper at all)
    x0, y0, x1, y1 = D.ANT_KEEPOUT
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    z.SetDoNotAllowCopperPour(True)
    z.SetDoNotAllowTracks(True)
    z.SetDoNotAllowVias(True)
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowFootprints(False)
    ls = pcbnew.LSET()
    ls.AddLayer(pcbnew.F_Cu); ls.AddLayer(pcbnew.B_Cu)
    z.SetLayerSet(ls)
    z.SetZoneName("XIAO antenna keep-out")
    o = z.Outline()
    o.NewOutline()
    for px, py in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        o.Append(FromMM(px), FromMM(py))
    board.Add(z)

    add_gnd_zones(board)
    # keep a copy of the custom XIAO footprint as a project library
    lib = os.path.join(ROOT, "crbox.pretty")
    os.makedirs(lib, exist_ok=True)
    xiao = xiao_footprint(board)
    xiao.SetReference("REF**")
    xiao.SetValue("XIAO_THT")
    pcbnew.PCB_IO_MGR.PluginFind(pcbnew.PCB_IO_MGR.KICAD_SEXP).FootprintSave(lib, xiao)
    pcbnew.SaveBoard(PCB, board)
    os.makedirs(BUILD, exist_ok=True)
    print("placed", len(board.GetFootprints()), "footprints")


def add_gnd_zones(board):
    gnd = board.FindNet("GND")
    m = 0.0
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(gnd)
        z.SetZoneName("GND")
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THT_THERMAL)
        z.SetThermalReliefGap(FromMM(0.3))
        z.SetThermalReliefSpokeWidth(FromMM(0.5))
        z.SetLocalClearance(FromMM(0.3))
        z.SetMinThickness(FromMM(0.25))
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        o = z.Outline()
        o.NewOutline()
        for px, py in ((m, m), (D.BOARD_W - m, m), (D.BOARD_W - m, D.BOARD_H - m), (m, D.BOARD_H - m)):
            o.Append(FromMM(px), FromMM(py))
        board.Add(z)


def finish_silk(board):
    text(board, "CR BOX FAN CTRL", 35.2, 44.8, 0.9, just="L")
    text(board, "rev A", 46.0, 39.6, 0.8)
    text(board, "USB PD", 0.9, 7.4, 0.9, just="L")
    text(board, "15V 30W+", 0.8, 20.4, 0.9, just="L")
    text(board, "FAN1", 9.9, 40.2, 0.9, just="R")
    text(board, "+TACH", 9.9, 41.8, 0.8, just="R")
    text(board, "FAN2", 28.8, 34.4, 0.9)
    for x0 in (12.0, 25.0):
        for i, s in enumerate(("G", "12", "T", "P")):
            text(board, s, x0 + 2.54 * i, 36.0 if x0 > 20 else 35.0, 0.8)
    text(board, "I2C", 48.5, 14.6, 0.9)
    for i, s in enumerate(("G", "3V3", "SDA", "SCL")):
        text(board, s, 46.6, 17.0 + 2.54 * i, 0.8, just="R")
    text(board, "UART", 48.5, 26.9, 0.9)
    for i, s in enumerate(("G", "5V", "RX", "TX")):
        text(board, s, 46.6, 29.0 + 2.54 * i, 0.8, just="R")
    text(board, "5V BUCK", 14.3, 2.9, 0.9)
    text(board, "IN  G  OUT", 14.3, 4.6, 0.8)
    text(board, "XIAO ESP32-C6", 34.0, 13.0, 1.0)
    text(board, "USB", 34.0, 3.0, 0.9)
    text(board, "ANT", 34.0, 21.0, 0.9)
    text(board, "12V BUCK", 12.0, 33.0, 0.9)


if __name__ == "__main__":
    {"place": place}[sys.argv[1]]()
