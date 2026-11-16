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
import paths

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
        m = np.hypot(xx * RES - x, yy * RES - y) <= r + 0.04
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
            # a track may always run over copper of its own net (e.g. out of a pad
            # squeezed between fine-pitch neighbours)
            allow.append((d >= need) | (self.own[li] == code))
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
    # --- USB-C: VBUS ---------------------------------------------------------
    g = r.add_track("VBUS", T, [(7.29, 16.45), (8.9, 16.45)], 0.5)
    r.add_track("VBUS", T, [(8.9, 16.45), (8.9, 22.6), (9.62, 23.3), (9.62, 23.9)], 0.8, g)
    r.add_track("VBUS", T, [(9.63, 23.9), (9.63, 26.05)], 0.6, g)
    r.add_track("VBUS", T, [(9.64, 26.05), (10.6, 26.05), (11.3, 25.6)], 0.5, g)
    r.add_via("VBUS", 8.9, 17.4, 0.9, 0.5, g)
    r.add_track("VBUS", T, [(7.29, 11.55), (8.9, 11.55)], 0.5, g)
    r.add_via("VBUS", 8.9, 11.55, 0.9, 0.5, g)
    r.add_track("VBUS", B, [(8.9, 11.55), (8.9, 17.4)], 0.8, g)
    if D.VARIANT == "module":
        # join the duplicated D+/D- contacts of the reversible socket:
        # D+ behind the contact row (under the socket body), D- in front of it
        r.add_track("USB_DP", T, [(7.29, 13.75), (6.1, 13.75), (6.1, 14.75), (7.29, 14.75)], 0.2)
        r.add_track("USB_DM", T, [(7.29, 13.25), (8.5, 13.25), (8.5, 14.25), (7.29, 14.25)], 0.2)
        g = r.add_track("GND", T, [(25.6, 9.55), (24.5, 9.9)], 0.4)
        r.add_via("GND", 24.3, 10.0, 0.8, 0.4, g)
        # EN: module pin 8 -> RC (R21, C22) and RESET button, under the left-side exits
        g = r.add_track("EN", T, [(28.1, 12.6), (26.9, 12.6)], 0.25)
        r.add_via("EN", 26.9, 12.6, 0.6, 0.3, g)
        r.add_track("EN", B, [(26.9, 12.6), (26.9, 17.8), (26.3, 18.4)], 0.25, g)
        r.add_via("EN", 26.3, 18.4, 0.6, 0.3, g)
        r.add_track("EN", T, [(26.3, 18.4), (26.5, 19.42)], 0.25, g)
        r.add_track("EN", T, [(24.9, 19.3), (26.5, 19.42)], 0.25, g)
        r.add_track("EN", T, [(24.9, 19.3), (24.9, 21.1)], 0.25, g)
        # PD_PG: module pin 10 -> CH224A pin 10, under the other left-side exits
        g = r.add_track("PD_PG", T, [(28.1, 14.2), (25.9, 14.2)], 0.25)
        r.add_via("PD_PG", 25.9, 14.2, 0.6, 0.3, g)
        r.add_track("PD_PG", B, [(25.9, 14.2), (15.9, 13.2)], 0.25, g)
        r.add_via("PD_PG", 15.9, 13.2, 0.6, 0.3, g)
        r.add_track("PD_PG", T, [(15.9, 13.2), (15.0, 12.6), (15.0, 12.24)], 0.25, g)
        # +3V3 reference pin of the USB ESD array, down to R21's +3V3 pad
        g = r.add_track("+3V3", T, [(22.14, 16.6), (23.3, 16.6)], 0.3)
        r.add_via("+3V3", 23.3, 16.6, 0.6, 0.3, g)
        r.add_track("+3V3", B, [(23.3, 16.6), (23.3, 18.3)], 0.3, g)
        r.add_via("+3V3", 23.3, 18.3, 0.6, 0.3, g)
        r.add_track("+3V3", T, [(23.3, 18.3), (23.3, 19.3)], 0.3, g)
        # short escapes to the bottom layer for two pins in crowded spots
        g = r.add_track("TACH_MCU", T, [(39.9, 15.0), (41.3, 15.0)], 0.25)
        r.add_via("TACH_MCU", 41.3, 15.0, 0.6, 0.3, g)
        g = r.add_track("FAN_EN", T, [(29.2, 15.9), (29.2, 17.1)], 0.25)
        r.add_via("FAN_EN", 29.2, 17.1, 0.6, 0.3, g)
    else:
        g = r.add_track("GND", T, [(42.38, 21.6), (43.3, 21.6)], 0.4)
        r.add_via("GND", 43.3, 21.6, 0.8, 0.4, g)
    # CC lines out of the fine-pitch contact row
    r.add_track("CC_A", T, [(7.29, 12.75), (11.0, 12.75)], 0.2)
    g = r.add_track("CC_B", T, [(7.29, 15.75), (10.4, 15.75)], 0.2)
    r.add_via("CC_B", 10.4, 15.75, 0.6, 0.3, g)
    r.add_track("CC_B", B, [(10.4, 15.75), (11.7, 14.45), (11.7, 13.6)], 0.2, g)
    r.add_via("CC_B", 11.7, 13.6, 0.6, 0.3, g)
    r.add_track("CC_B", T, [(11.7, 13.6), (12.0, 13.0), (12.0, 12.24)], 0.2, g)
    # ground pin of the PWM transistor sits in a pour island too small for a via
    g = r.add_track("GND", T, [(37.06, 39.45), (35.5, 39.45)], 0.4)
    r.add_via("GND", 35.5, 39.45, 0.8, 0.4, g)
    # top-layer pour island at the UART header ground pin
    g = r.add_track("GND", T, [(48.5, 29.0), (46.4, 29.0)], 0.5)
    r.add_via("GND", 46.4, 29.0, 0.8, 0.4, g)
    # --- CH224A --------------------------------------------------------------
    r.add_track("DPDM", T, [(11.0, 6.96), (12.0, 6.96)], 0.3)
    # --- 12 V buck (same layout as rev A) -------------------------------------
    g = r.add_track("SW", T, [(9.64, 27.0), (15.875, 27.0)], 0.6)
    r.add_track("SW", T, [(9.64, 27.0), (8.5, 27.0), (8.5, 29.3), (9.1, 29.9)], 0.25, g)
    r.add_track("BOOT", T, [(7.36, 27.95), (7.36, 29.4), (7.72, 30.1)], 0.25)
    r.add_track("FB", T, [(5.42, 22.5), (5.42, 26.05), (7.36, 26.05)], 0.25)
    r.add_track("BUCK_EN", T, [(5.42, 29.7), (5.42, 27.9), (6.3, 27.0), (7.36, 27.0)], 0.25)
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
        g = r.add_track("GND", T, [(24.88, y), (25.95, y)], 0.6)
        r.add_via("GND", 25.95, y, 0.8, 0.4, g)
    g = r.add_track("+12V", T, [(19.125, 24.7), (21.93, 24.7)], 1.0)
    r.add_track("+12V", T, [(19.125, 27.0), (21.93, 27.0)], 1.0, g)
    r.add_track("+12V", T, [(19.125, 29.3), (21.93, 29.3)], 1.0, g)
    r.add_track("+12V", T, [(21.93, 29.7), (21.93, 37.0)], 1.0, g)
    r.add_track("+12V", T, [(21.93, 37.0), (15.5, 37.0), (14.54, 37.96), (14.54, 41.0)], 1.0, g)
    r.add_track("+12V", T, [(21.93, 37.0), (26.6, 37.0), (27.54, 37.94), (27.54, 41.0)], 1.0, g)
    # --- 5 V buck (mirror of the 12 V layout) ---------------------------------
    g = r.add_track("SW5", T, [(32.64, 29.0), (37.5, 29.0)], 0.6)
    r.add_track("SW5", T, [(32.64, 29.0), (31.5, 29.0), (31.5, 30.8), (32.1, 31.4)], 0.25, g)
    r.add_track("BOOT5", T, [(30.36, 29.95), (30.36, 31.0), (30.72, 31.6)], 0.25)
    r.add_track("FB5", T, [(28.6, 25.4), (28.6, 29.0)], 0.25)
    r.add_track("FB5", T, [(28.6, 28.05), (30.36, 28.05)], 0.25)
    g = r.add_track("VBUS", T, [(32.64, 26.625), (32.64, 28.05)], 0.5)
    r.add_track("VBUS", T, [(32.64, 28.05), (33.6, 28.05), (34.2, 27.6)], 0.5, g)
    g = r.add_track("GND", T, [(32.64, 29.95), (33.6, 29.95), (34.2, 30.4)], 0.5)
    r.add_track("GND", T, [(34.9, 30.48), (34.9, 31.9)], 0.5, g)
    r.add_via("GND", 34.9, 31.9, 0.8, 0.4, g)
    g = r.add_track("GND", T, [(32.64, 24.975), (31.4, 25.5)], 0.4)
    r.add_via("GND", 31.4, 25.5, 0.8, 0.4, g)
    # feedback divider top: bring +5V over on the bottom layer
    g = r.add_track("+5V", T, [(27.0, 25.4), (27.0, 27.2)], 0.3)
    r.add_via("+5V", 27.0, 26.3, 0.7, 0.3, g)
    r.add_track("+5V", B, [(27.0, 26.3), (27.0, 33.0), (40.2, 33.0), (41.0, 32.2)], 0.4, g)
    r.add_via("+5V", 41.0, 32.2, 0.7, 0.3, g)
    r.add_track("+5V", T, [(41.0, 32.2), (42.13, 31.0)], 0.4, g)
    # USB-C shield pin next to the ground contacts
    r.add_track("GND", T, [(6.38, 18.32), (7.29, 17.25)], 0.4)
    # small ground pads that the pour can't reach on its own
    g = r.add_track("GND", T, [(18.78, 6.4), (19.9, 6.4)], 0.4)
    r.add_via("GND", 19.9, 6.4, 0.8, 0.4, g)
    # stitching vias for top-layer pour islands at the headers
    r.add_via("GND", 21.0, 39.2, 0.8, 0.4)
    r.add_via("GND", 46.8, 15.6, 0.8, 0.4)
    g = r.add_track("+5V", T, [(40.5, 27.5), (42.13, 27.5)], 0.8)
    r.add_track("+5V", T, [(40.5, 30.5), (42.13, 30.5)], 0.8, g)
    for y0, y1 in ((27.5, 25.9), (30.5, 32.1)):
        g = r.add_track("GND", T, [(45.07, y0), (45.07, y1)], 0.6)
        r.add_via("GND", 45.07, y1, 0.8, 0.4, g)


