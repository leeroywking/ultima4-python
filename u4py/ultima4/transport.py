"""Transport — ships, horse, balloon (U4_MAP.C / CMD_Board / CMD_X_it).

The party's current vessel is `state.Party.tile`: the avatar's displayed tile, 0x1F on foot.
Boarding changes it to the vessel tile, which changes overworld walkability — a ship sails
water (tiles.SAILABLE), a balloon flies over anything, a horse travels land like foot but is
not slowed by rough terrain. X-it returns you to foot; Fire shoots ship cannons.

Overworld objects (the actual ships/horses on the map) are placed by monsters.py / the editor;
until then there is simply nothing to Board in normal play, which is the faithful behavior.
"""
from __future__ import annotations

from .constants import MOD_OUTDOORS
from .tiles import is_walkable, SAILABLE

SHIP_TILES = (0x10, 0x11, 0x12, 0x13)      # ship facing W / N / E / S
HORSE_TILES = (0x14, 0x15)                 # horse facing W / E
BALLOON_TILE = 0x18
AVATAR_ON_FOOT = 0x1F


def is_ship(t: int) -> bool:    return t in SHIP_TILES
def is_horse(t: int) -> bool:   return t in HORSE_TILES
def is_balloon(t: int) -> bool: return t == BALLOON_TILE
def on_foot(party) -> bool:     return party.tile in (0, AVATAR_ON_FOOT)


def can_move_onto(party_tile: int, target_tile: int) -> bool:
    """Overworld walkability for the current transport. C: U4_MAP.C C_2A38 (ship) / C_2999."""
    if is_ship(party_tile):
        return target_tile in SAILABLE          # ships sail deep/medium water + whirlpools
    if is_balloon(party_tile):
        return True                             # the balloon floats over everything
    return is_walkable(target_tile)             # horse + on foot use land walkability


# --- commands ---------------------------------------------------------------
def cmd_board(game) -> None:
    """C: CMD_Board — board the vessel the avatar stands on."""
    if game.mode != MOD_OUTDOORS or not on_foot(game.party):
        game.message("Board what?")
        return
    t = game.world.tile_at(game.party.x, game.party.y)
    if is_ship(t) or is_horse(t) or is_balloon(t):
        game.party.tile = t
        name = "ship" if is_ship(t) else "horse" if is_horse(t) else "balloon"
        game.message(f"Board {name}!")
    else:
        game.message("Board what?")


def cmd_exit(game) -> None:
    """C: CMD_X_it — leave the current transport onto your feet."""
    if on_foot(game.party):
        game.message("Not here!")
        return
    game.party.tile = AVATAR_ON_FOOT
    game.message("X-it.")


def cmd_fire(game) -> None:
    """C: CMD_Fire — fire ship cannons in a direction (asks Dir)."""
    if not is_ship(game.party.tile):
        game.message("You cannot fire here!")
        return
    game.message("Fire- Dir?")
    game.pending_dir = "fire"


def fire_dir(game, direction: int) -> None:
    """Cannon shot to port/starboard. Damage resolution needs combat.py; for now it booms."""
    game.message("Boom!")
