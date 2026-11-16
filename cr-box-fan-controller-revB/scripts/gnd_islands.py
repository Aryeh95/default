#!/usr/bin/python3.12
"""Report ground pour islands that are not joined to the rest of the ground net."""
import os, sys
import pcbnew
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

b = pcbnew.LoadBoard(paths.PCB)
links = [v.GetPosition() for v in b.GetTracks() if v.GetClass() == "PCB_VIA" and v.GetNetname() == "GND"]
links += [p.GetPosition() for fp in b.GetFootprints() for p in fp.Pads()
          if p.GetNetname() == "GND" and p.GetDrillSize().x > 0]
polys = []
for z in b.Zones():
    if z.GetNetname() != "GND" or z.GetIsRuleArea():
        continue
    layer = z.GetLayer()
    ps = z.GetFilledPolysList(layer)
    for i in range(ps.OutlineCount()):
        polys.append((pcbnew.LayerName(layer) if hasattr(pcbnew, "LayerName") else layer, ps, i))
parent = list(range(len(polys)))
def find(a):
    while parent[a] != a:
        parent[a] = parent[parent[a]]; a = parent[a]
    return a
for pt in links:
    hit = [k for k, (l, ps, i) in enumerate(polys) if ps.Outline(i).PointInside(pt)]
    for k in hit[1:]:
        parent[find(k)] = find(hit[0])
groups = {}
for k in range(len(polys)):
    groups.setdefault(find(k), []).append(k)
big = max(groups.values(), key=lambda g: sum(polys[k][1].Outline(polys[k][2]).Area() for k in g))
for g in groups.values():
    if g is big:
        continue
    for k in g:
        l, ps, i = polys[k]
        bb = ps.Outline(i).BBox()
        print("isolated", l, [round(pcbnew.ToMM(v), 1) for v in (bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom())])
