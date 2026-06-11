"""Moongates (U4_ANIM.C C_3A80 + U4_MAP.C C_2A91; tables in data_tables.py).

Two moons cycle through 8 phases. Trammel advances slowly, Felucca ~3x faster (C: per moon
tick the trammel counter += 2, the felucca counter += 6; phase = counter >> 5). The open
moongate sits at the Trammel-phase location (MOONGATE_X/Y[trammel]); stepping onto the fully
-open gate teleports the avatar to the Felucca-phase location (MOONGATE_X/Y[felucca]). When
both moons are full (phase 4) the gate instead leads toward the Abyss (loc 0x1f).

We draw the gate straight onto the (now mutable) world map and restore the tile it covers as
the gate moves, so it is both visible and steppable with no extra render path.
"""
from __future__ import annotations

from .data_tables import MOONGATE_X, MOONGATE_Y

GATE_OPEN = 0x43                       # TIL_43: the fully-open moongate (only this is enterable)
GATE_TILES = (0x40, 0x41, 0x42, 0x43)
PHASES = 8


# The moons advance on the animation clock (C: U4_ANIM.C C_3A80), NOT on the player's moves:
# C_3A80 runs from the overworld redraw (C_3B35), and a divider D_1668 (= speed_info/2) gates a
# sub-counter D_1664 that bumps the phase counters every 4th step (+2 Trammel / +6 Felucca; phase
# = counter >> 5). speed_info is the DOS CPU-speed calibration with no fixed value, so MOON_DIV is
# the smallest defensible inference: at our ~18.2 Hz overworld redraw it makes a Trammel-phase step
# ~ every 20s (a full 8-phase cycle ~ 3 min), independent of how far the party walks.
MOON_DIV = 6                           # stand-in for D_1668 reset (speed_info/2)


def tick_moons(game) -> None:
    """One animation tick of the moons (C: U4_ANIM.C C_3A80). Call once per overworld redraw
    frame — never from movement. Advances the time cascade and repositions the open gate when
    the Trammel phase changes."""
    if game._moongate is None:                          # first overworld frame: open a gate now
        _place_gate(game)
    if game._moon_div > 0:                              # D_1668 divider
        game._moon_div -= 1
        return
    game._moon_div = MOON_DIV
    game._moon_sub = (game._moon_sub + 0x40) & 0xFF     # D_1664 += 0x40
    if game._moon_sub != 0:                             # bump only on the 4th step (overflow)
        return
    old_trammel = game.party.trammel
    game._trammel_ctr = (game._trammel_ctr + 2) & 0xFF
    game._felucca_ctr = (game._felucca_ctr + 6) & 0xFF
    game.party.trammel = game._trammel_ctr >> 5
    game.party.felucca = game._felucca_ctr >> 5
    if game.party.trammel != old_trammel:               # gate follows the Trammel phase
        _place_gate(game)


def _restore_gate(game) -> None:
    if game._moongate is not None:
        gx, gy, orig = game._moongate
        game.world.set_tile(gx, gy, orig)
        game._moongate = None


def _place_gate(game) -> None:
    _restore_gate(game)
    tx, ty = MOONGATE_X[game.party.trammel], MOONGATE_Y[game.party.trammel]
    game._moongate = (tx, ty, game.world.tile_at(tx, ty))
    game.world.set_tile(tx, ty, GATE_OPEN)


def step_through(game) -> None:
    """C: U4_MAP.C C_2A91 — teleport from the open gate to the Felucca-phase destination."""
    p = game.party
    if p.trammel == 4 and p.felucca == 4:           # both moons full -> the Abyss approach
        game.message("The moongate pulls thee toward the Stygian Abyss!")
        return
    _restore_gate(game)                             # we are leaving the gate tile
    p.x, p.y = MOONGATE_X[p.felucca], MOONGATE_Y[p.felucca]
    game.message("Enter the moongate!")
