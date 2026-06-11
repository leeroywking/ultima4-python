"""Game engine: init + main-loop dispatch, ported from U4_MAIN.C and U4_INIT.C.

This is the skeleton of the interactive game. The command table mirrors the scancode
switch in `main()` (U4_MAIN.C); movement (CMDDIR_*) is implemented faithfully for the
overworld on-foot case so the avatar actually walks. The remaining CMD_* commands are
named stubs to be filled in Phase 1, each citing its C function.

Kept rendering-free on purpose: this module is pure state + rules, so it can be unit
tested headlessly and driven by any front-end (the pygame window in render.py).
"""
from __future__ import annotations

import random
from typing import Callable, Dict, List, Optional

from .constants import (DIR_W, DIR_N, DIR_E, DIR_S, DIR_DX, DIR_DY,
                        MOD_OUTDOORS, MOD_BUILDING, MOD_COMBAT, MOD_DUNGEON, MODE_NAMES)
from .data_tables import (MOONGATE_X, MOONGATE_Y, PLACE_X, PLACE_Y,
                          LOCATION_FILES, MULTI_FLOOR)
from . import (combat, dungeon, hazards, items, mixing, moongate, monsters, shrines, spells,
               transport, upkeep)   # v1 modules
from .dialogue import Conversation, TalkData, load_for_location
from .lb import LordBritish, level_for_xp
from .location import Location, NPC
from .savefile import load_party, save_party
from .shops import open_shop, SHOP_SIGN_Y
from .state import Party
from .tiles import (is_walkable, is_sign_glyph, SLOW_PROGRESS, tile_name,
                    CHEST, LADDER_UP, LADDER_DOWN, MERCHANT, LORD_BRITISH,
                    DEEP_WATER, SWAMP, SCRUB, FOREST, HILLS, FIRE_FIELD,
                    TOWN, CASTLE, VILLAGE, RUINS, SHRINE, DUNGEON_ENTRANCE,
                    LB_CASTLE_ENTRANCE, DOOR, LOCKED_DOOR, BRICK_FLOOR)
from .world import World


def _sign(n: int) -> int:                 # C: u4_sign
    return (n > 0) - (n < 0)


def _signed_byte(b: int) -> int:          # interpret a 0..255 var as a signed char
    return b - 256 if b >= 128 else b

# Top-level movement is arrows only (C: U4 moves with arrow keys; letters are commands,
# so e.g. the 'E' key is Enter, never "move East").
_ARROW_KEYS = {"UP": DIR_N, "DOWN": DIR_S, "LEFT": DIR_W, "RIGHT": DIR_E}
# Direction *selection* (after a command like Talk asks "Dir:") additionally accepts the
# bare compass letters, since that's a direction prompt, not the command layer.
_DIR_KEYS = {**_ARROW_KEYS, "N": DIR_N, "S": DIR_S, "E": DIR_E, "W": DIR_W}