def _inside(px, py, poly):
    """Even-odd point-in-polygon test for arrays of points."""
    inside = np.zeros(px.shape, dtype=bool)
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        cond = (y0 > py) != (y1 > py)
        xint = x0 + (py - y0) * (x1 - x0) / ((y1 - y0) if y1 != y0 else 1e-12)
        inside ^= cond & (px < xint)
    return inside


def stitch_islands(board, r, dia=0.8, drill=0.4):
    """Give every top-layer GND pour island that has no via or through-hole
    ground pad of its own a via down to the bottom-layer pour."""
    gnd = board.FindNet("GND")
    code = gnd.GetNetCode()
    need = 0.2 + dia / 2 + MARGIN + 0.05
    okmask = np.ones((NY, NX), dtype=bool)
    for li in (0, 1):
        foreign = (r.own[li] != 0) & (r.own[li] != code)
        okmask &= ndimage.distance_transform_edt(~foreign) * RES >= need
    okmask &= ndimage.distance_transform_edt(~r.holes) * RES >= drill / 2 + 0.5
    anchors = [(ToMM(v.GetPosition().x), ToMM(v.GetPosition().y)) for v in board.GetTracks()
               if v.GetClass() == "PCB_VIA" and v.GetNetname() == "GND"]
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname() == "GND" and pad.GetDrillSize().x > 0:
                anchors.append((ToMM(pad.GetPosition().x), ToMM(pad.GetPosition().y)))
    added = 0
    for z in board.Zones():
        if z.GetIsRuleArea() or z.GetNetname() != "GND" or z.GetLayer() != pcbnew.F_Cu:
            continue
        polys = z.GetFilledPolysList(pcbnew.F_Cu)
        for i in range(polys.OutlineCount()):
            ch = polys.Outline(i)
            pts = [(ToMM(ch.CPoint(k).x), ToMM(ch.CPoint(k).y)) for k in range(ch.PointCount())]
            holes = []
            for h in range(polys.HoleCount(i)):
                hc = polys.Hole(i, h)
                holes.append([(ToMM(hc.CPoint(k).x), ToMM(hc.CPoint(k).y)) for k in range(hc.PointCount())])
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            ax = np.array([a[0] for a in anchors])
            ay = np.array([a[1] for a in anchors])
            if len(anchors) and _inside(ax, ay, pts).any():
                continue
            i0, i1 = max(0, ci(min(xs))), min(NX - 1, ci(max(xs)))
            j0, j1 = max(0, ci(min(ys))), min(NY - 1, ci(max(ys)))
            gx, gy = np.meshgrid(np.arange(i0, i1 + 1) * RES, np.arange(j0, j1 + 1) * RES)
            mask = _inside(gx, gy, pts)
            for hp in holes:
                mask &= ~_inside(gx, gy, hp)
            if not mask.any():
                continue
            d = ndimage.distance_transform_edt(mask) * RES
            d[~okmask[j0:j1 + 1, i0:i1 + 1]] = 0
            k = np.unravel_index(np.argmax(d), d.shape)
            if d[k] < dia / 2 + 0.1:
                print("  island at (%.1f, %.1f) too small for a via" % (gx[k], gy[k]))
                continue
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(VECTOR2I(FromMM(float(gx[k])), FromMM(float(gy[k]))))
            v.SetWidth(pcbnew.F_Cu, FromMM(dia))
            v.SetDrill(FromMM(drill))
            v.SetNet(gnd)
            board.Add(v)
            r.add_via  # (bookkeeping below keeps later vias apart)
            for li in (0, 1):
                r.stamp(li, float(gx[k]), float(gy[k]), dia / 2, code)
            okmask &= np.hypot(*np.meshgrid(np.arange(NX) * RES - float(gx[k]),
                                            np.arange(NY) * RES - float(gy[k]))) >= dia + 0.3
            anchors.append((float(gx[k]), float(gy[k])))
            added += 1
    print("  stitching vias added:", added)
    return added


