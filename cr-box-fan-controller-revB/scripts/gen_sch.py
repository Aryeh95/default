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

from paths import ROOT, NAME, SCH

SYMDIR = "/usr/share/kicad/symbols/"
ROOT_UUID = str(uuid.uuid5(uuid.NAMESPACE_DNS, NAME))


def uid(*a):
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, NAME + "/" + "/".join(map(str, a))))


# --- project symbols: name -> (left pins, right pins) as (number, name) -----
_esp_left = [("1", "GND"), ("2", "GND"), ("3", "3V3"), ("4", "NC"), ("5", "IO2"), ("6", "IO3"), ("7", "NC"),
             ("8", "EN"), ("9", "IO4/ADC1_CH4"), ("10", "IO5"), ("11", "GND"), ("12", "IO0"), ("13", "IO1"),
             ("14", "GND"), ("15", "IO6"), ("16", "IO7"), ("17", "IO12/USB_D-"), ("18", "IO13/USB_D+"),
             ("19", "IO14"), ("20", "IO15"), ("21", "NC"), ("22", "IO8"), ("23", "IO9/BOOT")]
_esp_right = [("24", "IO18"), ("25", "IO19"), ("26", "IO20"), ("27", "IO21"), ("28", "IO22"), ("29", "IO23"),
              ("30", "RXD0/IO17"), ("31", "TXD0/IO16"), ("32", "NC"), ("33", "NC"), ("34", "NC"), ("35", "NC")]
_esp_right += [(str(n), "GND") for n in range(36, 54)]
CUSTOM = {
    "USB_C_16P": ([("S1", "SHIELD"), ("A1", "GND"), ("A12", "GND"), ("B1", "GND"), ("B12", "GND")],
                  [("A4", "VBUS"), ("A9", "VBUS"), ("B4", "VBUS"), ("B9", "VBUS"), ("A5", "CC1"), ("B5", "CC2"),
                   ("A6", "D+"), ("B6", "D+"), ("A7", "D-"), ("B7", "D-"), ("A8", "SBU1"), ("B8", "SBU2")]),
    "CH224A": ([("1", "VHV"), ("8", "VBUS"), ("7", "CC1"), ("6", "CC2"), ("4", "DP"), ("5", "DM")],
               [("10", "PG"), ("9", "CFG1"), ("2", "CFG2/SCL"), ("3", "CFG3/SDA"), ("11", "GND")]),
    "TPS54302": ([("3", "VIN"), ("5", "EN"), ("1", "GND")],
                 [("6", "BOOT"), ("2", "SW"), ("4", "FB")]),
    "NPN_BEC": ([("1", "B")], [("3", "C"), ("2", "E")]),
    "Fan_4pin": ([], [("1", "GND"), ("2", "+12V"), ("3", "TACH"), ("4", "PWM")]),
    "Header_I2C": ([], [("1", "GND"), ("2", "3V3"), ("3", "SDA"), ("4", "SCL")]),
    "Header_UART": ([], [("1", "GND"), ("2", "5V"), ("3", "RX"), ("4", "TX")]),
    "Socket_1x7": ([], [(str(k), "P%d" % k) for k in range(1, 8)]),
    "ESP32-C6-MINI-1": (_esp_left, _esp_right),
    "AP2112K": ([("1", "VIN"), ("3", "EN"), ("2", "GND")], [("5", "VOUT"), ("4", "NC")]),
    "Button": ([("1", "1")], [("2", "2")]),
    "USBLC6": ([("1", "I/O1"), ("3", "I/O2"), ("2", "GND")], [("6", "I/O1"), ("4", "I/O2"), ("5", "VBUS")]),
}
HALF_W = 12.7
WIDE = {"ESP32-C6-MINI-1": 20.32, "CH224A": 15.24}
PIN_LEN = 2.54

# which symbol each part uses (overrides design.py)
SYMBOL = {}