class Game:
    def __init__(self, party: Optional[Party] = None, world: Optional[World] = None):
        # C: U4_INIT.C C_C51C — load save + map, set moon-driven moongate dests, go outdoors.
        self.party = party if party is not None else load_party()
        self.world = world if world is not None else World.load()
        self.mode = MOD_OUTDOORS
        self.location: Optional[Location] = None   # current town/castle when MOD_BUILDING
        self.messages: List[str] = []
        self.rng = random.Random()
        self.active = None                  # current interaction (Conversation or shop), or None
        self.pending_dir: Optional[str] = None             # command awaiting a direction
        self._talk_cache: Dict[int, TalkData] = {}         # loc_id -> parsed .TLK
        self._door: Optional[tuple] = None                 # (x, y, turns_left) of an open door
        self.torchlight = 0                                # turns of torch light remaining
        self._trammel_ctr = (self.party.trammel & 7) << 5  # 8-bit moon counters (phase=ctr>>5)
        self._felucca_ctr = (self.party.felucca & 7) << 5
        self._moon_div = 0                                 # C: D_1668 divider (moons tick on time)
        self._moon_sub = 0                                 # C: D_1664 sub-counter
        self._moongate: Optional[tuple] = None             # (x, y, covered_tile) of the open gate
        self.monsters: List = []                           # active overworld monsters (monsters.py)
        self.combat = None                                 # CombatState when MOD_COMBAT
        self._combat_return = (MOD_OUTDOORS, 0, 0)         # (mode, x, y) to restore after combat
        self.dungeon = None                                # DungeonState when MOD_DUNGEON
        self._dungeon_return = (0, 0)                      # overworld (x, y) to restore on exit
        self.elevated = set()                              # virtue indices with partial Avatarhood
        self.won = False                                   # set when the Codex quest is completed
        self.quit_requested = False                        # set by Quit&Save so the driver exits
        # Fresh "no party" saves sit at loc 0; keep the avatar on the overworld.
        if not (0x11 <= self.party.loc <= 0x18):
            self.party.loc = 0
        self._build_dispatch()

    def load_saved(self, name: str = "PARTY.SAV") -> None:
        """Resume a saved game ('Journey Onward'). C: U4_INIT.C Load("PARTY.SAV", &Party).
        Restores the byte-accurate party (position, transport, karma, moons) and re-derives the
        moon counters. Minimal: we always resume on the overworld (dungeon/town map state isn't
        persisted yet), placing the avatar at its saved world position."""
        self.party = load_party(name)
        self._trammel_ctr = (self.party.trammel & 7) << 5
        self._felucca_ctr = (self.party.felucca & 7) << 5
        if self.party.loc:                                 # was inside a location -> step back out
            self.party.x, self.party.y = self.party.out_x, self.party.out_y
            self.party.loc = 0
        self.mode = MOD_OUTDOORS
        self.location = None

    # --- main loop dispatch (C: U4_MAIN.C main() switch) ---------------------
    def _build_dispatch(self) -> None:
        self.commands: Dict[str, Callable[[], None]] = {
            "A": self.cmd_attack, "B": self.cmd_board, "C": self.cmd_cast,
            "D": self.cmd_descend, "E": self.cmd_enter, "F": self.cmd_fire,
            "G": self.cmd_get, "H": self.cmd_hole_up, "I": self.cmd_ignite,
            "J": self.cmd_jimmy, "K": self.cmd_klimb, "L": self.cmd_locate,
            "M": self.cmd_mix, "N": self.cmd_new_order, "O": self.cmd_open,
            "P": self.cmd_peer, "Q": self.cmd_quit, "R": self.cmd_ready,
            "S": self.cmd_search, "T": self.cmd_talk, "U": self.cmd_use,
            "V": self.cmd_volume, "W": self.cmd_wear, "X": self.cmd_x_it,
            "Y": self.cmd_yell, "Z": self.cmd_ztats,
        }

    def handle(self, key: str) -> None:
        """Process one player input. `key` is a logical token (a letter, a move name)."""
        key = key.upper()
        # A live interaction (talk/shop) swallows single keystrokes; the front-end routes
        # typed lines to feed() instead (C: CMD_Talk runs its own input loop).
        if self.active is not None:
            return
        # Combat is its own input mode (move the active member, A=attack, space=pass).
        if self.mode == MOD_COMBAT and self.combat is not None:
            self._combat_input(key)
            return
        # Dungeon is first-person: arrows advance/turn, K/D climb, X exits. Other letters
        # (Cast, Ztats, ...) fall through to the normal command dispatch below.
        if self.mode == MOD_DUNGEON and self.dungeon is not None:
            if self._dungeon_input(key):
                return
        # A command that asked "which direction?" consumes the next move key. It does NOT
        # cost a turn until it actually resolves into an action.
        if self.pending_dir is not None:
            cmd, self.pending_dir = self.pending_dir, None
            direction = _DIR_KEYS.get(key)
            if direction is not None:
                self._resolve_dir(cmd, direction)
            else:
                self.message("Nevermind.")
            if self.active is None:
                self.end_turn()
            return
        if key in _ARROW_KEYS:
            self._move(_ARROW_KEYS[key])
            self.end_turn()
            return
        if key in (" ", "SPACE", "PASS"):
            self.end_turn()                         # C: w_Pass()
            return
        cmd = self.commands.get(key)
        if cmd is None:
            self.message("Bad command!")            # C: U4_MAIN.C default case
            return
        cmd()
        # Commands that opened a sub-interaction or are waiting for a direction haven't
        # taken their turn yet — feed()/the direction key will end it.
        if self.pending_dir is None and self.active is None:
            self.end_turn()

    # --- movement (C: U4_MAP.C CMDDIR_* / C_2B19 etc.) -----------------------
    def _move(self, direction: int) -> bool:
        if self.mode == MOD_BUILDING:
            return self._move_building(direction)
        return self._move_overworld(direction)

    def _move_overworld(self, direction: int) -> bool:
        dx, dy = DIR_DX[direction], DIR_DY[direction]
        nx, ny = (self.party.x + dx) & 0xFF, (self.party.y + dy) & 0xFF
        target = self.world.tile_at(nx, ny)
        # C: C_2B19 lets you step onto the LB-castle entrance even though it's not in the
        # walkable set, so you can stand on it and Enter. Vessel rules come from transport.py.
        if target != LB_CASTLE_ENTRANCE and not transport.can_move_onto(self.party.tile, target):
            self.message("Blocked!")                # C: !C_2999 -> w_Blocked
            return False
        # Rough-terrain slow progress applies on foot/horse only (not ship/balloon).
        if transport.on_foot(self.party) and target in SLOW_PROGRESS and self._slow_blocks(target):
            self.message("Slow progress!")          # C: C_29EF
            return True                             # turn consumed, no movement
        self.party.x, self.party.y = nx, ny
        self.message(_DIR_WORDS[direction])
        if target == moongate.GATE_OPEN:             # stepped onto an open moongate
            moongate.step_through(self)
        return True

    def _move_building(self, direction: int) -> bool:
        """Move within a town's 32x32 map; stepping off any edge leaves (C: C_2747)."""
        dx, dy = DIR_DX[direction], DIR_DY[direction]
        nx, ny = self.party.x + dx, self.party.y + dy
        target = self.location.tile_at(nx, ny)
        if target is None:                          # walked off the edge -> leave
            self._leave_location()
            return True
        if self.location.npc_at(nx, ny) is not None or not is_walkable(target):
            self.message("Blocked!")
            return False
        self.party.x, self.party.y = nx, ny
        self.message(_DIR_WORDS[direction])
        return True

    def _leave_location(self) -> None:
        # C: U4_MAP.C C_2747 "Leaving..." — restore overworld position and mode.
        self.message("Leaving...")
        self.party.x, self.party.y = self.party.out_x, self.party.out_y
        self.party.loc = 0
        self.mode = MOD_OUTDOORS
        self.location = None

    def _slow_blocks(self, tile: int) -> bool:
        """C: U4_MAP.C C_29EF — chance that rough terrain eats the move."""
        if tile == SWAMP:
            return self.rng.randint(0, 7) == 0          # 1/8
        if tile in (SCRUB, FOREST):
            return self.rng.randint(0, 3) == 0          # 1/4
        if tile in (HILLS, FIRE_FIELD):
            return self.rng.randint(0, 1) == 0          # 1/2
        return False

    # --- end of turn (C: U4_MAIN.C C_1C53) -----------------------------------
    def end_turn(self) -> None:
        self.party.moves += 1
        if hazards.per_turn_hazard(self):            # C: C_9209 — standing-tile field/lava hazard
            return                                   # a fatal sinking relocated the party
        if upkeep.per_turn_upkeep(self):             # C: C_1C53 — food/status/MP/hull/death
            return                                   # party was revived at LB; skip the rest
        if self.mode == MOD_BUILDING and self.location is not None:
            self._move_npcs_building()
            self._tick_door()
        elif self.mode == MOD_OUTDOORS:
            monsters.spawn_and_move(self)            # roam overworld monsters; fight if adjacent
        # Note: the moons are NOT advanced here — they run on their own animation clock
        # (game.tick_moons, called from the redraw loop), independent of movement. C: U4_ANIM.C C_3A80.

    def tick_moons(self) -> None:
        """Advance the moons one animation tick (C: U4_ANIM.C C_3A80). Driven by the real-time
        redraw loop on the overworld, not by movement — so the moons cycle even while standing
        still and freeze off the overworld (the HUD is overworld-only)."""
        if self.mode == MOD_OUTDOORS:
            moongate.tick_moons(self)
        # Per-move upkeep (food/status/MP/hull/death) lives in end_turn via upkeep.py
        # (C: C_1C53) — it is move-driven, not on this animation clock.

    # --- dungeon input mode (C: U4_DNG.C DNG_main) ---------------------------
    def _dungeon_input(self, key: str) -> bool:
        d = self.dungeon
        actions = {"UP": d.advance, "DOWN": d.retreat, "LEFT": d.turn_left,
                   "RIGHT": d.turn_right, "K": d.klimb, "D": d.descend}
        if key in actions:
            actions[key]()
            self.party.moves += 1
            upkeep.per_turn_upkeep(self)             # C: U4_DNG.C mirrors C_1C53 upkeep
            return True
        if key == "X":
            self._exit_dungeon()
            return True
        return False                                    # let normal commands (C/Z/M/...) run

    def _exit_dungeon(self) -> None:
        self.dungeon = None
        self.party.x, self.party.y = self._dungeon_return
        self.party.loc = 0
        self.mode = MOD_OUTDOORS
        self.message("Leaving the dungeon...")

    # --- combat input mode (C: U4_COMBA.C in-combat dispatch) ----------------
    def _combat_input(self, key: str) -> None:
        c = self.combat
        if self.pending_dir == "combat_attack":
            self.pending_dir = None
            direction = _DIR_KEYS.get(key)
            if direction is not None:
                c.attack(direction)
            else:
                self.message("Nevermind.")
        elif key in _DIR_KEYS:
            c.move(_DIR_KEYS[key])
        elif key == "A":
            self.pending_dir = "combat_attack"
            self.message("Attack- Dir?")
            return
        elif key in (" ", "SPACE", "PASS", "."):
            c.pass_turn()
        else:
            self.message("Combat: arrows move, A attacks, space passes.")
            return
        if c.over:
            combat.finish(self)

    # --- direction-targeted commands (C: AskDir then act) --------------------
    def _resolve_dir(self, cmd: str, direction: int) -> None:
        if cmd == "talk":
            self._talk_dir(direction)
        elif cmd == "open":
            self._open_door(direction)
        elif cmd == "jimmy":
            self._jimmy(direction)
        elif cmd == "get":
            items.get_dir(self, direction)
        elif cmd == "fire":
            transport.fire_dir(self, direction)
        # (future: attack also AskDir first, dispatched here)

    # --- Open / Jimmy doors (C: U4_EXPLO.C CMD_Open / CMD_Jimmy) --------------
    def cmd_open(self) -> None:
        if self.mode != MOD_BUILDING or self.location is None:
            self.message("Not here!")
            return
        self.message("Open- Dir?")
        self.pending_dir = "open"

    def cmd_jimmy(self) -> None:
        if self.mode != MOD_BUILDING or self.location is None:
            self.message("Not here!")
            return
        self.message("Jimmy- Dir?")
        self.pending_dir = "jimmy"

    def _open_door(self, direction: int) -> None:
        dx, dy = DIR_DX[direction], DIR_DY[direction]
        tx, ty = self.party.x + dx, self.party.y + dy
        tile = self.location.tile_at(tx, ty)
        if tile == LOCKED_DOOR:
            self.message("Can't!  'Tis locked.  (Jimmy it.)")
        elif tile == DOOR:
            self.location.tiles[ty * 32 + tx] = BRICK_FLOOR   # opened: walkable for a while
            self._door = (tx, ty, 5)                          # C: auto-closes after 5 turns
            self.message("Opened!")
        else:
            self.message("Not here!")

    def _jimmy(self, direction: int) -> None:
        dx, dy = DIR_DX[direction], DIR_DY[direction]
        tx, ty = self.party.x + dx, self.party.y + dy
        if self.location.tile_at(tx, ty) != LOCKED_DOOR:
            self.message("Not here!")
        elif self.party.keys == 0:
            self.message("No keys left!")
        else:
            self.party.keys -= 1
            self.location.tiles[ty * 32 + tx] = DOOR          # now merely closed; Open it
            self.message("Unlocked!")

    # --- Talk (C: U4_TALK.C CMD_Talk / C_A4B4) -------------------------------
    def cmd_talk(self) -> None:
        if self.mode != MOD_BUILDING or self.location is None:
            self.message("Funny, no response!")          # C: D_2A7A
            return
        self.message("Talk- Dir?")
        self.pending_dir = "talk"

    def _talk_dir(self, direction: int) -> None:
        dx, dy = DIR_DX[direction], DIR_DY[direction]
        tx, ty = self.party.x + dx, self.party.y + dy
        tile = self.location.tile_at(tx, ty)
        # Sign-board path: a glyph tile with a merchant behind it opens a shop (C: CMD_Talk
        # alphabet branch -> C_A686, keyed off the sign's row).
        if tile is not None and is_sign_glyph(tile):
            merchant = self.location.npc_at(tx + dx, ty + dy)
            if merchant is not None and merchant.tile == MERCHANT:
                self._open_shop_at(ty)
            else:
                self.message("Funny, no response!")
            return
        npc = self.location.npc_at(tx, ty)
        if npc is None:
            self.message("Funny, no response!")
            return
        if npc.dialogue is not None:                     # editor-injected NPC (inline dialogue)
            self._begin(Conversation(self, npc, npc.dialogue))
            return
        if npc.tlkidx == 0:                              # C: no dialogue
            self.message("Funny, no response!")
            return
        if npc.tile == LORD_BRITISH:                     # C: C_E59B (U4_LB.C)
            self._begin(LordBritish(self))
            return
        dialogue = self._talk_data().for_npc(npc.tlkidx)
        if dialogue is None:
            self.message("Funny, no response!")
            return
        self._begin(Conversation(self, npc, dialogue))

    def _open_shop_at(self, sign_y: int) -> None:
        """C: C_A686 — map a sign's row to a shop slot for this town, then open it."""
        rows = SHOP_SIGN_Y[self.party.loc - 1]
        slot = next((s for s in range(7, -1, -1) if rows[s] == sign_y), None)
        if slot is None:
            self.message("Funny, no response!")
            return
        session, msg = open_shop(self, slot)
        if session is None:
            self.message(msg)
            return
        self._begin(session)

    # --- generic interaction plumbing (Talk + shops share this) --------------
    def _begin(self, interaction) -> None:
        self.active = interaction
        for line in interaction.intro():
            self.message(line)
        self.message(interaction.prompt)

    def feed(self, text: str) -> None:
        """Feed one typed line to the active interaction (front-end calls this)."""
        if self.active is None:
            return
        for line in self.active.respond(text):
            self.message(line)
        if self.active.done:
            self.active = None
            self.message("")
            self.end_turn()
        else:
            self.message(self.active.prompt)

    talk_input = feed              # back-compat alias

    def _talk_data(self) -> TalkData:
        loc = self.party.loc
        if loc not in self._talk_cache:
            self._talk_cache[loc] = load_for_location(loc)   # prefers editable JSON
        return self._talk_cache[loc]

    # --- NPC movement in towns (C: U4_NPC.C C_5293 / C_51A7 / C_4E94) --------
    def _move_npcs_building(self) -> None:
        for n in self.location.npcs:
            if n.tile == 0 or n.var == 0:                # 0 => stationary (shopkeepers)
                continue
            v = _signed_byte(n.var)
            if v >= 0:                                   # random wander
                if self.rng.random() < 0.5:
                    self._npc_step(n, _sign(self.rng.randint(-128, 127)),
                                   _sign(self.rng.randint(-128, 127)), tries=2)
            else:                                        # follow the avatar
                sx = _sign(self.party.x - n.x)
                sy = _sign(self.party.y - n.y)
                if abs(self.party.x - n.x) + abs(self.party.y - n.y) >= 2:
                    self._npc_step(n, sx, sy, tries=2)
                # adjacent + 0xff would attack here (combat: Phase 2)

    def _npc_step(self, n: NPC, dx: int, dy: int, tries: int) -> None:
        """C: C_51A7 — try horizontal-then-vertical, else retry a random direction."""
        if dx and self.rng.random() < 0.5:
            if self._npc_can_move(n, n.x + dx, n.y):
                self._npc_do_move(n, n.x + dx, n.y)
            return
        if dy:
            if self._npc_can_move(n, n.x, n.y + dy):
                self._npc_do_move(n, n.x, n.y + dy)
            return
        if dx and self._npc_can_move(n, n.x + dx, n.y):
            self._npc_do_move(n, n.x + dx, n.y)
            return
        if n.var != 0x80 and tries > 0:
            self._npc_step(n, _sign(self.rng.randint(-128, 127)),
                           _sign(self.rng.randint(-128, 127)), tries - 1)

    def _npc_can_move(self, n: NPC, nx: int, ny: int) -> bool:
        """C: C_4E94 for a town NPC (display tile < 0x80)."""
        if not (0 <= nx < 32 and 0 <= ny < 32):
            return False
        for other in self.location.npcs:
            if (other.tile and other.x == nx and other.y == ny
                    and other.tile != CHEST):
                return False
        if self.party.x == nx and self.party.y == ny:
            return False
        if (nx, ny) == (n.old_x, n.old_y) and self.rng.randint(0, 3) == 0:
            return False
        return is_walkable(self.location.tile_at(nx, ny))

    def _npc_do_move(self, n: NPC, nx: int, ny: int) -> None:
        n.old_x, n.old_y = n.x, n.y
        n.x, n.y = nx, ny

    def _tick_door(self) -> None:
        """C: C_431D — an opened door swings shut after a few turns."""
        if not self._door:
            return
        x, y, turns = self._door
        turns -= 1
        if turns <= 0:
            self.location.tiles[y * 32 + x] = DOOR
            self._door = None
        else:
            self._door = (x, y, turns)

    # --- entering a location (C: U4_EXPLO.C CMD_Enter / C_4018) ---------------
    def cmd_enter(self) -> None:
        if self.party.loc != 0:                      # C: only from the overworld
            self.message("Enter what?")
            return
        # Find which place we're standing on (C: scan D_0844/D_0864).
        place = next((i for i in range(len(PLACE_X))
                      if PLACE_X[i] == self.party.x and PLACE_Y[i] == self.party.y), None)
        if place is None:
            self.message("Enter what?")
            return
        tile = self.world.tile_at(self.party.x, self.party.y)
        loc_id = place + 1
        if tile in (TOWN, VILLAGE, RUINS):
            self._enter_location(loc_id, entry=(1, 15), kind="towne")
        elif tile in (CASTLE, LB_CASTLE_ENTRANCE):
            self._enter_location(loc_id, entry=(15, 30), kind="castle")
        elif tile == DUNGEON_ENTRANCE:
            dungeon.enter_dungeon(self, 0x11 + (place % 8))   # C: U4_DNG.C entry
        elif tile == SHRINE:
            shrines.enter_shrine(self, place % 8)            # C: U4_SHRIN.C shrine entry
        elif self.party.x == items.ABYSS_X and self.party.y == items.ABYSS_Y:
            # The Great Stygian Abyss — opens only once the Bell/Book/Candle ritual is done.
            if items.abyss_ritual_done(self.party):          # C: U4_EXPLO.C C_3FB9
                dungeon.enter_dungeon(self, 0x18)            # loc 0x18 -> Abyss.Dng
            else:
                self.message("Can't!")                       # C: w_Cant_t (ritual unfinished)
        else:
            self.message("Enter what?")

    def _enter_location(self, loc_id: int, entry, kind: str) -> None:
        if not 1 <= loc_id <= len(LOCATION_FILES):
            self.message("Enter what?")
            return
        # A location may have several stacked floors (ladders connect them); most have one.
        self.floor_files = list(MULTI_FLOOR.get(loc_id, (LOCATION_FILES[loc_id - 1],)))
        self.floor = 0
        self.party.out_x, self.party.out_y = self.party.x, self.party.y
        self.party.loc = loc_id
        self.party.x, self.party.y = entry           # C: C_3F4A / castle entry coords
        self.mode = MOD_BUILDING
        name = self._load_floor()
        self.message(f"Enter {kind}!  {name}")

    def _load_floor(self) -> str:
        """(Re)load the current floor's .ULT into self.location; returns its display name."""
        fname = self.floor_files[self.floor]
        name = fname.split(".")[0].replace("_1", "").replace("_2", "").title()
        self.location = Location.load(fname, self.party.loc, name)
        return name

    # --- view for the renderer ------------------------------------------------
    def viewport(self, radius: int = 5) -> List[List[int]]:
        """Tile-id grid centred on the avatar, for the current mode.
        In a building, off-map cells render as deep water (0x00) like the original edge."""
        if self.mode == MOD_COMBAT and self.combat is not None:
            return [row[:] for row in self.combat.arena]    # the 11x11 arena
        if self.mode == MOD_DUNGEON and self.dungeon is not None:
            return self.dungeon.viewport(radius)            # top-down dungeon window
        if self.mode == MOD_BUILDING and self.location is not None:
            cx, cy = self.party.x, self.party.y
            grid = []
            for dy in range(-radius, radius + 1):
                row = []
                for dx in range(-radius, radius + 1):
                    t = self.location.tile_at(cx + dx, cy + dy)
                    row.append(DEEP_WATER if t is None else t)
                grid.append(row)
            return grid
        return self.world.viewport(self.party.x, self.party.y, radius)

    def npc_sprites(self, radius: int = 5):
        """(col, row, tile) of NPCs visible in the building viewport, for the renderer."""
        if self.mode != MOD_BUILDING or self.location is None:
            return []
        cx, cy = self.party.x, self.party.y
        out = []
        for n in self.location.npcs:
            dx, dy = n.x - cx, n.y - cy
            if -radius <= dx <= radius and -radius <= dy <= radius:
                out.append((dx + radius, dy + radius, n.tile))
        return out

    def combat_sprites(self):
        """(col, row, tile) of every combatant when MOD_COMBAT (arena coords = viewport coords)."""
        if self.mode == MOD_COMBAT and self.combat is not None:
            return self.combat.sprites()
        return []

    def monster_sprites(self, radius: int = 5):
        """(col, row, tile) of overworld monsters visible in the viewport, for the renderer."""
        if self.mode != MOD_OUTDOORS:
            return []
        out = []
        for m in self.monsters:
            dx = ((m.x - self.party.x + 128) & 0xFF) - 128     # torus-wrapped delta
            dy = ((m.y - self.party.y + 128) & 0xFF) - 128
            if -radius <= dx <= radius and -radius <= dy <= radius:
                out.append((dx + radius, dy + radius, m.tile))
        return out

    def status_line(self) -> str:
        t = self.world.tile_at(self.party.x, self.party.y)
        return (f"[{MODE_NAMES[self.mode]}] ({self.party.x},{self.party.y}) "
                f"on {tile_name(t)}  moves={self.party.moves}  gold={self.party.gold}")

    def message(self, text: str) -> None:
        self.messages.append(text)

    # --- command stubs --------------------------------------------------------
    # The remaining CMD_* keys are wired to their v1 modules (combat/spells/items/transport/
    # mixing). Those modules are scaffolds that raise NotImplementedError; `_stub` catches that
    # and shows a friendly "coming in v1" line instead of crashing, so the dispatch is real and
    # the implementation slots in by filling the module function.
    def _todo(self, name: str) -> None:
        self.message(f"({name}: not yet implemented)")

    def _stub(self, fn, name: str) -> None:
        try:
            fn(self)
        except NotImplementedError:
            self.message(f"({name}: coming in v1)")

    def cmd_attack(self):    self._stub(combat.cmd_attack, "Attack")    # C: U4_COMBA.C
    def cmd_board(self):     self._stub(transport.cmd_board, "Board")   # C: CMD_Board
    def cmd_cast(self):      self._stub(spells.cmd_cast, "Cast")        # C: U4_SPELL.C
    # --- Klimb / Descend between building floors (C: CMD_Klimb / CMD_Descend) -
    def cmd_klimb(self) -> None:
        if self.mode == MOD_BUILDING and self.location is not None:
            if (self.location.tile_at(self.party.x, self.party.y) == LADDER_UP
                    and self.floor + 1 < len(self.floor_files)):
                self.floor += 1
                self._load_floor()                   # ladders align, so keep x/y
                self.message("Klimb!")
                return
            self.message("Klimb what?")
            return
        self._todo("Klimb")                          # outdoor klimb (balloon) later

    def cmd_descend(self) -> None:
        if self.mode == MOD_BUILDING and self.location is not None:
            if (self.location.tile_at(self.party.x, self.party.y) == LADDER_DOWN
                    and self.floor > 0):
                self.floor -= 1
                self._load_floor()
                self.message("Descend!")
                return
            self.message("Descend what?")
            return
        self._todo("Descend")
    # cmd_enter is implemented above (C: U4_EXPLO.C CMD_Enter)
    def cmd_fire(self):      self._stub(transport.cmd_fire, "Fire")     # C: CMD_Fire
    def cmd_get(self):       self._stub(items.cmd_get, "Get")          # C: U4_GET.C
    def cmd_hole_up(self):   self._stub(items.cmd_hole_up, "Hole up")  # C: CMD_HoleUp
    def cmd_ignite(self):    self._stub(items.cmd_ignite, "Ignite")    # C: CMD_Ignite
    # cmd_jimmy is implemented above (C: U4_EXPLO.C CMD_Jimmy)
    def cmd_locate(self):    self._stub(items.cmd_locate, "Locate")    # C: CMD_Locate
    def cmd_mix(self):       self._stub(mixing.cmd_mix, "Mix")         # C: U4_MIX.C
    def cmd_new_order(self): self._todo("New order")  # C: CMD_NewOrder (reorder party)
    # cmd_open is implemented above (C: U4_EXPLO.C CMD_Open)
    def cmd_peer(self):      self._stub(items.cmd_peer, "Peer")        # C: U4_PEER.C
    def cmd_quit(self):
        # C: U4_Q_N_V.C CMD_Quit — "Quit & Save". Only on the overworld (loc 0) or in a dungeon
        # (0x11-0x18); refuses inside a town/castle ("Not Here!"). Writes the byte-accurate
        # PARTY.SAV, then asks the driver to exit (Journey Onward reloads it).
        self.message("Quit & Save...")
        self.message(f"{self.party.moves} moves")
        if self.party.loc and not (0x11 <= self.party.loc <= 0x18):
            self.message("Not Here!")
            return
        save_party(self.party)
        self.message("Saved.")
        self.quit_requested = True
    def cmd_ready(self):     self._stub(items.cmd_ready, "Ready")      # C: CMD_Ready
    def cmd_search(self):    self._stub(items.cmd_search, "Search")    # C: U4_SRCH.C
    # cmd_talk is implemented above (C: U4_TALK.C CMD_Talk)
    def cmd_use(self):       self._stub(items.cmd_use, "Use")          # C: U4_USE.C
    def cmd_volume(self):    self._todo("Volume")     # C: CMD_Volume (sound toggle)
    def cmd_wear(self):      self._stub(items.cmd_wear, "Wear")        # C: CMD_Wear
    def cmd_x_it(self):      self._stub(transport.cmd_exit, "X-it")    # C: CMD_X_it
    def cmd_yell(self):      self._todo("Yell")       # C: CMD_Yell (name/board a horse)

    def cmd_ztats(self):                                # C: CMD_Ztats (character sheet)
        p = self.party
        self.message(f"== Party ==  Gold {p.gold}  Food {p.food // 100}")
        if not p.members:
            self.message("(no companions yet)")
            return
        for i, c in enumerate(p.members):
            self.message(f"{i + 1}. {c.name or '—'}  L{level_for_xp(c.xp)}  "
                         f"HP {c.hp}/{c.hp_max}  MP {c.mp}  [{c.status}]")
            self.message(f"   STR {c.str_}  DEX {c.dex}  INT {c.intel}  XP {c.xp}")


_DIR_WORDS = {DIR_N: "North", DIR_S: "South", DIR_E: "East", DIR_W: "West"}
