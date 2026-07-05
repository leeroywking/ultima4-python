"""Combat (U4_COMBA.C / U4_COMBB.C / U4_COMBC.C + U4_AI.C).

When the party meets a monster the game switches to MOD_COMBAT on an 11x11 arena. Party
members and monsters alternate rounds: the player acts each conscious member (move / Attack
a direction / Pass), then every monster acts (close on the nearest member, strike if in
range). Killing all monsters wins (XP awarded); losing the whole party returns you to the
overworld, battered.

v1 uses a clean generated brick arena (loading the per-terrain `.CON` maps for arena visuals
is a refinement); the turn loop, AI, and hit resolution are real. Cites the C combat funcs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .constants import DIR_DX, DIR_DY, MOD_COMBAT, MOD_OUTDOORS
from .tiles import is_walkable, tile_name, BRICK_FLOOR

ARENA = 11

# Per-weapon melee/ranged damage ceiling (rough U4 values, by weapon id 0..15).
WEAPON_DMG = (8, 16, 8, 16, 24, 32, 40, 32, 48, 8, 48, 64, 96, 80, 128, 255)
RANGED_WEAPONS = {3, 7, 8, 9, 13, 14}      # sling, bow, crossbow, oil, magic bow, wand
RANGED_REACH = 3


AVATAR_TILE = 0x1F                        # TIL_1F: the Avatar figure (party slot 0)
_CLASS_FIGURE_BASE = 0x20                 # class person-tiles: 0x20 mage, 0x22 bard, .. 0x2E shepherd


def party_member_tile(index: int, chara) -> int:
    """The arena figure for a party member. Slot 0 (the Avatar) keeps the avatar tile; each
    companion shows as its CLASS figure — the person-tiles in tiles.py are laid out by class
    (CLASS_NAMES order), two animation frames apart: `0x20 + 2*class` (mage 0x20 .. shepherd 0x2E).
    The class is the character's `_class` byte (C: tChara._class)."""
    if index == 0:
        return AVATAR_TILE
    cls = ord((chara.char_class or "\x00")[:1]) & 0x07
    return _CLASS_FIGURE_BASE + 2 * cls


def monster_hp(tile: int) -> int:
    """Rougher monsters (higher tile id) have more HP. C: monster stats table."""
    if tile < 0x90:
        return 16                          # sea creatures
    return 16 + (tile - 0x90)              # rat(0x90)=16 .. balron(0xFC)≈124


@dataclass
class Unit:
    x: int
    y: int
    tile: int
    hp: int
    hp_max: int
    member: int = -1                       # >=0 => party member index; -1 => monster

    @property
    def alive(self) -> bool:
        return self.hp > 0


