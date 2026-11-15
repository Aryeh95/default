#!/usr/bin/python3
"""Generate the KiCad schematic (and the small project symbol library) from design.py.

Every pin gets a net label, so the drawing is a labelled netlist grouped by
function rather than a wired diagram.  `kicad-cli sch export netlist` output is
compared against design.py by check_netlist.py.
"""
import os
import re
import sys
import uuid

sys.path.insert(0, os.path.dirname(__file__))
import design as D

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
NAME = "cr-box-fan-controller"
SYMDIR = "/usr/share/kicad/symbols/"
ROOT_UUID = str(uuid.uuid5(uuid.NAMESPACE_DNS, NAME))


def uid(*a):
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, NAME + "/" + "/".join(map(str, a))))


# --- project symbols: name -> (left pins, right pins) as (number, name) -----
CUSTOM = {
    "USB_C_Power_6P": ([("S1", "SHIELD"), ("A12", "GND"), ("B12", "GND")],
                       [("A9", "VBUS"), ("B9", "VBUS"), ("A5", "CC1"), ("B5", "CC2")]),
    "CH224A": ([("1", "VHV"), ("8", "VBUS"), ("7", "CC1"), ("6", "CC2"), ("4", "DP"), ("5", "DM")],
               [("10", "PG"), ("9", "CFG1"), ("2", "CFG2/SCL"), ("3", "CFG3/SDA"), ("11", "GND")]),
    "TPS54302": ([("3", "VIN"), ("5", "EN"), ("1", "GND")],
                 [("6", "BOOT"), ("2", "SW"), ("4", "FB")]),
    "Buck_5V_SIP3": ([("1", "VIN"), ("2", "GND")], [("3", "VOUT")]),
    "XIAO_ESP32C6": ([("1", "D0/GPIO0"), ("2", "D1/GPIO1"), ("3", "D2/GPIO2"), ("4", "D3/GPIO21"),
                      ("5", "D4/GPIO22/SDA"), ("6", "D5/GPIO23/SCL"), ("7", "D6/GPIO16/TX")],
                     [("14", "5V"), ("13", "GND"), ("12", "3V3"), ("11", "D10/GPIO18"),
                      ("10", "D9/GPIO20"), ("9", "D8/GPIO19"), ("8", "D7/GPIO17/RX")]),
    "NPN_BEC": ([("1", "B")], [("3", "C"), ("2", "E")]),
    "Fan_4pin": ([], [("1", "GND"), ("2", "+12V"), ("3", "TACH"), ("4", "PWM")]),
    "Header_I2C": ([], [("1", "GND"), ("2", "3V3"), ("3", "SDA"), ("4", "SCL")]),
    "Header_UART": ([], [("1", "GND"), ("2", "5V"), ("3", "RX"), ("4", "TX")]),
}
HALF_W = 12.7
WIDE = {"XIAO_ESP32C6": 22.86, "CH224A": 15.24}
PIN_LEN = 2.54

# which symbol each part uses
SYMBOL = {"J1": "USB_C_Power_6P", "U1": "CH224A", "U2": "Buck_5V_SIP3", "U3": "XIAO_ESP32C6",
          "U4": "TPS54302", "Q3": "NPN_BEC", "J2": "Fan_4pin", "J3": "Fan_4pin",
          "J4": "Header_I2C", "J5": "Header_UART", "D1": "Device:D_Schottky", "L1": "Device:L"}

# schematic layout: (title, x, y, [rows of refs])
SECTIONS = [
    ("USB-C PD input: CH224A requests 15 V (56k on CFG1). CC lines are interchangeable.", 25, 30,
     [["J1", "U1"], ["R1", "R16", "C1", "R2", "R13"]]),
    ("VBUS voltage sense (to ADC)", 25, 135, [["R11", "R12", "C7"]]),
    ("5 V rail for the XIAO and UART sensor header", 25, 185, [["U2"], ["C2", "C3", "D1"]]),
    ("12 V fan rail: TPS54302 buck, EN pin = fan power on/off", 165, 30,
     [["U4", "L1"], ["C9", "C10", "C8", "C11", "C12", "C13"], ["R3", "C6", "R4", "R5", "R6"]]),
    ("MCU: Seeed XIAO ESP32-C6 (plugs into two 1x7 headers)", 165, 185, [["U3", "C4"]]),
    ("Fan PWM (open collector, inverted) and tach", 290, 30, [["Q3"], ["R7", "R8", "R9", "R10"]]),
    ("Connectors", 290, 135, [["J2", "J3"], ["J4", "J5"], ["R14", "R15"]]),
]


