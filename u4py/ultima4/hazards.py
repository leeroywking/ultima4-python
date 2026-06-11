"""Environmental hazards — faithful port of U4_EVT.C C_9209 (the per-turn "random event").

Each turn the tile the party stands on can bite: swamp and poison fields poison a healthy
member (1/8), sleep fields put a conscious member to sleep (1/4), and lava/fire burns the
party on foot (1/2 → 10..24) or, at sea, eats the ship's hull (a sinking is fatal). The poison
inflicted here is exactly what upkeep.py then drains 2/move — together they close the status
loop. C: U4_EVT.C C_9209 / C_91D1 / C_919A / C_1584 (the lava case lives in U4_UTIL.C).
"""
from __future__ import annotations

from .constants import MOD_OUTDOORS

# Hazard tiles, by their tiles.py ids (C: U4_EVT.C tile_cur switch).
_SWAMP = 0x03
_POISON_FIELD = 0x44
_SLEEP_FIELD = 0x47
_FIRE_FIELD = 0x46          # the volcanic Abyss approach reads as lava here too (C: TIL_46)
_LAVA = 0x4C
_BRIDGE = 0x17              # C: TIL_17 — bridges where trolls lie in ambush
_TROLL = 0xA4              # C: TIL_A4 — the bridge-troll monster sprite
_SHIP_TILE_MAX = 0x13       # C: TIL_13 — avatar _tile <= this means "aboard a ship"


def _poison_field(game) -> None:        # C: U4_EVT.C C_91D1
    """Each healthy ('G') member has a 1/8 chance to be poisoned."""
    for ch in game.party.members:
        if ch.status == "G" and game.rng.randint(0, 7) == 0:
            ch.status = "P"


def _sleep_field(game) -> None:         # C: U4_EVT.C C_919A
    """Each conscious member has a 1/4 chance to fall asleep."""
    for ch in game.party.members:
        if ch.conscious and game.rng.randint(0, 3) == 0:
            ch.status = "S"


def _lava(game) -> bool:                # C: U4_UTIL.C C_1584
    """Burn the party on foot, or damage the hull at sea (sinking revives at Lord British).
    Returns True if the ship sank (the party was relocated)."""
    from . import upkeep
    p = game.party
    if p.tile > _SHIP_TILE_MAX:         # on foot / horse: each alive member, 1/2 -> 10..24
        for ch in p.members:
            if ch.alive and game.rng.randint(0, 1):
                upkeep.hit_chara(ch, game.rng.randint(0, 14) + 10)   # C: U4_RND3(15)+10
        return False
    p.ship -= 10                        # at sea: the hull takes 10
    if p.ship < 0:
        p.ship = 0
        game.message("Thy Ship Sinks!")
        upkeep._revive_at_lb(game)      # C: C_0EB1
        return True
    return False


def per_turn_hazard(game) -> bool:
    """Run the standing-tile hazard once per overworld move. C: U4_EVT.C C_9209 (overworld
    branch). Returns True if it relocated the party (a fatal sinking), so end_turn can stop."""
    if game.mode != MOD_OUTDOORS:
        return False
    tile = game.world.tile_at(game.party.x, game.party.y)
    # Bridge trolls ambush 1/8 of moves on a bridge (C: C_9209, ahead of the flying gate).
    if tile == _BRIDGE and game.rng.randint(0, 7) == 0:
        from . import combat
        game.message("Bridge Trolls!")
        combat.start_encounter(game, _TROLL)
        return True
    if game.party.flying:                                # ballooning floats over the rest (f_1dc)
        return False
    if tile in (_SWAMP, _POISON_FIELD):
        _poison_field(game)
    elif tile in (_FIRE_FIELD, _LAVA):
        return _lava(game)
    elif tile == _SLEEP_FIELD:
        _sleep_field(game)
    return False
