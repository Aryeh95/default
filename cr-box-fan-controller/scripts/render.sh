#!/bin/bash
# render.sh <out.png> [layers]  -- quick 2D preview of the board
cd "$(dirname "$0")/.."
L=${2:-F.Cu,B.Cu,F.SilkS,Edge.Cuts,F.Fab}
kicad-cli pcb export svg --layers "$L" --page-size-mode 2 --exclude-drawing-sheet -o build/preview.svg cr-box-fan-controller.kicad_pcb >/dev/null 2>&1
rsvg-convert -b white -z ${3:-16} build/preview.svg -o "$1" 2>/dev/null || convert -background white -density 400 build/preview.svg "$1"
