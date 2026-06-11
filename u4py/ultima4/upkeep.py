"""Per-turn upkeep — faithful port of U4_MAIN.C C_1C53 (the end-of-move housekeeping).

Every completed move runs this once. In source order (C_1C53):
  1. C_10FD  — if no member is still alive, Lord British pulls your spirits from the
               void (C_0EB1): revive at the throne room with a stiff penalty.
  2. hull    — while it is below 50, the ship's hull self-repairs 1 point, 1/3 of moves.
  3. status  — a sleeper ('S') wakes 1/8 of the time; a poisoned ('P') member takes 2.
  4. food    — food (stored x100) drains by party size; hitting 0 starves everyone for 2.
  5. MP       — each living member regenerates 1 magic point up to a class/Int-based cap.
  6. spells  — an active timed spell counts down (not yet modelled here — see note below).

Helpers (hitChara/food_dec/MP_recover) are ported from U4_UTIL.C.
"""
from __future__ import annotations

from .constants import MOD_BUILDING
from .data_tables import MULTI_FLOOR

AVATAR_TILE = 0x1F            # C: TIL_1F — the avatar-on-foot tile set by C_0EB1


def hit_chara(ch, dmg: int) -> bool:
    """Member takes `dmg` damage; returns True if it died. C: U4_UTIL.C hitChara (C_1135)."""
    if ch.hp >= dmg:
        ch.hp -= dmg
        return False
    ch.hp = 0
    ch.status = "D"
    return True


def mp_cap(class_index: int, intel: int) -> int:
    """Magic-point ceiling by class, as a function of Intelligence. C: U4_UTIL.C MP_recover
    (C_13B6). Classes: 0 Mage, 1 Bard, 2 Fighter, 3 Druid, 4 Tinker, 5 Paladin, 6 Ranger,
    7 Shepherd. Fighter/Shepherd cannot cast (cap 0). The cap is hard-clamped to 99."""
    if class_index == 0:                       # Mage
        cap = intel * 2
    elif class_index in (1, 5, 6):             # Bard, Paladin, Ranger
        cap = intel
    elif class_index == 3:                      # Druid
        cap = intel // 2 + intel
    elif class_index == 4:                      # Tinker
        cap = intel // 2
    else:                                       # Fighter (2), Shepherd (7)
        cap = 0
    return min(cap, 99)


def _class_index(ch) -> int:
    """The numeric class byte (0..7). Character creation stores `_class` as chr(index)
    (faithful to the save byte); fall back to 2 (Fighter, no magic) for stray values."""
    idx = ord(ch.char_class[:1] or "\x00")
    return idx if 0 <= idx <= 7 else 2


def per_turn_upkeep(game) -> bool:
    """Run one move's worth of upkeep. C: U4_MAIN.C C_1C53. Returns True if the party was
    relocated (a death/revive), so the caller can skip the rest of its end-of-turn work."""
    party = game.party
    members = party.members                    # the first `member_count` slots

    # 1. Party-death check (C_10FD): nobody alive -> Lord British revives you (C_0EB1).
    if members and not any(c.alive for c in members):
        _revive_at_lb(game)
        return True

    # 2. Restore some hull while it is damaged (1 point, 1/3 of moves, up to 50). C_1C53.
    if party.ship < 50 and game.rng.randint(0, 2) == 0:
        party.ship += 1

    # 3. Status ticks: a sleeper wakes 1/8 of the time; the poisoned take 2 damage.
    for ch in members:
        if ch.status == "S" and game.rng.randint(0, 7) == 0:
            ch.status = "G"
        elif ch.status == "P":
            hit_chara(ch, 2)

    # 4. Food drain (C: food_dec, U4_UTIL.C C_138B). Food is stored x100 and drained by the
    #    party size each move; reaching zero starves every living member for 2 hits.
    party.food -= party.member_count
    if party.food < 0:
        party.food = 0
        game.message("Starving!!!")
        for ch in members:
            if ch.alive:
                hit_chara(ch, 2)

    # 5. Magic-point regen (C: MP_recover, U4_UTIL.C C_13B6): +1 per move, clamped to cap.
    for ch in members:
        if ch.alive:
            ch.mp = min(ch.mp + 1, mp_cap(_class_index(ch), ch.intel))

    # 6. spell_cnt countdown (C_1C53): we do not yet model timed whole-party spell effects
    #    (Negate/Quickness/etc.), so there is no spell_cnt to tick here. Left as a deviation.
    return False


def _revive_at_lb(game) -> None:
    """All members fell — Lord British pulls your spirits from the void, dropping you in
    his throne room with weapons/armor stripped and food/gold reset. C: U4_UTIL.C C_0EB1."""
    party = game.party
    # Into Lord British's castle, upstairs throne room (LCB_2), at the fixed revive spot.
    game.combat = None
    game.dungeon = None
    party.loc = 0x01
    game.floor_files = list(MULTI_FLOOR[1])    # ("LCB_1.ULT", "LCB_2.ULT")
    game.floor = 1                             # LCB_2.ULT — the throne room
    party.x, party.y = 0x13, 0x08              # C_0EB1: _x=0x13, _y=0x08
    party.out_x, party.out_y = 0x56, 0x6C      # overworld spot outside the castle
    party.tile = AVATAR_TILE
    party.flying = 0
    game.mode = MOD_BUILDING
    game._load_floor()
    # Revive everyone to full HP; strip equipment; reset food & gold (the death penalty).
    for ch in party.members:
        ch.status = "G"
        ch.hp = ch.hp_max
    party.weapons = [0] * 16
    party.armors = [0] * 8
    party.food = 20099                         # C_0EB1: Party._food = 20099L  (=> 200 shown)
    party.gold = 200
    game.message("Lord British says: I have pulled thy spirit and some "
                 "possessions from the void.  Be more careful in the future!")
