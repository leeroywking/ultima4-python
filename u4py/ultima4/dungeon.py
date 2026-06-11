"""Dungeons (U4_DNG.C) — v1.

A dungeon is 8 stacked 8x8 levels in a `.DNG` file (first 512 bytes; the rest is room data).
Each cell is nibble-encoded: high nibble = kind. 0xF wall, 0x0 corridor, 0x1 ladder-up,
0x2 ladder-down, 0x3 both, 0x4 chest, 0x7 fountain, 0x8 field, 0x9 monster room, 0xA altar,
0xD door. You explore first-person: Advance/Retreat in your facing, Turn left/right, Klimb /
Descend ladders. (U4 renders a 3D view; v1 draws a top-down window centred on you — the 3D
raycast is a renderer refinement. Cites U4_DNG.C.)
"""
from __future__ import annotations

from .constants import DIR_DX, DIR_DY, DIR_N, MOD_DUNGEON

SIZE = 8
LEVELS = 8

# dungeon nibble-kind -> a display sprite id (for the top-down view)
_SPRITE = {0xF0: 0x08, 0x00: 0x3E, 0x10: 0x1B, 0x20: 0x1C, 0x30: 0x1B, 0x40: 0x3C,
           0x70: 0x16, 0x80: 0x44, 0x90: 0x3E, 0xA0: 0x3D, 0xC0: 0x3E, 0xD0: 0x3B}


def _sprite(code: int) -> int:
    return _SPRITE.get(code & 0xF0, 0x3E)


class DungeonState:
    """Exploration of one dungeon in first-person. C: U4_DNG.C DNG_main."""

    def __init__(self, game, dungeon_id: int, data: bytes):
        self.game = game
        self.dungeon_id = dungeon_id
        self.levels = [bytearray(data[L * 64:(L + 1) * 64]) for L in range(LEVELS)]
        self.x = self.y = self.z = 0
        self.facing = DIR_N
        for y in range(SIZE):                          # enter at the surface ladder of level 0
            for x in range(SIZE):
                if self.tile(x, y, 0) & 0xF0 == 0x10:
                    self.x, self.y = x, y
                    return

    def tile(self, x: int, y: int, z: int = None) -> int:
        z = self.z if z is None else z
        return self.levels[z][(y & 7) * SIZE + (x & 7)]

    @staticmethod
    def is_wall(t: int) -> bool:
        return (t & 0xF0) == 0xF0

    # --- movement -----------------------------------------------------------
    def advance(self) -> None:
        self._step(1)

    def retreat(self) -> None:
        self._step(-1)

    def _step(self, d: int) -> None:
        nx = (self.x + DIR_DX[self.facing] * d) & 7
        ny = (self.y + DIR_DY[self.facing] * d) & 7
        if self.is_wall(self.tile(nx, ny)):
            self.game.message("Blocked!")
            return
        self.x, self.y = nx, ny
        self._on_enter()

    def turn_left(self) -> None:
        self.facing = (self.facing - 1) % 4

    def turn_right(self) -> None:
        self.facing = (self.facing + 1) % 4

    def klimb(self) -> None:
        if self.tile(self.x, self.y) & 0xF0 in (0x10, 0x30):
            if self.z == 0:
                self.game._exit_dungeon()
            else:
                self.z -= 1
                self.game.message("Klimb!")
        else:
            self.game.message("Klimb what?")

    def descend(self) -> None:
        if self.tile(self.x, self.y) & 0xF0 in (0x20, 0x30):
            if self.z >= LEVELS - 1:
                if self.dungeon_id == 0x18:              # the bottom of the Abyss -> the Codex
                    from . import endgame
                    endgame.enter_codex(self.game)
                else:
                    self.game.message("Thou canst descend no further!")
            else:
                self.z += 1
                self.game.message("Descend!")
        else:
            self.game.message("Descend what?")

    # --- tile effects on entry (C: U4_DNG.C tile dispatch) ------------------
    def _on_enter(self) -> None:
        kind = self.tile(self.x, self.y) & 0xF0
        p = self.game.party
        if kind == 0x80:                               # an energy/poison/etc field
            for c in p.members:
                if c.alive:
                    c.hp = max(0, c.hp - 5)
            self.game.message("A field!  Thou art harmed!")
        elif kind == 0x40:                             # treasure chest
            p.gold = min(9999, p.gold + self.game.rng.randint(50, 150))
            self.levels[self.z][(self.y & 7) * SIZE + (self.x & 7)] = 0x00   # emptied
            self.game.message("A chest!  Thou dost find gold!")
        elif kind == 0x70:                             # a fountain
            for c in p.members:
                if c.alive:
                    c.hp = c.hp_max
            self.game.message("A fountain!  Thou art refreshed!")
        elif kind == 0x90:                             # a monster room
            from . import combat
            self.game.message("A monster room!")
            combat.start_encounter(self.game, 0x90 + self.game.rng.randint(0, 6) * 4)

    # --- render (top-down window centred on the party) ----------------------
    def viewport(self, radius: int = 5):
        return [[_sprite(self.tile(self.x + dx, self.y + dy))
                 for dx in range(-radius, radius + 1)]
                for dy in range(-radius, radius + 1)]


def load_dungeon_bytes(dungeon_id: int) -> bytes:
    """The full .DNG image (512 level bytes + room block) from its editable ascii file.

    data/maps/<base>.dng.txt is the single source of truth; the binary .DNG is an import
    source only (tools/convert_maps.py). C: U4_DNG.C dungeon load.
    """
    from pathlib import Path
    from . import asciimap as am
    from .savefile import DATA_DIR
    from .data_tables import DUNGEON_FILES
    base = Path(DUNGEON_FILES[(dungeon_id - 0x11) % len(DUNGEON_FILES)]).stem.lower()
    return am.parse_dungeon((DATA_DIR / "maps" / f"{base}.dng.txt").read_text(encoding="utf-8"))


def enter_dungeon(game, dungeon_id: int) -> DungeonState:
    """Enter a dungeon from its overworld entrance (tile 0x09). C: U4_DNG.C entry."""
    data = load_dungeon_bytes(dungeon_id)
    game._dungeon_return = (game.party.x, game.party.y)
    game.dungeon = DungeonState(game, dungeon_id, data)
    game.party.loc = dungeon_id
    game.mode = MOD_DUNGEON
    game.message("Enter the dungeon!")
    return game.dungeon