def custom_symbol_text(name):
    left, right = CUSTOM[name]
    HALF_W = WIDE.get(name, 12.7)
    n = max(len(left), len(right))
    h = n * 2.54 + 2.54
    top = h / 2
    out = ['\t(symbol "%s"' % name, '\t\t(exclude_from_sim no)', '\t\t(in_bom yes)', '\t\t(on_board yes)',
           '\t\t(property "Reference" "U" (at 0 %.2f 0) (effects (font (size 1.27 1.27))))' % (top + 1.9),
           '\t\t(property "Value" "%s" (at 0 %.2f 0) (effects (font (size 1.27 1.27))))' % (name, -top - 1.9),
           '\t\t(property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))',
           '\t\t(property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))',
           '\t\t(symbol "%s_0_1"' % name,
           '\t\t\t(rectangle (start %.2f %.2f) (end %.2f %.2f) (stroke (width 0.254) (type default)) (fill (type background)))'
           % (-HALF_W + PIN_LEN, top, HALF_W - PIN_LEN, -top),
           '\t\t)', '\t\t(symbol "%s_1_1"' % name]
    for side, pins in ((-1, left), (1, right)):
        for i, (num, pname) in enumerate(pins):
            y = top - 2.54 - i * 2.54
            out.append('\t\t\t(pin passive line (at %.2f %.2f %d) (length %.2f) (name "%s" (effects (font (size 1.27 1.27)))) '
                       '(number "%s" (effects (font (size 1.27 1.27)))))'
                       % (side * HALF_W, y, 0 if side < 0 else 180, PIN_LEN, pname, num))
    out += ['\t\t)', '\t\t(embedded_fonts no)', '\t)']
    return "\n".join(out)


def lib_symbol_text(lib_id):
    lib, name = lib_id.split(":")
    s = open(SYMDIR + lib + ".kicad_sym").read()
    i = s.index('\n\t(symbol "%s"' % name) + 1
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "(":
            depth += 1
        elif s[j] == ")":
            depth -= 1
            if depth == 0:
                break
    blk = s[i:j + 1]
    assert "(extends" not in blk, lib_id
    return blk.replace('(symbol "%s"' % name, '(symbol "%s"' % lib_id, 1)


def pins_of(text):
    """[(number, x, y, angle)] in symbol coordinates."""
    out = []
    for m in re.finditer(r'\(pin \w+ \w+\s*\(at ([-\d.]+) ([-\d.]+) (\d+)\)', text):
        num = re.search(r'\(number "([^"]+)"', text[m.end():]).group(1)
        out.append((num, float(m.group(1)), float(m.group(2)), int(m.group(3))))
    return out