class CombatState:
    """One encounter on an 11x11 arena. C: struct tCombat / U4_COMBA.C."""

    def __init__(self, game, monster_tile: int):
        self.game = game
        self.arena = [[BRICK_FLOOR] * ARENA for _ in range(ARENA)]
        self.party_units: List[Unit] = []
        self.monsters: List[Unit] = []
        self.over = False
        self.won = False

        members = game.party.members or [game.party.chara[0]]
        row = 1
        for i, c in enumerate(members):
            if c.alive:
                tile = party_member_tile(i, c)
                self.party_units.append(Unit(1, min(row, ARENA - 2), tile, c.hp, c.hp_max, member=i))
                row += 2
        count = 1 + game.rng.randint(0, 2)
        row = 1
        for _ in range(count):
            hp = monster_hp(monster_tile)
            self.monsters.append(Unit(ARENA - 2, min(row, ARENA - 2), monster_tile, hp, hp))
            row += 2
        self.active = 0                    # index into party_units for the current member

    # --- helpers ------------------------------------------------------------
    def _occupied(self, x: int, y: int) -> Optional[Unit]:
        for u in self.party_units + self.monsters:
            if u.alive and u.x == x and u.y == y:
                return u
        return None

    def current(self) -> Optional[Unit]:
        living = [u for u in self.party_units if u.alive]
        if not living:
            return None
        self.active %= len(living)
        return living[self.active]

    # --- player actions -----------------------------------------------------
    def move(self, direction: int) -> None:
        u = self.current()
        if u is None:
            return
        nx, ny = u.x + DIR_DX[direction], u.y + DIR_DY[direction]
        if 0 <= nx < ARENA and 0 <= ny < ARENA and is_walkable(self.arena[ny][nx]) \
                and self._occupied(nx, ny) is None:
            u.x, u.y = nx, ny
        self._end_member_turn()

    def attack(self, direction: int) -> None:
        u = self.current()
        if u is None:
            return
        weapon = self.game.party.chara[u.member].weapon
        reach = RANGED_REACH if weapon in RANGED_WEAPONS else 1
        dx, dy = DIR_DX[direction], DIR_DY[direction]
        for step in range(1, reach + 1):
            tgt = self._occupied(u.x + dx * step, u.y + dy * step)
            if tgt is not None and tgt.member == -1:
                self._strike(u, tgt, WEAPON_DMG[weapon % 16])
                break
            if tgt is not None:
                break                      # a friendly body blocks the shot
        else:
            self.game.message("Missed -- nothing in range.")
        self._end_member_turn()

    def pass_turn(self) -> None:
        self._end_member_turn()

    # --- resolution ---------------------------------------------------------
    def _strike(self, attacker: Unit, target: Unit, max_dmg: int) -> None:
        if self.game.rng.random() < 0.25:               # C: hit chance vs DEX/level
            self.game.message("Missed!")
            return
        dmg = self.game.rng.randint(max_dmg // 4 + 1, max_dmg)
        target.hp -= dmg
        name = tile_name(target.tile).replace("_", " ")
        if target.hp <= 0:
            target.hp = 0
            self.game.message(f"{name} is slain!")
        else:
            self.game.message(f"{name} takes {dmg}!")
        # mirror party-member HP back onto the real character
        if target.member >= 0:
            self.game.party.chara[target.member].hp = max(0, target.hp)
            if target.hp == 0:
                self.game.party.chara[target.member].status = "D"

    def _end_member_turn(self) -> None:
        if self._check_end():
            return
        living = [u for u in self.party_units if u.alive]
        self.active += 1
        if self.active >= len(living):                  # all members acted -> monsters act
            self.active = 0
            self._monster_round()
            self._check_end()

    def _monster_round(self) -> None:
        for m in self.monsters:
            if not m.alive:
                continue
            target = min((u for u in self.party_units if u.alive),
                         key=lambda u: abs(u.x - m.x) + abs(u.y - m.y), default=None)
            if target is None:
                return
            if abs(target.x - m.x) + abs(target.y - m.y) <= 1:        # adjacent -> strike
                self._strike(m, target, 16 + (m.tile & 0x0F))
            else:                                                     # else step closer
                sx = (target.x > m.x) - (target.x < m.x)
                sy = (target.y > m.y) - (target.y < m.y)
                for nx, ny in ((m.x + sx, m.y), (m.x, m.y + sy)):
                    if 0 <= nx < ARENA and 0 <= ny < ARENA and is_walkable(self.arena[ny][nx]) \
                            and self._occupied(nx, ny) is None:
                        m.x, m.y = nx, ny
                        break

    def _check_end(self) -> bool:
        if not any(m.alive for m in self.monsters):
            self.over, self.won = True, True
            return True
        if not any(u.alive for u in self.party_units):
            self.over, self.won = True, False
            return True
        return False

    def sprites(self):
        """(x, y, tile) of every living combatant, for the renderer."""
        return [(u.x, u.y, u.tile) for u in self.party_units + self.monsters if u.alive]


def start_encounter(game, monster_tile: int) -> CombatState:
    """Begin combat (C: C_7DFE). Switches game.mode to MOD_COMBAT."""
    game._combat_return = (game.mode, game.party.x, game.party.y)
    game.combat = CombatState(game, monster_tile)
    game.mode = MOD_COMBAT
    game.message("*** Combat! ***")
    return game.combat


def finish(game) -> None:
    """End combat: award XP on a win, then return to the prior mode (C: end-of-combat)."""
    c = game.combat
    if c is not None and c.won:
        xp = sum(m.hp_max for m in c.monsters)
        for ch in game.party.members:
            if ch.alive:
                ch.xp = min(9999, ch.xp + max(1, xp // max(1, len(game.party.members))))
        game.message("Victory!")
    elif c is not None:
        game.message("All is lost!  Thou art driven back...")
    game.combat = None
    game.mode, game.party.x, game.party.y = getattr(game, "_combat_return", (MOD_OUTDOORS, game.party.x, game.party.y))


def cmd_attack(game) -> None:
    """C: U4_COMBA.C CMD_Attack — strike an adjacent creature, starting combat from the map."""
    raise NotImplementedError("map-attack (starting combat by attacking) not yet wired")
