# CR Box fan controller, rev B

Rev B keeps the Seeed XIAO ESP32-C6, now plugged into two surface-mount sockets, and makes
everything else on the board surface-mount so JLCPCB can assemble it with Economic PCBA. The board
is 52 × 46 mm, 2-layer, with the same mounting holes and connectors as rev A.

**Status: designed and rule-checked, not built.** The board passes KiCad DRC with 0 violations and
0 unconnected items, and the schematic, PCB and `design.py` netlists match (33 nets / 139 pins).

A second version with an ESP32-C6-MINI-1 module soldered to the board was designed and then set
aside, because JLCPCB only fits that module with Standard PCBA. `scripts/design.py` still supports it
(`VARIANT=module`) and its generated files are in the git history.

## Changes from rev A

- **5 V rail:** a second TPS54302 buck (100 k / 13 k feedback, 5.18 V) replaces the K7805
  through-hole module. Its EN pin is left open, so it is always on.
- **12 V inductor:** Eaton EXLA1V0505-150-R (15 µH, 4 A continuous, 4.6 A saturation) on its
  recommended land pattern. The 12 V rail is now good for about 7 fans (use a 45 W charger above 5).
- **FAN2 tach** is read on its own pin (GPIO20) with its own 10 k pull-up and 10 k series resistor.
  FAN1's series resistor is also 10 k now, which protects the GPIO from fans that pull tach up to 12 V.
- **USB-C socket:** 16-pin TYPE-C-31-M-12 (its data pins are unused).
- **PD_PG pull-up** removed; the firmware uses the ESP32's internal pull-up.

## Ordering

1. Upload `xiao/fab/*-gerbers.zip`. 2 layers, 1.6 mm, **green**, lead-free HASL (other colours
   force Standard PCBA).
2. PCB Assembly, **Economic**, top side. Upload a BOM and the CPL with the same suffix:
   - `*-jlcpcb.csv`: surface-mount parts only; you solder the fan headers.
   - `*-fanhdr-C19795120.csv`: JLCPCB also fits the fan headers (Molex 470533000). This was quoted
     as Economic PCBA with a small handling fee per header.
3. **L1 is a pre-order part** (Eaton EXLA1V0505-150-R, C5737644, minimum 47). Pre-order it into your
   JLCPCB parts library first. The Abracon ASPI-5050LR-150M-T (C3224630, minimum 11) has the same
   size and pads and can be used instead.
4. In the placement preview, check the orientation of U1, U4, U5, Q3, D1, J1, J6, J7 and the fan
   headers (locking ramp along the bottom board edge). L1's placement has not been seen in JLCPCB's
   viewer yet.

## XIAO notes

- Pin use is the same as rev A, plus D9 (GPIO20) for FAN2 tach.
- Buy bare XIAOs and solder short (about 7.5 mm) 1×7 male headers to them, with the XIAO plugged
  into the board so the pins line up. The SMD sockets have closed bottoms, so long standard headers
  may not seat.
- The sockets are 5 mm tall; the case model assumes that.

## Files

| Path | What it is |
|---|---|
| `xiao/*.kicad_pro`, `.kicad_sch`, `.kicad_pcb` | KiCad 9 project |
| `xiao/docs/` | Schematic PDF, 3D render, assembly drawing (with reference designators), case preview |
| `xiao/fab/` | Gerbers, JLCPCB BOM and CPL files, hand-solder list |
| `esphome/cr-box-revB-xiao.yaml` | Firmware |
| `case/` | OpenSCAD case model and STL files |
| `scripts/` | Generators |

## Regenerating

```sh
cd scripts
export VARIANT=xiao
python3 gen_board.py place     # footprints, outline, zones
python3 route.py               # tracks, vias, silkscreen, pour, stitching
python3 drc.py                 # KiCad DRC summary
python3 gen_sch.py             # schematic
python3 check_netlist.py       # schematic == PCB == design.py
python3 gen_fab.py             # Gerbers, BOM, CPL, schematic PDF
```
