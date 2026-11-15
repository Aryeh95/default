// CR Box fan controller: 3D-printable case (base + lid)
//
// Export each part:
//   openscad -D 'part="base"' -o base.stl cr-box-case.scad
//   openscad -D 'part="lid"'  -o lid.stl  cr-box-case.scad
// part="assembly" shows both with a simplified board for a fit check.
//
// Coordinates below are KiCad board coordinates (mm): origin at the board's
// top-left corner, x to the right, y downwards, USB-C power socket on the
// left edge.  They are converted for OpenSCAD by B() below.
//
// Hardware: 4x M3 x 20 mm screws.  They pass through the lid, through the
// pillars that press the board down, and into the base standoffs.

part = "assembly";            // "base", "lid" or "assembly"

/* [Board] */
BW = 52;                      // board width
BH = 46;                      // board height
PCB_T = 1.6;
HOLES = [[3.5, 3.5], [48.5, 3.5], [3.5, 42.5], [48.5, 42.5]];

/* [Case] */
WALL = 2.0;
FLOOR = 2.0;
GAP = 0.5;                    // board edge to inner wall
STANDOFF_H = 5.0;             // room under the board for through-hole solder joints
CLEAR = 12.0;                 // board top to underside of the lid
LID_T = 2.0;
LIP_H = 2.5;                  // locating lip on the lid
LIP_T = 1.2;
LIP_FIT = 0.25;               // clearance between lip and wall
CORNER_R = 3.0;

/* [Screws] */
SCREW_PILOT = 2.6;            // self-tapping M3 into plastic; use 4.0 for M3 heat-set inserts
SCREW_CLEAR = 3.4;
STANDOFF_D = 6.5;
PILLAR_D = 6.0;

/* [Openings] */
// USB-C power socket J1 on the left edge
J1_Y = 14.0;
J1_Z = 1.6;                   // socket centre above the board top
J1_W = 13.0;                  // wide enough for the plug's overmould
J1_H = 7.5;
// XIAO's own USB-C port on the top edge (used to flash it the first time)
XIAO_X = 34.0;
XIAO_USB_Z = 10.1;            // 5 mm socket + 2.5 mm header spacer + 1 mm XIAO PCB + 1.6 mm
XIAO_USB_W = 12.5;
XIAO_USB_H = 7.5;
// Fan headers J2 and J3 (Molex 47053-1000), body outlines from the PCB
FANS = [[10.21, 37.76, 21.39, 44.84], [23.20, 37.76, 34.40, 44.84]];
FAN_MARGIN = 1.0;
// Slot over the I2C and UART headers J4 and J5 for sensor cables
SENSOR_SLOT = true;
SENSOR = [46.69, 15.19, 50.31, 38.44];
// Vents over the 12 V converter
VENTS = true;

/* [Mounting] */
EARS = true;                  // screw / zip-tie ears on the left and right of the base
EAR_LEN = 9;
EAR_W = 12;
EAR_T = 3;
EAR_HOLE = 4.2;

$fn = 48;

// ---------------------------------------------------------------------------
IN_W = BW + 2 * GAP;
IN_H = BH + 2 * GAP;
OUT_W = IN_W + 2 * WALL;
OUT_H = IN_H + 2 * WALL;
PCB_Z = FLOOR + STANDOFF_H;           // underside of the board
TOP_Z = PCB_Z + PCB_T;                // top of the board
BASE_H = TOP_Z + CLEAR;               // base walls end at the lid's underside

// board coordinates -> case coordinates (origin at the outer corner of the base)
function B(x, y) = [WALL + GAP + x, WALL + GAP + (BH - y)];

module rbox(w, h, d, r) {
    hull() for (x = [r, w - r], y = [r, h - r]) translate([x, y, 0]) cylinder(r = r, h = d);
}

module rrect_yz(w, h, d, r) {          // rounded rectangle in the YZ plane, extruded along X
    rotate([90, 0, 90]) translate([-w / 2, -h / 2, 0]) rbox(w, h, d, r);
}

module rrect_xz(w, h, d, r) {          // rounded rectangle in the XZ plane, extruded along Y
    rotate([90, 0, 0]) translate([-w / 2, -h / 2, 0]) rbox(w, h, d, r);
}