def main():
    used = {}
    for ref, part in D.PARTS.items():
        sym = SYMBOL.get(ref) or part[6]
        if not (":" in sym and sym.split(":")[0] == "Device") and sym not in CUSTOM:
            raise SystemExit("no symbol for " + ref)
        used[ref] = sym

    lib_text = {}
    for sym in sorted(set(used.values())):
        if sym in CUSTOM:
            lib_text["crbox:" + sym] = custom_symbol_text(sym).replace(
                '(symbol "%s"' % sym, '(symbol "crbox:%s"' % sym, 1)
        else:
            lib_text[sym] = lib_symbol_text(sym)

    # project symbol library + library tables
    with open(os.path.join(ROOT, "crbox.kicad_sym"), "w") as f:
        f.write('(kicad_symbol_lib\n\t(version 20241209)\n\t(generator "gen_sch.py")\n\t(generator_version "9.0")\n')
        for sym in CUSTOM:
            f.write(custom_symbol_text(sym) + "\n")
        f.write(")\n")
    with open(os.path.join(ROOT, "sym-lib-table"), "w") as f:
        f.write('(sym_lib_table\n  (version 7)\n  (lib (name "crbox")(type "KiCad")(uri "${KIPRJMOD}/crbox.kicad_sym")(options "")(descr "CR box fan controller symbols"))\n)\n')
    with open(os.path.join(ROOT, "fp-lib-table"), "w") as f:
        f.write('(fp_lib_table\n  (version 7)\n  (lib (name "crbox")(type "KiCad")(uri "${KIPRJMOD}/crbox.pretty")(options "")(descr "CR box fan controller footprints"))\n)\n')

    body = []
    grid = lambda v: round(round(v / 1.27) * 1.27, 2)
    for title, sx, sy, rows in SECTIONS:
        body.append('\t(text "%s" (exclude_from_sim no) (at %.2f %.2f 0) (effects (font (size 2 2) (bold yes)) (justify left bottom)) (uuid "%s"))'
                    % (title, sx, sy - 6, uid("title", title)))
        y = sy
        for row in rows:
            x = sx
            row_h = 0
            for ref in row:
                sym = used[ref]
                lib_id = ("crbox:" + sym) if sym in CUSTOM else sym
                text = lib_text[lib_id]
                pins = pins_of(text)
                big = sym in CUSTOM
                if big:
                    n = max(len(CUSTOM[sym][0]), len(CUSTOM[sym][1]))
                    h = n * 2.54 + 2.54
                    cx, cy = grid(x + 30), grid(y + h / 2 + 5)
                    x += 78
                    row_h = max(row_h, h + 22)
                else:
                    cx, cy = grid(x + 8), grid(y + 16)
                    x += 22
                    row_h = max(row_h, 40)
                fpid, value, _pos, padnets, lcsc, _smt, _s = D.PARTS[ref]
                fp_name = ("crbox:" + fpid[1]) if fpid[0] == "custom" else fpid[0] + ":" + fpid[1]
                if big:
                    rpos, vpos = (cx, cy - h / 2 - 2.2), (cx, cy + h / 2 + 2.2)
                    just = ""
                else:
                    rpos, vpos = (cx + 2.8, cy - 1.3), (cx + 2.8, cy + 1.3)
                    just = " (justify left)"
                    if sym == "Device:D_Schottky":
                        rpos, vpos = (cx, cy - 3.2), (cx, cy + 3.2)
                        just = ""
                s = ['\t(symbol (lib_id "%s") (at %.2f %.2f 0) (unit 1) (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no) (uuid "%s")'
                     % (lib_id, cx, cy, uid("sym", ref)),
                     '\t\t(property "Reference" "%s" (at %.2f %.2f 0) (effects (font (size 1.27 1.27))%s))' % (ref, rpos[0], rpos[1], just),
                     '\t\t(property "Value" "%s" (at %.2f %.2f 0) (effects (font (size 1.27 1.27))%s))' % (value, vpos[0], vpos[1], just),
                     '\t\t(property "Footprint" "%s" (at %.2f %.2f 0) (effects (font (size 1.27 1.27)) (hide yes)))' % (fp_name, cx, cy),
                     '\t\t(property "Datasheet" "" (at %.2f %.2f 0) (effects (font (size 1.27 1.27)) (hide yes)))' % (cx, cy),
                     '\t\t(property "LCSC" "%s" (at %.2f %.2f 0) (effects (font (size 1.27 1.27)) (hide yes)))' % (lcsc, cx, cy)]
                for num, _px, _py, _a in pins:
                    s.append('\t\t(pin "%s" (uuid "%s"))' % (num, uid("pin", ref, num)))
                s.append('\t\t(instances (project "%s" (path "/%s" (reference "%s") (unit 1))))' % (NAME, ROOT_UUID, ref))
                s.append('\t)')
                body.append("\n".join(s))
                for num, px, py, a in pins:
                    lx, ly = round(cx + px, 2), round(cy - py, 2)
                    net = padnets.get(num)
                    if net is None:
                        body.append('\t(no_connect (at %.2f %.2f) (uuid "%s"))' % (lx, ly, uid("nc", ref, num)))
                        continue
                    # label points away from the symbol body
                    ang = {0: 180, 180: 0, 90: 270, 270: 90}[a]
                    just = {0: "left bottom", 180: "right bottom", 90: "left bottom", 270: "right bottom"}[ang]
                    body.append('\t(label "%s" (at %.2f %.2f %d) (effects (font (size 1.27 1.27)) (justify %s)) (uuid "%s"))'
                                % (net, lx, ly, ang, just, uid("lbl", ref, num)))
            y += row_h

    notes = [
        "Notes",
        "1. Charger: any USB-C PD charger of 30 W or more (15 V is mandatory above 27 W).",
        "2. U1 can also be a CH224K: then R1 = 1k (1206), R16 = 10k, same 56k on CFG1.",
        "3. U2: 7805-pinout switching module (K7805-500R3 or similar), not a linear 7805.",
        "4. Fan PWM is open-collector through Q3, so the firmware output is inverted.",
        "5. FAN_EN low or floating keeps the 12 V rail off (R6 pull-down).",
    ]
    for i, n in enumerate(notes):
        body.append('\t(text "%s" (exclude_from_sim no) (at 280 %.2f 0) (effects (font (size 1.6 1.6)%s) (justify left bottom)) (uuid "%s"))'
                    % (n, 250 + i * 4.5, " (bold yes)" if i == 0 else "", uid("note", i)))

    with open(os.path.join(ROOT, NAME + ".kicad_sch"), "w") as f:
        f.write('(kicad_sch\n\t(version 20250114)\n\t(generator "eeschema")\n\t(generator_version "9.0")\n')
        f.write('\t(uuid "%s")\n\t(paper "A3")\n' % ROOT_UUID)
        f.write('\t(title_block (title "CR Box PWM Fan Controller") (rev "A") (comment 1 "USB-C PD in, 12 V PWM fans, Seeed XIAO ESP32-C6, ESPHome"))\n')
        f.write('\t(lib_symbols\n')
        for k in sorted(lib_text):
            f.write("\t" + lib_text[k].replace("\n", "\n\t") + "\n")
        f.write('\t)\n')
        f.write("\n".join(body) + "\n")
        f.write('\t(sheet_instances (path "/" (page "1")))\n\t(embedded_fonts no)\n)\n')
    print("wrote schematic with", len(D.PARTS), "parts")


if __name__ == "__main__":
    main()
