"""Remove the tracks of one net near a point (e.g. a clearance violation from the DRC report) and
print the loose ends, so common/patch_route.py can route that piece again (narrower, --width).

Run with KiCad's Python:
  common/rip_near.py <board.kicad_pcb> <net> <x> <y> [--radius MM]
(x, y): board mm (page - 20), as patch_route.py. Saves the board in place.
"""
import argparse

import pcbnew

OX = OY = 20.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("net")
    ap.add_argument("x", type=float)
    ap.add_argument("y", type=float)
    ap.add_argument("--radius", type=float, default=1.0)
    a = ap.parse_args()
    board = pcbnew.LoadBoard(a.board)
    net = a.net if a.net.startswith("/") else "/" + a.net
    code = board.FindNet(net).GetNetCode()
    c = pcbnew.VECTOR2I(pcbnew.FromMM(a.x + OX), pcbnew.FromMM(a.y + OY))
    r = pcbnew.FromMM(a.radius)
    gone = []
    for t in list(board.GetTracks()):
        if t.GetNetCode() != code or t.GetClass() != "PCB_TRACK" or t.IsLocked():
            continue
        if any((p.x - c.x) ** 2 + (p.y - c.y) ** 2 <= r * r for p in (t.GetStart(), t.GetEnd())):
            gone.append((t.GetStart(), t.GetEnd()))
            board.Remove(t)
    ends = {}
    for s, e in gone:
        for p in (s, e):
            ends[(p.x, p.y)] = ends.get((p.x, p.y), 0) + 1
    pcbnew.SaveBoard(a.board, board)
    print(f"{net}: removed {len(gone)} segments; ends:",
          [(round(pcbnew.ToMM(x) - OX, 3), round(pcbnew.ToMM(y) - OY, 3)) for (x, y), n in ends.items() if n == 1])


if __name__ == "__main__":
    main()
