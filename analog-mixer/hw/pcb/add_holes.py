"""Put the M2 mounting holes (D57, build_pcb.MOUNT_HOLES) on the routed boards without touching
the routing: only standalone GND stitching vias that collide with a hole are removed, then the
zones are refilled.

Run with KiCad's Python:  hw/pcb/add_holes.py analog|digital   (in place on <b>_routed.kicad_pcb)
"""
import argparse
import math

import pcbnew

import build_pcb as bp
import fix_pcb as fx

HOLE_KEEP = 2.2 + 0.3 + 0.25           # hole pad radius + via radius + hole-to-hole margin, mm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board", choices=("analog", "digital"))
    a = ap.parse_args()
    path = bp.HW / a.board / f"{a.board}_routed.kicad_pcb"
    board = pcbnew.LoadBoard(str(path))
    bp.add_mount_holes(board, a.board)
    gnd = next(board.FindNet(n) for n in ("/GND", "GND") if board.FindNet(n)).GetNetCode()
    ends = {(t.GetStart().x, t.GetStart().y) for t in board.GetTracks() if t.GetClass() != "PCB_VIA"} | \
           {(t.GetEnd().x, t.GetEnd().y) for t in board.GetTracks() if t.GetClass() != "PCB_VIA"}
    dropped = []
    for ref, (x, y) in bp.MOUNT_HOLES[a.board].items():
        c = bp.pt(x, y)
        for t in list(board.GetTracks()):
            if t.GetClass() != "PCB_VIA" or t.GetNetCode() != gnd:
                continue
            p = t.GetPosition()
            if (p.x, p.y) in ends:
                continue                      # a routed via, not stitching: leave it to DRC
            if math.hypot(pcbnew.ToMM(p.x - c.x), pcbnew.ToMM(p.y - c.y)) < HOLE_KEEP:
                dropped.append((ref, round(pcbnew.ToMM(p.x) - bp.OX, 2), round(pcbnew.ToMM(p.y) - bp.OY, 2)))
                board.Delete(t)
    fx.fill(board)
    board.Save(str(path))
    print(f"{a.board}: holes {list(bp.MOUNT_HOLES[a.board])}, stitching vias removed {dropped}")


if __name__ == "__main__":
    main()
