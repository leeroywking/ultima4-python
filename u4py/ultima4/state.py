"""Game state: byte-accurate port of `tChara` / `tParty` from U4.H.

This is the single source of truth for the whole game. The savegame `PARTY.SAV` is
literally a memory dump of `struct tParty` (502 bytes, packed, little-endian), so
`Party.from_bytes(open("PARTY.SAV","rb").read())` round-trips exactly.

Both runtime agents build on this:
  * the editor writes fields here ("max my stats" -> set str/dex/int = 99),
  * the tutor reads them ("what should I do next" -> inspect virtues/items).

C reference: U4.H  struct tChara /*size:0x27*/, struct tParty /*size:0x1f6*/.
Field offsets in comments match the C `/*+xx*/` annotations.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import List

from .constants import VIRTUES

# --- struct tChara (0x27 = 39 bytes) ------------------------------------------
# /*+00*/ U16 _HP[2]; /*+04*/ U16 _XP; /*+06*/ _str; /*+08*/ _dex; /*+0a*/ _int;
# /*+0c*/ _MP; /*+0e*/ char __0e[2]; /*+10*/ _weapon; /*+12*/ _armor;
# /*+14*/ char _name[16]; /*+24*/ sex; /*+25*/ _class; /*+26*/ _stat;
_CHARA_FMT = "<HHHHHHH2sHH16sccc"
CHARA_SIZE = struct.calcsize(_CHARA_FMT)
assert CHARA_SIZE == 0x27, CHARA_SIZE


def _cstr(raw: bytes) -> str:
    """Decode a fixed C char[] up to its first NUL."""
    return raw.split(b"\x00", 1)[0].decode("latin-1")


@dataclass
class Character:
    hp: int = 0          # _HP[0]: current hit points
    hp_max: int = 0      # _HP[1]: maximum hit points
    xp: int = 0          # _XP
    str_: int = 0        # _str
    dex: int = 0         # _dex
    intel: int = 0       # _int
    mp: int = 0          # _MP (magic points)
    weapon: int = 0      # _weapon (readied weapon id)
    armor: int = 0       # _armor (worn armor id)
    name: str = ""       # _name[16] (decoded up to the NUL)
    sex: str = "M"       # p_24 ('M'/'F')
    char_class: str = "A"  # _class (e.g. 'A' avatar / class letter)
    status: str = "G"    # _stat ('G' good, 'P' poisoned, 'S' sleeping, 'D' dead...)
    _pad0e: bytes = b"\x00\x00"  # __0e[2]: preserved for exact round-trip
    # Exact 16 name bytes as loaded. Lets us round-trip byte-perfectly even when the
    # original left uninitialised garbage after the NUL (unused party slots). Set to
    # None for a fresh Character; editing `.name` and re-saving re-encodes cleanly.
    name_raw: bytes | None = None

    @classmethod
    def from_bytes(cls, raw: bytes) -> "Character":
        (hp, hp_max, xp, str_, dex, intel, mp, pad0e, weapon, armor,
         name, sex, char_class, status) = struct.unpack(_CHARA_FMT, raw)
        return cls(
            hp=hp, hp_max=hp_max, xp=xp, str_=str_, dex=dex, intel=intel, mp=mp,
            weapon=weapon, armor=armor, name=_cstr(name),
            sex=sex.decode("latin-1"), char_class=char_class.decode("latin-1"),
            status=status.decode("latin-1"), _pad0e=pad0e, name_raw=name,
        )

    def to_bytes(self) -> bytes:
        # Preserve the exact loaded name bytes if the name hasn't been edited; otherwise
        # re-encode (NUL-padded). This keeps unused-slot garbage byte-identical on save.
        if self.name_raw is not None and _cstr(self.name_raw) == self.name:
            name_bytes = self.name_raw
        else:
            name_bytes = self.name.encode("latin-1")[:16].ljust(16, b"\x00")
        return struct.pack(
            _CHARA_FMT,
            self.hp, self.hp_max, self.xp, self.str_, self.dex, self.intel,
            self.mp, self._pad0e, self.weapon, self.armor,
            name_bytes,
            self.sex.encode("latin-1")[:1] or b"\x00",
            self.char_class.encode("latin-1")[:1] or b"\x00",
            self.status.encode("latin-1")[:1] or b"\x00",
        )

    @property
    def alive(self) -> bool:        # C: isCharaAlive -> _stat != 'D'
        return self.status != "D"

    @property
    def conscious(self) -> bool:    # C: isCharaConscious -> alive and not sleeping
        return self.status not in ("D", "S")


# --- struct tParty (0x1f6 = 502 bytes) ----------------------------------------
# Layout: [header 8] [chara[8] = 312] [tail 182]. See U4.H for every field.
_HEADER_FMT = "<II"               # f_000 (counter), _moves
_HEADER_SIZE = struct.calcsize(_HEADER_FMT)  # 8
_PARTY_SIZE = 0x1f6               # 502

# Tail starts at /*+140*/ (after header + 8 charas).
_TAIL_FMT = (
    "<"
    "i"     # _food (long)
    "H"     # _gold
    "8H"    # _hones.._humil  (the 8 virtue karmas, order == constants.VIRTUES)
    "H"     # _torches
    "H"     # _gems
    "H"     # _keys
    "H"     # _sextants
    "8H"    # _armors[8]
    "16H"   # _weapons[16]
    "8H"    # _reagents[8]
    "26H"   # _mixtures[26]
    "H"     # mItems (special-items bitmask; see constants.ST_*)
    "B"     # _x
    "B"     # _y
    "B"     # mStones
    "B"     # mRunes
    "H"     # f_1d8  (number of characters in party)
    "H"     # _tile
    "H"     # f_1dc  (isFlying / dungeon light)
    "H"     # _trammel (moon phase)
    "H"     # _felucca (moon phase)
    "H"     # _ship (hull integrity)
    "H"     # f_1e4  (did meet Lord British)
    "H"     # f_1e6  (last hole-up & camp)
    "H"     # f_1e8  (last found)
    "H"     # f_1ea  (last meditation / Hawkwind)
    "H"     # f_1ec  (last karma-conversation)
    "B"     # out_x
    "B"     # out_y
    "H"     # _dir (dungeon facing)
    "h"     # _z (dungeon level, signed)
    "H"     # _loc (current location id)
)
_TAIL_SIZE = struct.calcsize(_TAIL_FMT)
assert _HEADER_SIZE + 8 * CHARA_SIZE + _TAIL_SIZE == _PARTY_SIZE


@dataclass
class Party:
    # header
    counter: int = 0                 # f_000
    moves: int = 0                   # _moves
    chara: List[Character] = field(default_factory=lambda: [Character() for _ in range(8)])
    # tail
    food: int = 0                    # _food (note: original stores food*100)
    gold: int = 0
    karma: List[int] = field(default_factory=lambda: [0] * 8)  # by VIRTUES order
    torches: int = 0
    gems: int = 0
    keys: int = 0
    sextants: int = 0
    armors: List[int] = field(default_factory=lambda: [0] * 8)
    weapons: List[int] = field(default_factory=lambda: [0] * 16)
    reagents: List[int] = field(default_factory=lambda: [0] * 8)
    mixtures: List[int] = field(default_factory=lambda: [0] * 26)
    items: int = 0                   # mItems bitmask
    x: int = 0                       # world/local X
    y: int = 0                       # world/local Y
    stones: int = 0                  # mStones bitmask
    runes: int = 0                   # mRunes bitmask
    member_count: int = 0            # f_1d8
    tile: int = 0                    # _tile (avatar's current map tile)
    flying: int = 0                  # f_1dc
    trammel: int = 0                 # moon phase (selects moongate X)
    felucca: int = 0                 # moon phase (selects moongate Y)
    ship: int = 0                    # _ship hull integrity
    met_lb: int = 0                  # f_1e4
    last_holeup: int = 0             # f_1e6
    last_found: int = 0              # f_1e8
    last_meditation: int = 0         # f_1ea
    last_karma_convo: int = 0        # f_1ec
    out_x: int = 0                   # overworld X (saved while inside a location)
    out_y: int = 0                   # overworld Y
    dir: int = 0                     # dungeon facing
    z: int = 0                       # dungeon level
    loc: int = 0                     # _loc current location id

    @classmethod
    def from_bytes(cls, raw: bytes) -> "Party":
        if len(raw) != _PARTY_SIZE:
            raise ValueError(f"PARTY.SAV must be {_PARTY_SIZE} bytes, got {len(raw)}")
        counter, moves = struct.unpack_from(_HEADER_FMT, raw, 0)
        charas = [
            Character.from_bytes(raw[_HEADER_SIZE + i * CHARA_SIZE:
                                     _HEADER_SIZE + (i + 1) * CHARA_SIZE])
            for i in range(8)
        ]
        t = struct.unpack_from(_TAIL_FMT, raw, _HEADER_SIZE + 8 * CHARA_SIZE)
        i = iter(t)
        nx = lambda: next(i)
        take = lambda n: [next(i) for _ in range(n)]
        return cls(
            counter=counter, moves=moves, chara=charas,
            food=nx(), gold=nx(), karma=take(8),
            torches=nx(), gems=nx(), keys=nx(), sextants=nx(),
            armors=take(8), weapons=take(16), reagents=take(8), mixtures=take(26),
            items=nx(), x=nx(), y=nx(), stones=nx(), runes=nx(),
            member_count=nx(), tile=nx(), flying=nx(),
            trammel=nx(), felucca=nx(), ship=nx(),
            met_lb=nx(), last_holeup=nx(), last_found=nx(),
            last_meditation=nx(), last_karma_convo=nx(),
            out_x=nx(), out_y=nx(), dir=nx(), z=nx(), loc=nx(),
        )

    def to_bytes(self) -> bytes:
        out = bytearray()
        out += struct.pack(_HEADER_FMT, self.counter, self.moves)
        for c in self.chara:
            out += c.to_bytes()
        out += struct.pack(
            _TAIL_FMT,
            self.food, self.gold, *self.karma,
            self.torches, self.gems, self.keys, self.sextants,
            *self.armors, *self.weapons, *self.reagents, *self.mixtures,
            self.items, self.x, self.y, self.stones, self.runes,
            self.member_count, self.tile, self.flying,
            self.trammel, self.felucca, self.ship,
            self.met_lb, self.last_holeup, self.last_found,
            self.last_meditation, self.last_karma_convo,
            self.out_x, self.out_y, self.dir, self.z, self.loc,
        )
        assert len(out) == _PARTY_SIZE
        return bytes(out)

    @property
    def members(self) -> List[Character]:
        """The active party members (the first `member_count` slots)."""
        return self.chara[:self.member_count]

    def virtue_karma(self) -> dict:
        """{virtue_name: karma 0..99} — convenience for the tutor."""
        return dict(zip(VIRTUES, self.karma))
