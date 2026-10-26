"""Put the source-location block (build_pcb.ATTRIB, CERN-OHL-S-2.0 s. 4, D9) on a routed board
without touching anything else.

Run with KiCad's Python:  hw/pcb/add_silk.py analog|digital   (in place on <b>_routed.kicad_pcb)
"""
import argparse

import pcbnew

import build_pcb as bp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board", choices=("analog", "digital"))
    a = ap.parse_args()
    path = bp.HW / a.board / f"{a.board}_routed.kicad_pcb"
    board = pcbnew.LoadBoard(str(path))
    bp.add_attribution(board, a.board)
    board.Save(str(path))
    side, x, y = bp.ATTRIB[a.board]
    print(f"{a.board}: source location on {side}.SilkS at ({x}, {y})")


if __name__ == "__main__":
    main()
