"""Create a fresh PARTY.SAV — a simplified port of character creation (TITLE_1.C C_2E04).

The authentic intro (the gypsy reading the eight virtue dilemmas, in TITLE.EXE) isn't
ported yet. This does the part that matters for play: it takes the PARTY.NEW template of
the eight class companions, makes your chosen class party member 0 (the swap in C_2E04),
names you, and drops you at that class's home-town moongate position (D_30DC/D_30E4).

    python -m tools.newgame --class fighter --name Avatar
    python -m tools.newgame -c 0            # 0=Mage 1=Bard 2=Fighter 3=Druid
                                            # 4=Tinker 5=Paladin 6=Ranger 7=Shepherd

Stats/HP/equipment come from the canonical companion template; authentic stat-rolling
(the +increments per virtue, see data_tables.VIRTUE_*_INC) is a later character-creation port.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ultima4.data_tables import (CLASS_NAMES, CLASS_COMPANION, CLASS_HOME,
                                 START_X, START_Y)
from ultima4.state import Party
from ultima4.savefile import load_bytes, DATA_DIR

AVATAR_ON_FOOT = 0x1F  # TIL_1F


def resolve_class(value: str) -> int:
    if value.isdigit():
        v = int(value)
    else:
        names = [c.lower() for c in CLASS_NAMES]
        if value.lower() not in names:
            raise SystemExit(f"unknown class {value!r}; pick one of {CLASS_NAMES} or 0-7")
        v = names.index(value.lower())
    if not 0 <= v <= 7:
        raise SystemExit("class index must be 0-7")
    return v


def new_party(virtue: int, name: str) -> Party:
    party = Party.from_bytes(load_bytes("PARTY.NEW"))      # template of 8 companions
    party.chara[0], party.chara[virtue] = party.chara[virtue], party.chara[0]  # C: the swap
    party.chara[0].name = name
    party.member_count = 1                                  # C: Party.f_1d8 = 1
    party.x, party.y = START_X[virtue], START_Y[virtue]     # C: D_30DC/D_30E4
    party.tile = AVATAR_ON_FOOT
    party.loc = 0
    return party


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-c", "--class", dest="cls", default="fighter",
                    help="class name or virtue index 0-7")
    ap.add_argument("-n", "--name", default="Avatar")
    args = ap.parse_args()

    v = resolve_class(args.cls)
    party = new_party(v, args.name)
    (DATA_DIR / "PARTY.SAV").write_bytes(party.to_bytes())
    print(f"New game: {args.name} the {CLASS_NAMES[v]} (companion {CLASS_COMPANION[v]}), "
          f"starting near {CLASS_HOME[v]} at ({party.x},{party.y}).")
    print(f"Wrote {DATA_DIR / 'PARTY.SAV'}.  Boot with:  .venv/bin/python play.py ega")


if __name__ == "__main__":
    main()
