"""Output locations: the KiCad project and its outputs live in ../pcb."""
import os

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pcb")
NAME = "pd-fan-ctrl"
PCB = os.path.join(ROOT, NAME + ".kicad_pcb")
PRO = os.path.join(ROOT, NAME + ".kicad_pro")
SCH = os.path.join(ROOT, NAME + ".kicad_sch")
BUILD = os.path.join(ROOT, "build")
os.makedirs(BUILD, exist_ok=True)
