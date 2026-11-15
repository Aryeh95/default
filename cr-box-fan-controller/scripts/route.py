#!/usr/bin/python3.12
"""Route the board: hand-placed power tracks first, then a small grid router.

The router works on a 0.1 mm grid with exact clearance checking (distance
transform against all foreign copper), so its output is checked again by
KiCad's own DRC afterwards.
"""
import heapq
import math
import os
import sys

import numpy as np
import pcbnew
from pcbnew import FromMM, ToMM, VECTOR2I
from scipy import ndimage

sys.path.insert(0, os.path.dirname(__file__))
import design as D
import gen_board as G

RES = 0.1
NX = int(round(D.BOARD_W / RES)) + 1
NY = int(round(D.BOARD_H / RES)) + 1
MARGIN = 0.06          # extra clearance to absorb grid quantisation
EDGE = 0.45            # copper to board edge
LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu)


def ci(v):
    return int(round(v / RES))


class Router:
    def __init__(self, board):
        self.board = board
        self.own = np.zeros((2, NY, NX), dtype=np.int32)       # 0 free, >0 net code, -1 hard
        self.padmask = np.zeros((2, NY, NX), dtype=bool)        # any pad copper (no via-in-pad)
        self.holes = np.zeros((NY, NX), dtype=bool)             # drilled holes
        self.parent = {}                                        # union-find over groups
        self.cellgrp = {}                                       # (l, iy, ix) -> group
        self.netgroups = {}                                     # net -> set(groups)
        self.padgrp = {}
        self.padcentre = {}                                     # interior cell -> pad centre (mm)
        self.failed = []
        self._setup()

    # --- union-find ---------------------------------------------------------
    def find(self, g):
        while self.parent[g] != g:
            self.parent[g] = self.parent[self.parent[g]]
            g = self.parent[g]
        return g

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.parent[b] = a

    def newgroup(self, net):
        g = len(self.parent)
        self.parent[g] = g
        self.netgroups.setdefault(net, set()).add(g)
        return g

    # --- setup --------------------------------------------------------------
    def _setup(self):
        own = self.own
        e = ci(EDGE)
        own[:, :e, :] = -1
        own[:, -e:, :] = -1
        own[:, :, :e] = -1
        own[:, :, -e:] = -1
        yy, xx = np.mgrid[0:NY, 0:NX]
        # rounded corners + screw-head keep-out around mounting holes
        for hx, hy in D.HOLES:
            d = np.hypot(xx * RES - hx, yy * RES - hy)
            own[:, d < 3.3] = -1
            self.holes |= d < 1.6
        x0, y0, x1, y1 = D.ANT_KEEPOUT
        own[:, ci(y0):ci(y1) + 1, ci(x0):ci(x1) + 1] = -1

        for fp in self.board.GetFootprints():
            for pad in fp.Pads():
                bb = pad.GetBoundingBox()
                bx0, by0 = ToMM(bb.GetLeft()), ToMM(bb.GetTop())
                bx1, by1 = ToMM(bb.GetRight()), ToMM(bb.GetBottom())
                net = pad.GetNetCode()
                has_cu = False
                for li, layer in enumerate(LAYERS):
                    if not pad.IsOnLayer(layer):
                        continue
                    has_cu = True
                    sl = (li, slice(max(0, math.floor(by0 / RES)), math.ceil(by1 / RES) + 1),
                          slice(max(0, math.floor(bx0 / RES)), math.ceil(bx1 / RES) + 1))
                    own[sl] = net if net > 0 else -1
                    self.padmask[sl] = True
                if pad.GetDrillSize().x > 0:
                    c = pad.GetPosition()
                    r = ToMM(pad.GetDrillSize().x) / 2
                    d = np.hypot(xx * RES - ToMM(c.x), yy * RES - ToMM(c.y))
                    self.holes |= d < r
                    if not has_cu:
                        own[:, d < r + 0.3] = -1
                if has_cu and net > 0:
                    g = self.newgroup(net)
                    self.padgrp[(fp.GetReference(), pad.GetNumber(), ToMM(pad.GetPosition().x),
                                 ToMM(pad.GetPosition().y))] = g
                    # interior cells (shrunk a little) are valid track end points
                    for li, layer in enumerate(LAYERS):
                        if not pad.IsOnLayer(layer):
                            continue
                        for iy in range(math.ceil((by0 + 0.1) / RES), math.floor((by1 - 0.1) / RES) + 1):
                            for ix in range(math.ceil((bx0 + 0.1) / RES), math.floor((bx1 - 0.1) / RES) + 1):
                                k = (li, iy, ix)
                                self.padcentre[k] = (ToMM(pad.GetPosition().x), ToMM(pad.GetPosition().y))
                                if k in self.cellgrp:
                                    self.union(self.cellgrp[k], g)
                                else:
                                    self.cellgrp[k] = g

    # --- copper bookkeeping -------------------------------------------------
    def stamp(self, li, x, y, r, net):
        """Mark a disc of copper (mm coords) on layer li."""
        n = int(math.ceil(r / RES)) + 1
        cx, cy = ci(x), ci(y)
        ys = slice(max(0, cy - n), min(NY, cy + n + 1))
        xs = slice(max(0, cx - n), min(NX, cx + n + 1))
        yy, xx = np.mgrid[ys, xs]
        m = np.hypot(xx * RES - x, yy * RES - y) <= r
        sub = self.own[li, ys, xs]
        sub[m & (sub == 0)] = net

    def add_track(self, net, li, pts, w, grp=None):
        code = self.board.GetNetcodeFromNetname(net)
        netinfo = self.board.FindNet(net)
        if grp is None:
            grp = self.newgroup(code)
        for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
            if (xa, ya) == (xb, yb):
                continue
            t = pcbnew.PCB_TRACK(self.board)
            t.SetStart(VECTOR2I(FromMM(xa), FromMM(ya)))
            t.SetEnd(VECTOR2I(FromMM(xb), FromMM(yb)))
            t.SetWidth(FromMM(w))
            t.SetLayer(LAYERS[li])
            t.SetNet(netinfo)
            self.board.Add(t)
            n = max(1, int(math.hypot(xb - xa, yb - ya) / (RES / 2)))
            for i in range(n + 1):
                x = xa + (xb - xa) * i / n
                y = ya + (yb - ya) * i / n
                self.stamp(li, x, y, w / 2, code)
                k = (li, ci(y), ci(x))
                if k in self.cellgrp:
                    self.union(self.cellgrp[k], grp)
                else:
                    self.cellgrp[k] = grp
        return grp

    def add_via(self, net, x, y, dia, drill, grp=None):
        code = self.board.GetNetcodeFromNetname(net)
        if grp is None:
            grp = self.newgroup(code)
        v = pcbnew.PCB_VIA(self.board)
        v.SetPosition(VECTOR2I(FromMM(x), FromMM(y)))
        v.SetWidth(pcbnew.F_Cu, FromMM(dia))
        v.SetDrill(FromMM(drill))
        v.SetNet(self.board.FindNet(net))
        self.board.Add(v)
        for li in (0, 1):
            self.stamp(li, x, y, dia / 2, code)
            k = (li, ci(y), ci(x))
            if k in self.cellgrp:
                self.union(self.cellgrp[k], grp)
            else:
                self.cellgrp[k] = grp
        yy, xx = np.mgrid[0:NY, 0:NX]
        self.holes |= np.hypot(xx * RES - x, yy * RES - y) < drill / 2
        return grp

    # --- automatic routing --------------------------------------------------
    def groups_of(self, net):
        code = self.board.GetNetcodeFromNetname(net)
        return {self.find(g) for g in self.netgroups.get(code, ())}

    def route_net(self, net, w, clr=0.2, via=(0.7, 0.3), allow_via=True, bottom_cost=1.4,
                  only=None, start=None):
        """Join all copper groups of a net.  `only`: list of pad refs to limit to."""
        code = self.board.GetNetcodeFromNetname(net)
        while True:
            groups = self.groups_of(net)
            if only is not None:
                wanted = {self.find(g) for (ref, _n, _x, _y), g in self.padgrp.items()
                          if ref in only and self.find(g) in groups}
            else:
                wanted = set(groups)
            if start:
                main = self.find(next(g for (ref, num, _x, _y), g in self.padgrp.items()
                                      if (ref, num) == start))
            else:
                # biggest group = the one with most cells
                size = {}
                for k, g in self.cellgrp.items():
                    g = self.find(g)
                    if g in groups:
                        size[g] = size.get(g, 0) + 1
                main = max(groups, key=lambda g: size.get(g, 0))
            targets = wanted - {main}
            if not targets:
                return True
            if not self._connect(code, main, targets, w, clr, via, allow_via, bottom_cost):
                bad = sorted({ref + "." + num for (ref, num, _x, _y), g in self.padgrp.items()
                              if self.find(g) in targets})
                self.failed.append((net, bad))
                print("  !! could not finish", net)
                return False

    def _connect(self, code, main, targets, w, clr, via, allow_via, bottom_cost):
        need = clr + w / 2 + MARGIN
        allow = []
        dist = []
        for li in (0, 1):
            foreign = (self.own[li] != 0) & (self.own[li] != code)
            d = ndimage.distance_transform_edt(~foreign) * RES
            dist.append(d)
            allow.append(d >= need)
        vdia, vdrill = via
        vneed = clr + vdia / 2 + MARGIN
        via_ok = (dist[0] >= vneed) & (dist[1] >= vneed)
        via_ok &= ndimage.distance_transform_edt(~(self.padmask[0] | self.padmask[1])) * RES >= vdia / 2 + 0.15
        via_ok &= ndimage.distance_transform_edt(~self.holes) * RES >= vdrill / 2 + 0.5
        if not allow_via:
            via_ok[:] = False
        A = [a.tobytes() for a in allow]
        V = via_ok.tobytes()

        src, tgt = [], set()
        for k, g in self.cellgrp.items():
            g = self.find(g)
            if g == main:
                src.append(k)
            elif g in targets:
                tgt.add(k)
        best = {}
        prev = {}
        heap = []
        for k in src:
            best[k] = 0
            heap.append((0, k))
        heapq.heapify(heap)
        steps = ((0, 1, 10), (0, -1, 10), (1, 0, 10), (-1, 0, 10),
                 (1, 1, 14), (1, -1, 14), (-1, 1, 14), (-1, -1, 14))
        lcost = (1.0, bottom_cost)
        end = None
        while heap:
            c, k = heapq.heappop(heap)
            if best.get(k, 1e18) < c:
                continue
            if k in tgt:
                end = k
                break
            li, iy, ix = k
            for dy, dx, sc in steps:
                ny, nx = iy + dy, ix + dx
                if not (0 <= ny < NY and 0 <= nx < NX):
                    continue
                nk = (li, ny, nx)
                if not A[li][ny * NX + nx] and nk not in tgt:
                    continue
                nc = c + sc * lcost[li]
                if nc < best.get(nk, 1e18):
                    best[nk] = nc
                    prev[nk] = k
                    heapq.heappush(heap, (nc, nk))
            if V[iy * NX + ix]:
                nk = (1 - li, iy, ix)
                nc = c + 250
                if nc < best.get(nk, 1e18):
                    best[nk] = nc
                    prev[nk] = k
                    heapq.heappush(heap, (nc, nk))
        if end is None:
            return False
        path = [end]
        while path[-1] in prev:
            path.append(prev[path[-1]])
        path.reverse()
        grp = self.cellgrp[path[0]]
        netname = self.board.FindNet(code).GetNetname()
        # split into per-layer polylines, vias at layer changes
        run = [path[0]]
        for k in path[1:]:
            if k[0] != run[-1][0]:
                self._emit(netname, run, w, grp)
                self.add_via(netname, k[2] * RES, k[1] * RES, vdia, vdrill, grp)
                run = [k]
            else:
                run.append(k)
        self._emit(netname, run, w, grp)
        self.union(grp, self.cellgrp[end])
        return True

    def _emit(self, net, run, w, grp):
        if len(run) < 2:
            return
        pts = [(run[0][2] * RES, run[0][1] * RES)]
        for a, b, c in zip(run, run[1:], run[2:]):
            if (b[1] - a[1], b[2] - a[2]) != (c[1] - b[1], c[2] - b[2]):
                pts.append((b[2] * RES, b[1] * RES))
        pts.append((run[-1][2] * RES, run[-1][1] * RES))
        # finish on the pad centre when the run starts / ends inside a pad
        if run[0] in self.padcentre:
            pts.insert(0, self.padcentre[run[0]])
        if run[-1] in self.padcentre:
            pts.append(self.padcentre[run[-1]])
        self.add_track(net, run[0][0], pts, w, grp)


