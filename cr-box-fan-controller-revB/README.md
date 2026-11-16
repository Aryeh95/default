# CR Box fan controller, rev B

Rev B comes in two versions built from one design (`scripts/design.py`), so they can be quoted side by
side at JLCPCB. Both are 52 × 46 mm, 2-layer, with the same mounting holes (except one, see below),
connectors and fan circuitry.

| | `module/` | `xiao/` |
|---|---|---|
| ESP32 | ESP32-C6-MINI-1-N4 module, fitted by JLCPCB | Seeed XIAO ESP32-C6, plugged into two SMD sockets |
| Flashing | Through the board's own USB-C port (also the power input) | Through the XIAO's USB-C port |
| Extra parts JLCPCB fits | Module, 3.3 V LDO, USB ESD array, BOOT/RESET buttons | Two 1×7 SMD sockets, Schottky diode |
| Extra extended-part fees vs. the other version (about $3 each) | 3 (module, AP2112K, USBLC6) | 1 (socket) |
| Parts you buy separately | — | XIAO ESP32-C6 (bare) and two short 1×7 male headers |
| Hand soldering per board | Fan headers: 8 joints | Fan headers: 8 joints, plus 14 XIAO header pins |
| Firmware | `esphome/cr-box-revB-module.yaml` | `esphome/cr-box-revB-xiao.yaml` |
| Case | `case/cr-box-case-revB-module-*.stl` (lower lid, BOOT/RESET holes) | `case/cr-box-case-revB-xiao-*.stl` |

Rough parts cost per board for the part that differs (prices from JLCPCB/LCSC listings, check the
quote): module version about $3 (module ≈ $2.50–3, LDO, ESD array, buttons), XIAO version about
$5.80 (XIAO $5.40, sockets $0.34, diode). The module version adds two more extended-part fees per
order. Whichever is cheaper overall depends on the quantity and on JLCPCB's order-value thresholds,
so compare the two quotes.

**Status: designed and rule-checked, not built.** Both boards pass KiCad DRC with 0 errors and
0 unconnected items (5 silkscreen warnings where pin labels touch pads), and the schematic, PCB and
`design.py` netlists match (module: 37 nets / 192 pins, XIAO: 33 nets / 139 pins).

## Changes from rev A (both versions)

- **5 V rail:** a second TPS54302 buck (100 k / 13 k feedback, 5.18 V) replaces the K7805
  through-hole module. Its EN pin is left open, so it is always on.
- **12 V inductor:** Eaton EXLA1V0505-150-R (15 µH, 4 A continuous, 4.6 A saturation) on its
  recommended land pattern. The 12 V rail is now good for about 7 fans (use a 45 W charger above 5).
- **FAN2 tach** is read on its own pin (GPIO20) with its own 10 k pull-up and 10 k series resistor.
  FAN1's series resistor is also 10 k now, which protects the GPIO from fans that pull tach up to 12 V.
- **USB-C socket:** 16-pin TYPE-C-31-M-12 (data lines used by the module version).
- **PD_PG pull-up** removed; the firmware uses the ESP32's internal pull-up.

## Ordering

1. Upload `<version>/fab/*-gerbers.zip`. 2 layers, 1.6 mm, **green**, lead-free HASL (other colours
   force Standard PCBA).
2. PCB Assembly, **Economic**, top side. Upload `*-bom-jlcpcb.csv` and `*-cpl-jlcpcb.csv`.
3. **L1 is a pre-order part** (Eaton EXLA1V0505-150-R, C5737644, minimum 47). Pre-order it into your
   JLCPCB parts library first. The Abracon ASPI-5050LR-150M-T (C3224630, minimum 11) has the same
   size and pads and can be used instead.
4. In the placement preview, check the orientation of U1, U4, U5, Q3 and J1, and on the module
   version U3, U6, U7; on the XIAO version D1, J6 and J7. The rotations for the new packages were not
   checked against JLCPCB's viewer.
5. Fan headers J2/J3 (Molex 47053-1000) are left for hand soldering. `*-with-tht.csv` files include
   them, for comparing the price of having JLCPCB fit them (that forces Standard PCBA).

## Module version notes

- Pins: VSENSE GPIO4, PD_PG GPIO5, FAN_EN GPIO0, PWM GPIO21, tach GPIO19/GPIO20, I2C GPIO22/23,
  UART GPIO16/17, USB GPIO12/13 (the full map is at the top of the YAML).
- First flash: plug the board into a computer with a USB-C data cable and run `esphome run`. A
  computer's 5 V runs the ESP32 (through the 5 V buck in dropout and the LDO); the fans stay off
  until a 15 V charger is connected. If the module doesn't show up, hold BOOT and tap RESET.
- The antenna end of the module overhangs a copper-free strip along the top edge. Keep metal and
  wiring away from it; the case is plastic.
- Mounting hole H2 is at (48.5, 9.0) instead of (48.5, 3.5) so it clears the antenna keep-out. The
  rev B case files account for this.

## XIAO version notes

- Pin use is the same as rev A, plus D9 (GPIO20) for FAN2 tach.
- Buy bare XIAOs and solder short (about 7.5 mm) 1×7 male headers to them, with the XIAO plugged
  into the board so the pins line up. The SMD sockets have closed bottoms, so long standard headers
  may not seat.
- The sockets are 5 mm tall; the case model assumes that.

## Files

| Path | What it is |
|---|---|
| `<version>/*.kicad_pro`, `.kicad_sch`, `.kicad_pcb` | KiCad 9 project |
| `<version>/docs/` | Schematic PDF, 3D render, assembly drawing, case preview |
| `<version>/fab/` | Gerbers, JLCPCB BOM and CPL, hand-solder list |
| `esphome/` | Firmware for each version |
| `case/` | OpenSCAD case model (`VARIANT` parameter) and STL files |
| `scripts/` | Generators; run with `VARIANT=module` or `VARIANT=xiao` |

## Regenerating

```sh
cd scripts
export VARIANT=module          # or xiao
python3 gen_board.py place     # footprints, outline, zones
python3 route.py               # tracks, vias, silkscreen, pour, stitching
python3 drc.py                 # KiCad DRC summary
python3 gen_sch.py             # schematic
python3 check_netlist.py       # schematic == PCB == design.py
python3 gen_fab.py             # Gerbers, BOM, CPL, schematic PDF
```
