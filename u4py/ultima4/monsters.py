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
# Off-screen creatures are dropped in the original (they scroll out of the active window). Cull
# beyond this Chebyshev distance so slots recycle — otherwise stranded/left-behind monsters (e.g.
# sea creatures wedged against a coast) permanently fill the cap and encounters stop. Exact
# original window isn't pinned down; this is the smallest defensible margin past SPAWN_RING.
CULL_DIST = 12
# Also cull a creature that has made no progress toward the avatar for this many turns — it's
# wedged (a sea creature against a coast) or milling unreachably (a sea creature near an inland
# party). Without this, such monsters sit within CULL_DIST forever and still fill the cap.
STUCK_LIMIT = 8
# A creature this close (Chebyshev) is NEVER culled — the party can see it, so it must not blink
# out of existence on screen; it may only leave by an encounter or by walking off. This exceeds the
# 11x11 view radius (5) and SPAWN_RING (7), so nothing visible (or freshly spawned) is ever dropped.
SIGHT_RADIUS = 8

# Representative creature base tiles (4-frame land monsters / 2-frame sea creatures).
LAND_MONSTERS = (0x90, 0x94, 0x98, 0x9C, 0xA0, 0xA4, 0xA8, 0xC0, 0xC4, 0xC8)  # rat..rogue
SEA_MONSTERS = (0x84, 0x86, 0x88, 0x8A)                                       # nixie..seahorse


@dataclass
class Monster:
    x: int
    y: int
    tile: int
    stuck: int = 0             # turns without getting closer to the avatar (for the stuck-cull)


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
    _cull(game)
    _move(game)
    if len(game.monsters) < MAX_MONSTERS and game.rng.random() < SPAWN_CHANCE:
        _spawn(game)


def _cull(game) -> None:
    """Drop creatures that have fallen far from the avatar (off the active window), freeing cap
    slots — the original doesn't keep off-screen monsters. Without this, monsters that get stranded
    (sea creatures wedged against a coast the avatar sailed past) fill MAX_MONSTERS forever and
    overworld encounters stop for the rest of the game."""
    p = game.party
    kept = []
    for m in game.monsters:
        d = max(abs(_wrap(p.x - m.x)), abs(_wrap(p.y - m.y)))
        if d <= SIGHT_RADIUS:                       # visible -> never cull; it can only leave by
            kept.append(m)                          # an encounter or by walking off the active area
        elif d <= CULL_DIST and m.stuck < STUCK_LIMIT:
            kept.append(m)                          # off-screen but nearby and still making progress
        # else: off-screen AND (far OR wedged) -> drop, freeing its cap slot
    game.monsters[:] = kept


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
        dist0 = max(abs(dx), abs(dy))
        if dist0 <= 1:                      # adjacent -> the creature attacks
            encounter(game, m)
            continue
        sx, sy = _sign(dx), _sign(dy)
        # Try to close in; if the direct step is blocked (e.g. a sea creature facing a coast), fall
        # back to axis steps and then perpendicular slides so it follows the shore instead of wedging.
        cands = []
        if sx and sy:
            cands.append((sx, sy))          # diagonal toward the avatar
        if abs(dx) >= abs(dy):
            cands += [(sx, 0), (0, sy)]
        else:
            cands += [(0, sy), (sx, 0)]
        cands += [(0, 1), (0, -1), (1, 0), (-1, 0)]   # coast-follow: slide along terrain when stuck
        for cdx, cdy in cands:
            if cdx == 0 and cdy == 0:
                continue
            nx, ny = (m.x + cdx) & 0xFF, (m.y + cdy) & 0xFF
            if (nx, ny) != (p.x, p.y) \
                    and not any(o is not m and o.x == nx and o.y == ny for o in game.monsters) \
                    and _terrain_ok(game.world.tile_at(nx, ny), m.tile):
                m.x, m.y = nx, ny
                break
        dist1 = max(abs(_wrap(p.x - m.x)), abs(_wrap(p.y - m.y)))
        m.stuck = 0 if dist1 < dist0 else m.stuck + 1    # progress resets the stuck-cull counter


def encounter(game, m: Monster) -> None:
    """A monster reached the avatar -> begin combat. C: C_7DFE."""
    if m in game.monsters:
        game.monsters.remove(m)
    try:
        combat.start_encounter(game, m.tile)
    except NotImplementedError:
        game.message(f"{tile_name(m.tile).replace('_', ' ')} attacks!")
