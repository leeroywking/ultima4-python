"""Overworld monsters & encounters (U4_AI.C / U4_NPC.C C_5712 / U4_Z.C).

Monsters roam the overworld: they spawn near the edge of view on terrain that suits them
(sea creatures on water, land monsters on land), close on the avatar each turn, and start a
fight when adjacent (combat.py). They are tracked in `game.monsters`, a parallel to the town
tNPC block. Exact spawn tables/rates from the original are approximated; movement mirrors the
town follow-AI (step toward the avatar over terrain the creature can cross).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import combat
from .tiles import is_walkable, tile_name, SAILABLE

MAX_MONSTERS = 4            # active overworld creatures cap (C: tNPC block is small)
SPAWN_CHANCE = 0.12        # per outdoor turn
SPAWN_RING = 7             # spawn just outside the ~11x11 view

# Representative creature base tiles (4-frame land monsters / 2-frame sea creatures).
LAND_MONSTERS = (0x90, 0x94, 0x98, 0x9C, 0xA0, 0xA4, 0xA8, 0xC0, 0xC4, 0xC8)  # rat..rogue
SEA_MONSTERS = (0x84, 0x86, 0x88, 0x8A)                                       # nixie..seahorse


@dataclass
class Monster:
    x: int
    y: int
    tile: int


def _sign(n: int) -> int:
    return (n > 0) - (n < 0)


def _wrap(d: int) -> int:
    """Shortest signed delta on the 256-wide torus."""
    d &= 0xFF
    return d - 256 if d > 128 else d


def _terrain_ok(tile_id: int, monster_tile: int) -> bool:
    if monster_tile < 0x90:                 # a sea creature
        return tile_id in SAILABLE
    return is_walkable(tile_id)             # a land monster


def spawn_and_move(game) -> None:
    """C: U4_NPC.C C_5712 (move) + U4_AI.C (spawn) — once per overworld turn."""
    _move(game)
    if len(game.monsters) < MAX_MONSTERS and game.rng.random() < SPAWN_CHANCE:
        _spawn(game)


def _spawn(game) -> None:
    p = game.party
    for _ in range(6):                      # a few placement attempts
        ex = (p.x + game.rng.randint(-SPAWN_RING, SPAWN_RING)) & 0xFF
        ey = (p.y + game.rng.randint(-SPAWN_RING, SPAWN_RING)) & 0xFF
        if (ex, ey) == (p.x, p.y) or any(m.x == ex and m.y == ey for m in game.monsters):
            continue
        t = game.world.tile_at(ex, ey)
        if t in SAILABLE:
            game.monsters.append(Monster(ex, ey, game.rng.choice(SEA_MONSTERS)))
            return
        if is_walkable(t):
            game.monsters.append(Monster(ex, ey, game.rng.choice(LAND_MONSTERS)))
            return


def _move(game) -> None:
    p = game.party
    for m in list(game.monsters):
        dx, dy = _wrap(p.x - m.x), _wrap(p.y - m.y)
        if max(abs(dx), abs(dy)) <= 1:      # adjacent -> the creature attacks
            encounter(game, m)
            continue
        nx, ny = (m.x + _sign(dx)) & 0xFF, (m.y + _sign(dy)) & 0xFF
        if (nx, ny) != (p.x, p.y) and not any(o is not m and o.x == nx and o.y == ny
                                              for o in game.monsters) \
                and _terrain_ok(game.world.tile_at(nx, ny), m.tile):
            m.x, m.y = nx, ny


def encounter(game, m: Monster) -> None:
    """A monster reached the avatar -> begin combat. C: C_7DFE."""
    if m in game.monsters:
        game.monsters.remove(m)
    try:
        combat.start_encounter(game, m.tile)
    except NotImplementedError:
        game.message(f"{tile_name(m.tile).replace('_', ' ')} attacks!")
