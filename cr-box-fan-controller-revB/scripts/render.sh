#!/bin/bash
# render.sh <variant> <out.png> [layers] [zoom] -- quick 2D preview of the board
cd "$(dirname "$0")/../$1"
L=${3:-F.Cu,B.Cu,F.SilkS,Edge.Cuts,F.Fab}
kicad-cli pcb export svg --layers "$L" --page-size-mode 2 --exclude-drawing-sheet -o build/preview.svg cr-box-fan-controller-revB-$1.kicad_pcb >/dev/null 2>&1
rsvg-convert -b white -z ${4:-9} build/preview.svg -o "$2"
