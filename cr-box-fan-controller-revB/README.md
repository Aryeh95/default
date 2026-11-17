# CR Box fan controller, rev B

Rev B keeps the Seeed XIAO ESP32-C6, now plugged into two surface-mount sockets, and makes
everything else on the board surface-mount so JLCPCB can assemble it with Economic PCBA. The board
is 52 × 46 mm, 2-layer, with the same mounting holes and connectors as rev A.

**Status: designed and rule-checked, not built.** The board passes KiCad DRC with 0 violations and
0 unconnected items, and the schematic, PCB and `design.py` netlists match (33 nets / 142 pins).

A second version with an ESP32-C6-MINI-1 module soldered to the board was designed and then set
aside, because JLCPCB only fits that module with Standard PCBA. `scripts/design.py` still supports it
(`VARIANT=module`) and its generated files are in the git history.

## Changes from rev A

- **5 V rail:** a second TPS54302 buck (100 k / 13 k feedback, 5.18 V) replaces the K7805
  through-hole module. Its EN pin is left open, so it is always on.
- **12 V inductor:** TMPA0605S-150MN-D (LCSC C305194; 15 µH, 4 A rated and saturation, 73 mΩ,
  7.3 × 6.6 mm) on JLCPCB's land pattern for it. It is in stock at JLCPCB, so no pre-order is needed.
  The inductor would allow about 7 fans, but the TPS54302 then dissipates
  roughly 0.6–0.7 W in a SOT-23-6, so **treat 5 fans as the limit** until a built board has been
  checked for temperature at full load.
- **5 V inductor:** FXL0518-100-M (10 µH, 2.5 A continuous, 3 A saturation) instead of a 1.95 A part,
  so a short on the 5 V header no longer saturates it before the converter's current limit trips.
- **CH224A on the I2C bus:** its CFG2/SCL and CFG3/SDA pins join the XIAO's I2C bus (the datasheet
  allows 3.3 V logic on them; the board's 4.7 k pull-ups serve both). The CH224A still requests
  15 V by itself through its 56 k resistor. The firmware reads which protocol was negotiated and how
  much current the charger offers ("Charger Max Current" / "Charger Max Power"), so you can see
  whether a charger is big enough for your fans. The CH224A uses I2C address 0x22 or 0x23 (the
  datasheet gives both); don't put a sensor at those addresses on the header.
- **PWM driver base resistor R7** is 1 k (was 2.2 k), so Q3 stays saturated with 7 or more fans
  pulling the PWM line up at once.
- **Extra thermal vias** next to the 12 V converter's ground pin, spreading its heat into the
  bottom copper.
- **FAN2 tach** is read on its own pin (GPIO20) with its own 10 k pull-up and 10 k series resistor.
  FAN1's series resistor is also 10 k now, which protects the GPIO from fans that pull tach up to 12 V.
- **USB-C socket:** 16-pin TYPE-C-31-M-12 (its data pins are unused).
- **PD_PG pull-up** removed; the firmware uses the ESP32's internal pull-up.
- **Fan-header peg holes** are 1.3 mm (Molex recommends 1.25 mm; the KiCad library has 1.1 mm) so
  machine-inserted headers seat flat.
- **VBUS test pad (TP1)** next to the 12 V converter, for measuring the charger voltage.
- **Wider supply tracks:** the charger input (VBUS) is 0.8 mm wide (was 0.5 mm) for 7-fan loads, and
  no longer passes through a resistor pad on the way to the 5 V converter. The 12 V fan rail is 1 mm.
- **CH224A ground pad** has two vias straight down to the bottom ground plane (its exposed pad is
  its only ground pin).
- **CH224A DP/DM** are shorted together at the chip and not connected to the USB-C socket, as the
  datasheet describes for PD-only use. This turns off the QC/BC 1.2 fallbacks, which could only
  offer 5–12 V anyway; the fans need the 15 V PD profile.
- **Ground plane:** signal tracks on the bottom layer cut from about 260 mm to 150 mm. Estimated ground
  resistance from the USB-C socket and the 12 V output capacitors to the 12 V converter is now
  0.5–0.7 mΩ (a solid plane would be about 0.4 mΩ).

### Things to check on the first board

- **CH224A VBUS pin (R16):** the datasheet's reference circuit ties it straight to VBUS (as here,
  through R16 = 0 Ω), while its pin table says the pin tolerates 3.8 V. If PD negotiation misbehaves
  or U1 runs hot, this is the first thing to look at.
- **12 V converter temperature** with all fans at 100 %.
- **CH224A I2C:** check the boot log's I2C scan finds it at 0x22 or 0x23, and that "Charger Max
  Current" matches the charger's label. If the CH224A misbehaves with the bus connected, the
  sensors can be removed from the firmware, since it requests 15 V from its resistor with no I2C
  traffic needed.
- **Wi-Fi signal** with the XIAO in its sockets, compared with a bare XIAO (the 5 V converter is
  about 6 mm from the antenna end, 7.5 mm below it).
- Pull the XIAO **straight up** out of the SMD sockets; they're held only by their solder pads.

## Ordering

1. Upload `xiao/fab/*-gerbers.zip`. 2 layers, 1.6 mm, any solder-mask colour (green and blue were
   both quoted with Economic PCBA), HASL with or without lead. Don't pick OSP: that finish forces
   Standard PCBA.
2. PCB Assembly, **Economic**, top side. Upload a BOM and the CPL with the same suffix:
   - `*-jlcpcb.csv`: surface-mount parts only; you solder the fan headers.
   - `*-fanhdr-C19795120.csv`: JLCPCB also fits the fan headers (Molex 470533000). This was quoted
     as Economic PCBA with a small handling fee per header.
3. In the placement preview, check the orientation of U1, U4, U5, Q3, D1, J1, J6, J7 and the fan
   headers (locking ramp along the bottom board edge). L1 and L2 haven't been seen in JLCPCB's
   viewer yet; both are two-pad parts, so only their position matters.

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