// ---------------------------------------------------------------------------
module base() {
    difference() {
        union() {
            difference() {
                rbox(OUT_W, OUT_H, BASE_H, CORNER_R);
                translate([WALL, WALL, FLOOR]) rbox(IN_W, IN_H, BASE_H, max(0.5, CORNER_R - WALL));
            }
            for (h = HOLES) translate([each B(h[0], h[1]), 0])
                cylinder(d = STANDOFF_D, h = PCB_Z);
            if (EARS) for (side = [0, 1]) {
                x0 = side == 0 ? -EAR_LEN : OUT_W - 0.01;
                translate([x0, OUT_H / 2 - EAR_W / 2, 0])
                    hull() {
                        cube([EAR_LEN + 0.01, EAR_W, EAR_T]);
                        translate([side == 0 ? EAR_LEN : 0, 0, 0]) cube([0.01, EAR_W, EAR_T + 3]);
                    }
            }
        }
        // screw pilots
        for (h = HOLES) translate([each B(h[0], h[1]), FLOOR]) cylinder(d = SCREW_PILOT, h = BASE_H);
        // USB-C power socket
        translate([-1, B(0, J1_Y)[1], TOP_Z + J1_Z]) rrect_yz(J1_W, J1_H, WALL + 2, 1.5);
        // XIAO USB port: a notch open at the top so the board drops in
        translate([B(XIAO_X, 0)[0], OUT_H + 1, 0]) {
            translate([0, 0, TOP_Z + XIAO_USB_Z]) rrect_xz(XIAO_USB_W, XIAO_USB_H, WALL + 2, 1.5);
            translate([-XIAO_USB_W / 2, -WALL - 2, TOP_Z + XIAO_USB_Z]) cube([XIAO_USB_W, WALL + 2, BASE_H]);
        }
        // ear holes
        if (EARS) for (x = [-EAR_LEN / 2 - 0.5, OUT_W + EAR_LEN / 2 + 0.5])
            translate([x, OUT_H / 2, -1]) cylinder(d = EAR_HOLE, h = EAR_T + 5);
        // label on the floor underside
        translate([OUT_W / 2, OUT_H / 2, -0.01]) mirror([1, 0, 0])
            linear_extrude(0.6) text("CR BOX FAN CTRL", size = 4, halign = "center", valign = "center");
    }
}

// ---------------------------------------------------------------------------
module lid_openings(h) {
    for (f = FANS) {
        p = B(f[0] - FAN_MARGIN, f[3] + FAN_MARGIN);
        translate([p[0], p[1], -1])
            rbox(f[2] - f[0] + 2 * FAN_MARGIN, f[3] - f[1] + 2 * FAN_MARGIN, h + 2, 1.0);
    }
    if (SENSOR_SLOT) {
        p = B(SENSOR[0] - 0.5, SENSOR[3] + 0.5);
        translate([p[0], p[1], -1]) rbox(SENSOR[2] - SENSOR[0] + 1, SENSOR[3] - SENSOR[1] + 1, h + 2, 1.0);
    }
    if (VENTS) for (i = [0:6]) {
        p = B(4 + i * 3, 33);
        translate([p[0], p[1], -1]) rbox(1.6, 11, h + 2, 0.8);
    }
}