def plan(board):
    nets = sorted({n for p in D.PARTS.values() for n in p[3].values()})
    # signal nets go shortest first (half-perimeter of their pads), so short
    # local connections are not boxed in by long ones
    pos = {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname():
                pos.setdefault(pad.GetNetname(), []).append(
                    (ToMM(pad.GetPosition().x), ToMM(pad.GetPosition().y)))

    def hpwl(n):
        xs = [p[0] for p in pos.get(n, [(0, 0)])]
        ys = [p[1] for p in pos.get(n, [(0, 0)])]
        return max(xs) - min(xs) + max(ys) - min(ys)

    first = [("VBUS", 0.3, {}), ("+12V", 0.25, {}), ("USB_DP", 0.25, {}), ("USB_DM", 0.25, {}),
             ("CC_A", 0.2, {}), ("CC_B", 0.2, {}), ("VHV", 0.4, {}),
             ("+5V", 0.4, {"via": (0.8, 0.4)}), ("XIAO_5V", 0.5, {"via": (0.8, 0.4)}),
             ("+3V3", 0.4, {"via": (0.8, 0.4)}), ("VSENSE", 0.25, {"bottom_cost": 1.0}),
             ("PD_PG", 0.25, {"bottom_cost": 1.0})]
    out = [x for x in first if x[0] in nets]
    done = {x[0] for x in out} | {"GND"}
    out += [(n, 0.25, {"bottom_cost": 1.15}) for n in sorted(nets, key=hpwl) if n not in done]
    out.append(("GND", 0.4, {"via": (0.8, 0.4), "bottom_cost": 1.0}))
    return out


def main():
    board = pcbnew.LoadBoard(paths.PCB)
    for t in list(board.GetTracks()):
        board.Remove(t)
    r = Router(board)
    manual(r)
    for net, w, kw in plan(board):
        print("routing", net)
        r.route_net(net, w, **kw)
    G.finish_silk(board)
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    for _ in range(3):
        if not stitch_islands(board, r):
            break
        filler.Fill(board.Zones())
    pcbnew.SaveBoard(paths.PCB, board)
    print("tracks:", len(board.GetTracks()), "failed:", r.failed)


if __name__ == "__main__":
    main()