C1X, C2X, C3X, C4X = 20, 175, 335, 485
if D.VARIANT == "module":
    MCU = [("MCU: ESP32-C6-MINI-1-N4 with EN reset RC, IO8 pull-up and BOOT/RESET buttons", C3X, 30,
            [["U3"], ["C25", "C4", "R21", "C22"], ["R22", "R23"], ["SW1", "SW2"]]),
           ("3.3 V for the module: AP2112K LDO from +5V", C3X, 265, [["U6", "C24"]]),
           ("USB data protection (USB-C D+/D- to IO13/IO12)", C1X, 200, [["U7"]])]
else:
    MCU = [("MCU: Seeed XIAO ESP32-C6 in two SMD 1x7 sockets (J6 pin k = XIAO pin k, J7 pin k = XIAO pin 15-k)",
            C3X, 30, [["J6", "J7"], ["D1", "C4"]])]
SECTIONS = [
    ("USB-C input: CH224A requests 15 V (56k on CFG1). CC lines are interchangeable.", C1X, 30,
     [["J1", "U1"], ["R1", "R16", "C1", "R2"]]),
    ("VBUS voltage sense (to ADC)", C1X, 150, [["R11", "R12", "C7"]]),
    ("12 V fan rail: TPS54302 buck, EN pin = fan power on/off", C2X, 30,
     [["U4", "L1"], ["C9", "C10", "C8", "C11", "C12", "C13"], ["R3", "C6", "R4", "R5", "R6"]]),
    ("5 V rail: TPS54302 buck, EN left open (always on)", C2X, 190,
     [["U5", "L2"], ["C17", "C23", "C18", "C19", "C20"], ["R19", "C21", "R20"]]),
    ("Fan PWM (open collector, inverted) and tach inputs", C4X, 30,
     [["Q3"], ["R7", "R8", "R9", "R10"], ["R17", "R18"]]),
    ("Connectors", C4X, 175, [["J2"], ["J3"], ["J4"], ["J5"], ["R14", "R15"]]),
] + MCU


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
        if sym.startswith("custom:"):
            sym = sym.split(":", 1)[1]
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
        "3. Fan PWM is open-collector through Q3, so the firmware output is inverted.",
        "4. FAN_EN low or floating keeps the 12 V rail off (R6 pull-down).",
        "5. PD_PG is open drain: enable the MCU's internal pull-up in firmware.",
        "6. Tach inputs: 10k pull-up to 3V3 and 10k series resistor (protects against fans that pull tach to 12 V).",
        "7. J2, J3 (and J4, J5 if used) are hand-soldered through-hole headers.",
    ]
    if D.VARIANT == "module":
        notes.append("8. USB: the board's USB-C port carries data to the module's USB Serial/JTAG (flash and logs).")
    else:
        notes.append("8. Flash the XIAO through its own USB-C port. D1 stops it back-feeding the board's 5 V rail.")
    for i, n in enumerate(notes):
        body.append('\t(text "%s" (exclude_from_sim no) (at 25 %.2f 0) (effects (font (size 2 2)%s) (justify left bottom)) (uuid "%s"))'
                    % (n, 330 + i * 5.5, " (bold yes)" if i == 0 else "", uid("note", i)))

    with open(SCH, "w") as f:
        f.write('(kicad_sch\n\t(version 20250114)\n\t(generator "eeschema")\n\t(generator_version "9.0")\n')
        f.write('\t(uuid "%s")\n\t(paper "A2")\n' % ROOT_UUID)
        f.write('\t(title_block (title "CR Box PWM Fan Controller") (rev "B-%s") (comment 1 "USB-C PD in, 12 V PWM fans, ESP32-C6, ESPHome"))\n' % D.VARIANT)
        f.write('\t(lib_symbols\n')
        for k in sorted(lib_text):
            f.write("\t" + lib_text[k].replace("\n", "\n\t") + "\n")
        f.write('\t)\n')
        f.write("\n".join(body) + "\n")
        f.write('\t(sheet_instances (path "/" (page "1")))\n\t(embedded_fonts no)\n)\n')
    print("wrote schematic with", len(D.PARTS), "parts")


if __name__ == "__main__":
    main()