module lid() {
    lip_w = IN_W - 2 * LIP_FIT;
    lip_h = IN_H - 2 * LIP_FIT;
    difference() {
        union() {
            // top plate
            translate([0, 0, LIP_H]) rbox(OUT_W, OUT_H, LID_T, CORNER_R);
            // locating lip
            translate([WALL + LIP_FIT, WALL + LIP_FIT, 0]) difference() {
                rbox(lip_w, lip_h, LIP_H + 0.01, max(0.5, CORNER_R - WALL));
                translate([LIP_T, LIP_T, -1]) rbox(lip_w - 2 * LIP_T, lip_h - 2 * LIP_T, LIP_H + 2, 0.5);
            }
            // pillars that clamp the board against the standoffs
            for (h = HOLES) translate([each B(h[0], h[1]), LIP_H - CLEAR])
                cylinder(d = PILLAR_D, h = CLEAR + 0.01);
        }
        for (h = HOLES) translate([each B(h[0], h[1]), -CLEAR]) cylinder(d = SCREW_CLEAR, h = CLEAR * 2 + LID_T);
        translate([0, 0, 0]) lid_openings(LIP_H + LID_T);
        // gap in the lip where the XIAO USB notch is
        translate([B(XIAO_X, 0)[0] - XIAO_USB_W / 2, OUT_H - WALL - 2, -1]) cube([XIAO_USB_W, WALL + 3, LIP_H + 1]);
        // gap in the lip at the fan openings near the bottom edge
        for (f = FANS) translate([B(f[0] - FAN_MARGIN, 0)[0], -1, -1])
            cube([f[2] - f[0] + 2 * FAN_MARGIN, WALL + 3, LIP_H + 1]);
        // labels, debossed into the top
        for (i = [0:1]) {
            f = FANS[i];
            p = B((f[0] + f[2]) / 2, f[1] - 3.2);
            translate([p[0], p[1], LIP_H + LID_T - 0.6])
                linear_extrude(1) text(i == 0 ? "FAN1" : "FAN2", size = 3.2, halign = "center", valign = "center");
        }
        if (SENSOR_SLOT) {
            p = B(SENSOR[0] - 2.6, (SENSOR[1] + SENSOR[3]) / 2);
            translate([p[0], p[1], LIP_H + LID_T - 0.6]) rotate([0, 0, 90])
                linear_extrude(1) text("SENSOR", size = 2.6, halign = "center", valign = "center");
        }
    }
}

// ---------------------------------------------------------------------------
// Simplified board and tall parts, for the fit check only
module board_model() {
    color("darkgreen") translate([WALL + GAP, WALL + GAP, PCB_Z]) cube([BW, BH, PCB_T]);
    board_parts();
}

module board_parts() {
    module blk(x0, y0, x1, y1, h, c) {
        p = B(x0, y1);
        color(c) translate([p[0], p[1], TOP_Z]) cube([x1 - x0, y1 - y0, h]);
    }
    blk(8.6, 1.9, 20.2, 9.5, 10.2, "black");          // 5 V module U2
    blk(-0.4, 9.6, 7.0, 18.4, 3.3, "silver");         // USB-C socket J1
    for (f = FANS) blk(f[0], f[1], f[2], f[3], 11.4, "white");  // fan headers
    blk(25.1, 0.8, 27.6, 22.2, 5.0, "black");         // XIAO sockets
    blk(40.4, 0.8, 42.9, 22.2, 5.0, "black");
    blk(25.1, 1.0, 42.9, 22.0, 1.0, "royalblue");     // XIAO PCB (drawn at the board, lifted below)
    blk(14.4, 24.0, 20.6, 30.0, 4.5, "dimgray");      // inductor L1
    blk(46.7, 15.2, 50.3, 38.4, 8.5, "black");        // sensor pin headers
}

module xiao_model() {
    p = B(25.1, 22.0);
    color("royalblue") translate([p[0], p[1], TOP_Z + 7.5]) cube([17.8, 21.0, 1.0]);
    q = B(29.6, 7.0);
    color("silver") translate([q[0], q[1], TOP_Z + 8.5]) cube([8.9, 7.3, 3.2]);          // USB-C
    r = B(26.5, 20.0);
    color("silver") translate([r[0], r[1], TOP_Z + 8.5]) cube([15, 10, 2.4]);           // shield can
}

module lid_in_place(lift = 0) translate([0, 0, BASE_H - LIP_H + lift]) lid();

if (part == "base") base();
else if (part == "collide") {   // should render empty: lid or base touching a part
    intersection() { lid_in_place(); union() { board_parts(); xiao_model(); } }
    intersection() { base(); union() { board_parts(); xiao_model(); } }
}
else if (part == "lid") translate([0, OUT_H, LIP_H + LID_T]) rotate([180, 0, 0]) lid();  // print upside down
else {
    color("lightgray") base();
    board_model();
    xiao_model();
    color("orange", 0.55) lid_in_place(part == "closed" ? 0 : 25);
}
