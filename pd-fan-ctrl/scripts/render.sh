#!/bin/bash
# render.sh <out.png> [layers] [zoom] -- quick 2D preview of the board
cd "$(dirname "$0")/../pcb"
L=${2:-F.Cu,B.Cu,F.SilkS,Edge.Cuts,F.Fab}
kicad-cli pcb export svg --layers "$L" --page-size-mode 2 --exclude-drawing-sheet -o build/preview.svg pd-fan-ctrl.kicad_pcb >/dev/null 2>&1
rsvg-convert -b white -z ${3:-9} build/preview.svg -o "$1"
