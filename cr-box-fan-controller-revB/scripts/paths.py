"""Output locations for the Rev B variant selected by the VARIANT environment variable."""
import os

import design as D

VARIANT = D.VARIANT
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", VARIANT)
NAME = "cr-box-fan-controller-revB-" + VARIANT
PCB = os.path.join(ROOT, NAME + ".kicad_pcb")
PRO = os.path.join(ROOT, NAME + ".kicad_pro")
SCH = os.path.join(ROOT, NAME + ".kicad_sch")
BUILD = os.path.join(ROOT, "build")
os.makedirs(BUILD, exist_ok=True)