def manual(r):
    T, B = 0, 1
    # USB-C CC lines straight into the CH224A
    r.add_track("CC_A", T, [(6.18, 13.5), (11.86, 13.5)], 0.25)
    r.add_track("CC_B", T, [(6.18, 14.5), (11.86, 14.5)], 0.25)
    r.add_track("DPDM", T, [(17.14, 13.5), (17.14, 14.5)], 0.3)
    # VBUS: both connector pins, joined on the bottom layer
    g = r.add_track("VBUS", T, [(6.18, 15.52), (8.3, 15.52), (8.3, 22.4), (9.4, 23.5), (9.62, 23.9)], 0.8)
    r.add_track("VBUS", T, [(9.63, 23.9), (9.63, 26.05)], 0.6, g)
    r.add_track("VBUS", T, [(9.64, 26.05), (10.6, 26.05), (11.3, 25.6)], 0.5, g)
    r.add_track("VBUS", T, [(8.3, 17.325), (9.8, 17.325)], 0.3, g)
    r.add_track("VBUS_DET", T, [(11.86, 15.5), (10.6, 15.5), (9.8, 15.675)], 0.25)
    r.add_track("CFG1", T, [(11.86, 16.5), (10.66, 16.5), (10.66, 18.8), (10.4, 19.075)], 0.25)
    r.add_track("VBUS", T, [(6.18, 12.48), (7.75, 12.48), (8.3, 11.9)], 0.6, g)
    r.add_track("VBUS", T, [(8.53, 11.6), (8.53, 9.6), (10.6, 7.5), (11.8, 7.5)], 0.6, g)
    r.add_via("VBUS", 7.75, 12.48, 0.9, 0.5, g)
    r.add_via("VBUS", 8.3, 16.2, 0.9, 0.5, g)
    r.add_track("VBUS", B, [(7.75, 12.48), (8.3, 13.2), (8.3, 16.2)], 0.8, g)
    # buck: switch node, bootstrap, feedback, enable
    g = r.add_track("SW", T, [(9.64, 27.0), (15.25, 27.0)], 0.6)
    r.add_track("SW", T, [(9.64, 27.0), (8.5, 27.0), (8.5, 29.3), (9.1, 29.9)], 0.25, g)
    r.add_track("BOOT", T, [(7.36, 27.95), (7.36, 29.4), (7.72, 30.1)], 0.25)
    r.add_track("FB", T, [(5.42, 22.5), (5.42, 26.05), (7.36, 26.05)], 0.25)
    r.add_track("BUCK_EN", T, [(5.42, 29.7), (5.42, 27.9), (6.3, 27.0), (7.36, 27.0)], 0.25)
    # buck grounds: IC pin -> input cap -> vias to the bottom plane
    g = r.add_track("GND", T, [(9.64, 27.95), (10.6, 27.95), (11.3, 28.4)], 0.5)
    r.add_track("GND", T, [(12.4, 28.6), (13.3, 29.1)], 0.5, g)
    r.add_via("GND", 13.3, 29.1, 0.8, 0.4, g)
    r.add_track("GND", T, [(11.9, 28.6), (11.9, 30.3)], 0.5, g)
    r.add_via("GND", 11.9, 30.3, 0.8, 0.4, g)
    g = r.add_track("GND", T, [(11.18, 23.9), (12.6, 23.6)], 0.4)
    r.add_via("GND", 12.6, 23.6, 0.8, 0.4, g)
    g = r.add_track("GND", T, [(3.78, 26.05), (3.78, 27.9)], 0.4)
    r.add_track("GND", T, [(3.78, 27.0), (2.5, 27.0)], 0.4, g)
    r.add_via("GND", 2.5, 27.0, 0.8, 0.4, g)
    for y in (24.3, 27.0, 29.7):
        g = r.add_track("GND", T, [(24.88, y), (26.7, y)], 0.6)
        r.add_via("GND", 26.7, y, 0.8, 0.4, g)
    # stitching vias so no top-side pour is left hanging off a single pad
    r.add_via("GND", 34.0, 8.0, 0.8, 0.4)
    r.add_via("GND", 21.0, 39.2, 0.8, 0.4)
    # 12 V: inductor -> output caps -> both fan headers
    g = r.add_track("+12V", T, [(19.75, 24.7), (21.93, 24.7)], 1.0)
    r.add_track("+12V", T, [(19.75, 27.0), (21.93, 27.0)], 1.0, g)
    r.add_track("+12V", T, [(19.75, 29.3), (21.93, 29.3)], 1.0, g)
    r.add_track("+12V", T, [(21.93, 29.7), (21.93, 37.0)], 1.0, g)
    r.add_track("+12V", T, [(21.93, 37.0), (15.5, 37.0), (14.54, 37.96), (14.54, 41.0)], 1.0, g)
    r.add_track("+12V", T, [(21.93, 37.0), (26.6, 37.0), (27.54, 37.94), (27.54, 41.0)], 1.0, g)


