"""Town/castle/village maps (.ULT files), ported from struct t_500 + tNPC (U4.H).

A .ULT is 1280 bytes = a 32x32 tile map (1024) followed by a 256-byte NPC block
(struct tNPC). The NPC block is 8 parallel arrays of 32 entries each:
    gtile[32] @0x00, x[32] @0x20, y[32] @0x40, tile[32] @0x60,
    old_x[32] @0x80, old_y[32] @0xA0, var[32] @0xC0, tlkidx[32] @0xE0
An NPC slot is active when its `tile` byte is non-zero. (C: U4_EXPLO.C C_3E30 loads
D_0824[loc-1] into D_8742, which is `struct t_500 { map; tNPC npc; }`.)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

MAP_BYTES = 32 * 32        # 1024
NPC_COUNT = 32
TNPC_BYTES = 0x100         # 256
ULT_BYTES = MAP_BYTES + TNPC_BYTES  # 1280


@dataclass
class NPC:
    slot: int
    x: int
    y: int
    tile: int          # current display tile (0 => inactive)
    gtile: int         # "ground"/home tile
    tlkidx: int        # index into the .TLK dialogue table
    var: int           # movement disposition: 0 still, +ve wander, -ve follow (0xff hostile)
    old_x: int = 0     # previous position (C: _old_x), used by the anti-backtrack rule
    old_y: int = 0
    dialogue: object = None   # editor-injected Dialogue (overrides the .TLK lookup) or None


class Location:
    def __init__(self, data: bytes, loc_id: int, name: str = ""):
        if len(data) != ULT_BYTES:
            raise ValueError(f".ULT must be {ULT_BYTES} bytes, got {len(data)}")
        self.loc_id = loc_id
        self.name = name
        self.tiles = bytearray(data[:MAP_BYTES])       # mutable: doors open, etc.
        npc = data[MAP_BYTES:]
        self.npcs: List[NPC] = []
        for i in range(NPC_COUNT):
            tile = npc[0x60 + i]
            if tile == 0:
                continue
            self.npcs.append(NPC(
                slot=i, x=npc[0x20 + i], y=npc[0x40 + i], tile=tile,
                gtile=npc[0x00 + i], tlkidx=npc[0xE0 + i], var=npc[0xC0 + i],
                old_x=npc[0x80 + i], old_y=npc[0xA0 + i],
            ))

    @classmethod
    def load(cls, filename: str, loc_id: int, name: str = "") -> "Location":
        """Load a town/castle floor from its editable ascii-tilemap (single source of truth).

        `filename` is still the original .ULT name (e.g. "BRITAIN.ULT") so call sites and the
        place tables don't change; we read data/maps/<base>.txt and fold the grid + NPC table
        back into the 1280-byte .ULT image. The binary .ULT is an import source only
        (tools/convert_maps.py) — never read here. C: U4_EXPLO.C C_3E30 struct t_500.
        """
        from pathlib import Path
        from . import asciimap as am
        from .savefile import DATA_DIR
        path = DATA_DIR / "maps" / f"{Path(filename).stem.lower()}.txt"
        tiles, npc = am.parse_town(path.read_text(encoding="utf-8"))
        return cls(tiles + npc, loc_id, name)

    def tile_at(self, x: int, y: int) -> Optional[int]:
        """Tile id at local (x, y); None if off the 32x32 map (== leaving)."""
        if 0 <= x < 32 and 0 <= y < 32:
            return self.tiles[y * 32 + x]
        return None

    def npc_at(self, x: int, y: int) -> Optional[NPC]:
        for n in self.npcs:
            if n.x == x and n.y == y:
                return n
        return None
