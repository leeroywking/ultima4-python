"""Dump a PARTY.SAV to verify byte-accurate fidelity against the original.

Usage:
    python -m tools.inspect_save [path/to/PARTY.SAV]

Also asserts a perfect from_bytes -> to_bytes round-trip, which is our Phase-0
fidelity check: if the bytes come back identical, the struct port matches the C layout.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ultima4.constants import VIRTUES, MODE_NAMES  # noqa: E402
from ultima4.state import Party  # noqa: E402


def main(path: str) -> None:
    raw = Path(path).read_bytes()
    party = Party.from_bytes(raw)

    # Fidelity check: round-trip must be byte-identical.
    rt = party.to_bytes()
    if rt == raw:
        print(f"[ok] round-trip byte-identical ({len(raw)} bytes)\n")
    else:
        diffs = [i for i, (a, b) in enumerate(zip(raw, rt)) if a != b]
        print(f"[FAIL] round-trip differs at {len(diffs)} offsets: "
              f"{[hex(d) for d in diffs[:16]]}\n")

    print(f"Location id : {party.loc}  (out_xy={party.out_x},{party.out_y}  xy={party.x},{party.y})")
    print(f"Moves       : {party.moves}")
    print(f"Gold        : {party.gold}    Food: {party.food}")
    print(f"Moons       : trammel={party.trammel} felucca={party.felucca}")
    print(f"Items mask  : {party.items:#06x}  stones={party.stones:#04x} runes={party.runes:#04x}")
    print(f"\nVirtues:")
    for name, k in zip(VIRTUES, party.karma):
        print(f"  {name:<13} {k}")
    print(f"\nParty ({party.member_count} members):")
    for c in party.members:
        print(f"  {c.name:<16} {c.char_class}{c.sex} HP {c.hp}/{c.hp_max} "
              f"MP {c.mp}  STR {c.str_} DEX {c.dex} INT {c.intel}  "
              f"XP {c.xp}  [{c.status}]")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/PARTY.SAV")