PLAN = [
    # net, width, kwargs
    ("GND", 0.4, {"via": (0.8, 0.4), "only": ["C4"], "bottom_cost": 1.0}),
    ("VBUS", 0.3, {}),
    ("+12V", 0.25, {}),
    ("VHV", 0.4, {}),
    ("VBUS_DET", 0.25, {}),
    ("CFG1", 0.25, {}),
    ("+5V", 0.5, {"via": (0.8, 0.4)}),
    ("XIAO_5V", 0.5, {"via": (0.8, 0.4)}),
    ("FAN_PWM", 0.3, {}),
    ("FAN_TACH", 0.25, {}),
    ("Q3_B", 0.25, {}),
    ("VSENSE", 0.25, {}),
    ("PD_PG", 0.25, {}),
    ("SDA", 0.25, {}),
    ("SCL", 0.25, {}),
    ("UART_TX", 0.25, {}),
    ("UART_RX", 0.25, {}),
    ("TACH_MCU", 0.25, {}),
    ("PWM_MCU", 0.25, {}),
    ("FAN_EN", 0.25, {}),
    ("+3V3", 0.4, {"via": (0.8, 0.4)}),
    ("GND", 0.4, {"via": (0.8, 0.4), "bottom_cost": 1.0}),
]


def main():
    board = pcbnew.LoadBoard(G.PCB)
    for t in list(board.GetTracks()):
        board.Remove(t)
    r = Router(board)
    manual(r)
    for net, w, kw in PLAN:
        print("routing", net)
        r.route_net(net, w, **kw)
    G.finish_silk(board)
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    pcbnew.SaveBoard(G.PCB, board)
    print("tracks:", len(board.GetTracks()), "failed:", r.failed)


if __name__ == "__main__":
    main()
