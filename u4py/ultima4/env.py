"""UltimaEnv — the agent-facing environment over the game.

This is the stable observe/act contract that lets an *external* agent play Ultima IV: perceive
a serializable observation, choose from the legal actions, and act. It wraps the headless
`Game` (the same engine interactive play and the demo Director use) and is transport-agnostic —
the CLI driver (tools/agent_play.py), the MCP server, and a human-watched live window all sit on
top of this one class.

Design goals:
- **Serializable observations** — everything an agent needs to decide, as plain JSON (no engine
  objects): mode, position, an ASCII view + tile legend, party/inventory, visible NPCs/monsters,
  messages since the last act, and the active interaction's prompt.
- **A small typed action vocabulary** with **`legal_actions`** computed per state — the single
  biggest quality lever for an LLM agent (it never has to guess which keys are valid here).
- **Determinism** — seeded; replaying the same action list from the same seed reproduces state,
  which the CLI driver exploits to be stateless across process invocations.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import transport
from .constants import (MODE_NAMES, MOD_OUTDOORS, MOD_BUILDING, MOD_DUNGEON, MOD_COMBAT)
from .demo import _glyph
from .game import Game
from .tiles import tile_name, is_walkable, LB_CASTLE_ENTRANCE

# Orthogonal steps and the arrow key each maps to (N=up).
_STEP_DIRS = (("UP", 0, -1), ("DOWN", 0, 1), ("RIGHT", 1, 0), ("LEFT", -1, 0))
_DIR_KEY = {"N": "UP", "S": "DOWN", "E": "RIGHT", "W": "LEFT"}
# Command words that prompt for a direction, so `act("attack E")` can do the key + direction in one
# call instead of `key A` then `move E`. (C: U4_MAIN.C CMD_* — these all ask "Dir?".)
_CMD_WORD = {"attack": "A", "talk": "T", "open": "O", "jimmy": "J",
             "get": "G", "fire": "F", "enter": "E"}


def _drive(gen):
    """Run a stepped-op generator to completion (headless — no window watching) and return its
    final value. In a windowed session the render loop drives the same generator one step per frame
    instead (so it animates); the end result is identical."""
    try:
        while True:
            next(gen)
    except StopIteration as e:
        return e.value

SCHEMA_VERSION = 1
_UNSET = object()               # sentinel for "no previous value" in compact/delta observations

# The command letters the engine's dispatch accepts, with friendly names (C: U4_MAIN.C switch).
_COMMANDS = {
    "A": "attack", "B": "board", "C": "cast", "D": "descend", "E": "enter", "F": "fire",
    "G": "get", "H": "hole-up", "I": "ignite", "J": "jimmy", "K": "klimb", "L": "locate",
    "M": "mix", "O": "open", "P": "peer", "Q": "quit", "R": "ready", "S": "search",
    "T": "talk", "U": "use", "W": "wear", "X": "x-it", "Z": "ztats",
}
# Common keyword suggestions when a Talk conversation is active (the real keyword slots; the
# per-NPC slots 5/6 vary, so these are hints, not an exhaustive list — free text is allowed).
_TALK_HINTS = ["name", "job", "health", "look", "join", "bye"]


class UltimaEnv:
    def __init__(self, seed: int = 7, game: Optional[Game] = None):
        self.seed = seed
        self.game = game or Game()
        self.game.rng.seed(seed)
        self._cursor = 0
        self.last_error: Optional[str] = None
        # Whether observe/act advance the real-time moon clock. True for headless (the env is the
        # only driver); a LiveWindow sets it False because its render loop drives the clock instead.
        self.drive_clock = True
        # "full" (default) sends the whole state each turn; "min" omits the big blocks (party,
        # gold, food, inventory, items, legal_actions) when they haven't changed since the last
        # observation — a large per-turn token saving during traversal. First obs after a reset (or
        # after switching to min) sends everything.
        self.verbosity = "full"
        self._min_prev: Dict[str, Any] = {}

    # --- lifecycle -----------------------------------------------------------
    def reset(self, seed: Optional[int] = None) -> Dict[str, Any]:
        self.seed = self.seed if seed is None else seed
        self.game = Game()
        self.game.rng.seed(self.seed)
        self._cursor = 0
        self.last_error = None
        self._min_prev = {}                          # fresh game -> next obs re-sends everything
        return self.observe()

    # --- perception ----------------------------------------------------------
    def render_ascii(self, radius: int = 4) -> List[str]:
        g = self.game
        chars = [[_glyph(t) for t in row] for row in g.viewport(radius)]
        for col, row, tile in (list(g.npc_sprites(radius)) + list(g.monster_sprites(radius))
                               + list(g.combat_sprites())):
            if 0 <= row < len(chars) and 0 <= col < len(chars[0]):
                chars[row][col] = _glyph(tile)
        if chars:
            chars[len(chars) // 2][len(chars[0]) // 2] = "@"
        return ["".join(r) for r in chars]

    def _recruitable(self, loc: int) -> bool:
        """Can the town's companion (the tlkidx==1 NPC) ever join? — the permanent class gate:
        a companion whose class == the Avatar's own class never joins (C: dialogue.py `_join`).
        (Karma/HP are situational; the reference table in AGENTS.md documents them.)"""
        vi = loc - 5
        if not (0 <= vi <= 7):
            return False
        avatar_class = ord((self.game.party.chara[0].char_class or "\x00")[:1])
        return vi != avatar_class

    def _visible(self, radius: int = 4) -> List[Dict[str, Any]]:
        g = self.game
        if g.mode == MOD_COMBAT:
            return []                                # combatants live in the `combat` block (one frame)
        if g.mode == MOD_BUILDING and g.location is not None:
            cx, cy = g.party.x, g.party.y
            try:
                talk = g._talk_data()                # the town's dialogue -> names by tlkidx
            except Exception:
                talk = None
            out = []
            for n in g.location.npcs:
                dx, dy = n.x - cx, n.y - cy
                if not (-radius <= dx <= radius and -radius <= dy <= radius):
                    continue
                entry: Dict[str, Any] = {"tile": tile_name(n.tile), "dx": dx, "dy": dy}
                d = talk.for_npc(n.tlkidx) if (talk and n.tlkidx) else None
                if d and d.name:
                    entry["name"] = d.name
                if n.tlkidx == 1:                    # the town's recruitable companion
                    entry["recruitable"] = self._recruitable(g.party.loc)
                out.append(entry)
            return out
        out = []
        for col, row, tile in (list(g.npc_sprites(radius)) + list(g.monster_sprites(radius))):
            out.append({"tile": tile_name(tile), "dx": col - radius, "dy": row - radius})
        return out

    def find_npc(self, name: str) -> Dict[str, Any]:
        """Locate an NPC by name in the current town (scans the WHOLE map, not just the view) so an
        agent can find a companion without reading .ULT/dialogue files. Returns {found, x, y, dx, dy,
        tlkidx, recruitable} or {found: False, reason}."""
        g = self.game
        if g.mode != MOD_BUILDING or g.location is None:
            return {"found": False, "reason": "not in a town"}
        try:
            talk = g._talk_data()
        except Exception:
            talk = None
        want = name.strip().lower()
        for n in g.location.npcs:
            d = talk.for_npc(n.tlkidx) if (talk and n.tlkidx) else None
            if d and d.name and d.name.lower() == want:
                return {"found": True, "name": d.name, "x": n.x, "y": n.y,
                        "dx": n.x - g.party.x, "dy": n.y - g.party.y, "tlkidx": n.tlkidx,
                        "recruitable": self._recruitable(g.party.loc) if n.tlkidx == 1 else None}
        return {"found": False, "reason": f"no NPC named {name!r} in {g.location.name}"}

    def _moons(self) -> Dict[str, Any]:
        """Moon phases + the open moongate (its position + where it sends you), for planning."""
        from . import moongate
        g, p = self.game, self.game.party
        info: Dict[str, Any] = {"trammel": p.trammel, "felucca": p.felucca, "gate": None}
        gate = moongate.open_gate(g) if g.mode == MOD_OUTDOORS else None
        if gate is not None:
            dest = moongate.gate_destination(g)
            info["gate"] = {
                "x": gate[0], "y": gate[1],
                "destination": "abyss" if dest == "abyss" else {"x": dest[0], "y": dest[1]},
                "adjacent": moongate.gate_adjacent(g),
            }
        return info

    def _combat_info(self):
        """The ONE authoritative combat frame (fixes the old confusion of three disagreeing frames):
        everything is expressed from the ACTIVE member — whose turn it is — with absolute arena
        positions too. `active.can_attack` lists the directions that hit something right now, and
        `active.nearest` points at the closest monster, so the obvious move is a one-field read:
        attack a `can_attack` direction, else `move` `active.nearest.dir`. `None` unless in combat."""
        g = self.game
        if g.mode != MOD_COMBAT or g.combat is None:
            return None
        from .combat import RANGED_WEAPONS, RANGED_REACH
        cur = g.combat.current()
        if cur is None:
            return None
        weapon = g.party.chara[cur.member].weapon if cur.member >= 0 else 0
        reach = RANGED_REACH if weapon in RANGED_WEAPONS else 1
        mons, can_attack = [], []
        for m in g.combat.monsters:
            if not m.alive:
                continue
            dx, dy = m.x - cur.x, m.y - cur.y
            if dx == 0 and dy != 0:
                direction = "S" if dy > 0 else "N"
            elif dy == 0 and dx != 0:
                direction = "E" if dx > 0 else "W"
            else:
                direction = None                     # diagonal — not directly attackable
            dist = max(abs(dx), abs(dy))
            in_range = direction is not None and 1 <= dist <= reach
            if in_range and direction not in can_attack:
                can_attack.append(direction)
            mons.append({"tile": tile_name(m.tile), "pos": {"x": m.x, "y": m.y},
                         "dx": dx, "dy": dy, "dist": dist, "direction": direction, "in_range": in_range})
        # nearest monster (Chebyshev), and the step toward it (may be diagonal -> pick the longer axis)
        nearest = min(mons, key=lambda e: e["dist"], default=None)
        step = None
        if nearest is not None:
            ndx, ndy = nearest["dx"], nearest["dy"]
            step = (("E" if ndx > 0 else "W") if abs(ndx) >= abs(ndy) else ("S" if ndy > 0 else "N"))
        active = {
            "member": cur.member, "pos": {"x": cur.x, "y": cur.y}, "reach": reach,
            "can_attack": can_attack,               # attack these directions to hit now
            "nearest": None if nearest is None else {
                "dir": nearest["direction"], "step": step, "dist": nearest["dist"],
                "in_range": nearest["in_range"], "tile": nearest["tile"]},
        }
        return {"active": active, "monsters": mons}

    def observe(self, radius: int = 4) -> Dict[str, Any]:
        from .agent.rpc import GameRPC
        if self.drive_clock:
            self.game.catch_up_moons()               # real-time moons advance to 'now' (headless)
        g, p = self.game, self.game.party
        snap = GameRPC(g).snapshot()
        new_msgs = [m for m in g.messages[self._cursor:] if m != ""]
        self._cursor = len(g.messages)
        loc = None
        if g.mode == MOD_BUILDING and g.location is not None:
            loc = g.location.name
        elif g.mode == MOD_DUNGEON and g.dungeon is not None:
            loc = f"dungeon z={g.dungeon.z}"
        d = {
            "schema": SCHEMA_VERSION,
            "mode": MODE_NAMES.get(g.mode, "?"),
            "moves": p.moves,
            "position": {"x": p.x, "y": p.y},
            "location": loc,
            "standing_on": tile_name(g.world.tile_at(p.x, p.y)) if g.mode == MOD_OUTDOORS else None,
            "view_ascii": self.render_ascii(radius),
            "party": snap["party"],
            "gold": snap["gold"], "food": snap["food"],
            "inventory": snap["inventory"], "items": snap["items"],
            "visible": self._visible(radius),
            "moons": self._moons(),
            "combat": self._combat_info(),
            "messages": new_msgs,
            "interaction": {"active": g.active is not None,
                            "prompt": getattr(g.active, "prompt", None) if g.active else None},
            "won": g.won,
            "legal_actions": self.legal_actions(),
            "error": self.last_error,
        }
        if d["combat"] is None:
            del d["combat"]                          # only present in combat
        return self._compact(d)

    # --- token-saving: drop big blocks that haven't changed since the last observation ------
    _MIN_DROPPABLE = ("party", "gold", "food", "inventory", "items", "legal_actions")

    def _compact(self, d: Dict[str, Any]) -> Dict[str, Any]:
        """When `verbosity == 'min'`, omit the large state blocks that are unchanged since the last
        observation (they dominate the per-turn token cost during traversal but rarely change).
        Omitted == unchanged from a previous full observation. Always kept: position/mode/messages/
        moons/combat/travel_reason/etc. `verbosity == 'full'` (default) returns everything."""
        if self.verbosity != "min":
            return d
        for k in self._MIN_DROPPABLE:
            if k in d and d[k] == self._min_prev.get(k, _UNSET):
                del d[k]                             # unchanged -> drop
            elif k in d:
                self._min_prev[k] = d[k]             # changed -> emit and remember
        if d.get("mode") == "combat":                # in combat the `combat` block is authoritative:
            d.pop("view_ascii", None)                #   the map picture + moons are dead weight,
            d.pop("moons", None)                     #   drop them from the highest-frequency call
        return d

    # --- legal actions (per-state) -------------------------------------------
    def legal_actions(self) -> List[str]:
        g = self.game
        if g.active is not None:                         # a Talk/shop interaction owns input
            return [f"say {h}" for h in _TALK_HINTS] + ["say <text>"]
        if g.pending_dir is not None:                    # a command is asking "which direction?"
            return ["move N", "move S", "move E", "move W"]
        if g.mode == MOD_COMBAT:
            # one-shot forms: `attack <dir>` (or bare `attack` = nearest in-range) + moves toward foes
            return ["attack", "attack N", "attack S", "attack E", "attack W",
                    "move N", "move S", "move E", "move W", "pass"]
        if g.mode == MOD_DUNGEON:
            return ["move N (advance)", "move S (retreat)", "move E (turn right)",
                    "move W (turn left)", "key K", "key D", "key X", "key C", "key Z"]
        moves = ["move N", "move S", "move E", "move W", "pass"]
        # `go x y` walks a whole path in one call (overworld + towns) — far cheaper than one
        # observe round-trip per step across open terrain.
        travel = ["go <x> <y>"] if g.mode in (MOD_OUTDOORS, MOD_BUILDING) else []
        # Time primitives: the moons run on a real-time clock, so `wait` lets it advance without
        # moving (e.g. to catch a moongate). Only meaningful on the overworld.
        waits = (["wait <seconds>", "wait until moongate", "wait until moons_dark"]
                 if g.mode == MOD_OUTDOORS else [])
        return moves + travel + waits + [f"key {k}" for k in _COMMANDS]  # full command set outdoors / in towns

    # --- action --------------------------------------------------------------
    def act(self, action: str) -> Dict[str, Any]:
        """Apply one action (string form: 'move N' | 'key T' | 'say health' | 'pass'), observe."""
        self.last_error = None
        verb, _, rest = action.strip().partition(" ")
        verb = verb.lower()
        # `wait` is a time primitive, not a move: "wait 20" (seconds) or "wait until <cond>".
        if verb == "wait":
            arg = rest.strip()
            if arg.lower().startswith("until"):
                return self.wait_until(arg[len("until"):].strip())
            try:
                return self.wait(float(arg))
            except ValueError:
                self.last_error = f"wait needs seconds or 'until <cond>', got {arg!r}"
                return self.observe()
        # `go`/`travel x y` walks a whole path in one call (stops on anything interesting).
        if verb in ("go", "travel"):
            parts = rest.split()
            try:
                return self.travel_to(int(parts[0]), int(parts[1]))
            except (IndexError, ValueError):
                self.last_error = f"{verb} needs 'x y' coordinates, got {rest!r}"
                return self.observe()
        # One-shot directional command: "attack E" / "talk N" / "open W" / "key A E" runs the command
        # key AND its direction in one call. "attack" with no direction hits the nearest in-range foe.
        letter, dir_arg = None, None
        if verb == "key":
            parts = rest.split()
            letter = parts[0][:1].upper() if parts else ""
            dir_arg = parts[1] if len(parts) > 1 else None
        elif verb in _CMD_WORD:
            letter, dir_arg = _CMD_WORD[verb], (rest.strip() or None)
        if letter:
            try:
                self.game.handle(letter)
            except (KeyError, IndexError):
                self.last_error = f"malformed action {action!r}"
                return self.observe()
            if self.game.pending_dir is not None:        # the command is asking "which direction?"
                d = (dir_arg or "").strip().upper()[:1]
                if not d and verb == "attack":           # "attack" alone -> nearest in-range monster
                    ci = self._combat_info()
                    ca = ci["active"]["can_attack"] if ci else []
                    d = ca[0] if ca else ""
                if d in _DIR_KEY:
                    self.game.handle(_DIR_KEY[d])
            return self.observe()
        try:
            if verb == "move":
                d = rest.strip().upper()[:1]
                self.game.handle(_DIR_KEY[d])
            elif verb in ("say", "feed"):
                if self.game.active is None:
                    self.last_error = "no active interaction to 'say' into"
                else:
                    self.game.feed(rest)
            elif verb == "pass":
                self.game.handle("SPACE")
            else:
                self.last_error = f"unknown action {action!r}"
        except (KeyError, IndexError):
            self.last_error = f"malformed action {action!r}"
        return self.observe()

    # --- time primitives (the moons run on a real-time clock; moves don't touch it) ----------
    def wait(self, seconds: float) -> Dict[str, Any]:
        """Let `seconds` of real game-time pass on the moon clock, then observe. Moves are
        unaffected — this is how a turn-based agent lets the real-time moons advance (e.g. to
        wait for a moongate to cycle into reach). Animates the moon glide in a window."""
        return _drive(self.wait_steps(seconds))

    def wait_steps(self, seconds: float):
        """Generator form of `wait`: advances the clock in bounded chunks, yielding each, so a
        window animates the moon glide in a few seconds of wall-time regardless of how long is
        waited; returns the final observation."""
        self.last_error = None
        try:
            secs = max(0.0, float(seconds))
        except (TypeError, ValueError):
            self.last_error = f"wait: seconds must be a number, got {seconds!r}"
            return self.observe()
        self.game.catch_up_moons()                       # fold in any elapsed wall time first
        chunks = 24                                      # ~a few seconds of animation at any wait size
        if secs > 0:
            step = secs / chunks
            for _ in range(chunks):
                self.game.advance_moon_seconds(step)
                yield
        return self.observe()

    def wait_until(self, condition: str, max_seconds: float = 600.0) -> Dict[str, Any]:
        """Advance the moon clock until `condition` holds (or `max_seconds` of game-time elapse),
        then observe. Conditions: 'moongate' (open gate on/adjacent — stops at its FIRST destination),
        'moongate <x> <y>' (until the open gate leads to that exact destination — for directed travel,
        since each gate reaches 3), 'moons_dark', 'trammel N', 'felucca N'. Adds `wait_reason` +
        `waited_seconds`; a timed-out targeted wait also lists `reachable_destinations`. Animates in a
        window."""
        return _drive(self.wait_until_steps(condition, max_seconds))

    def wait_until_steps(self, condition: str, max_seconds: float = 600.0):
        """Generator form of `wait_until`: yields as it advances (up to an animation budget, then
        fast-forwards the rest); returns the final observation."""
        self.last_error = None
        from . import moongate
        g, p = self.game, self.game.party
        cond = condition.strip().lower()
        parts = cond.split()
        # `moongate` (any open gate) OR `moongate <x> <y>` (advance until the open gate leads to a
        # SPECIFIC destination — each gate reaches 3, and the useful ones aren't the first-caught one).
        target_dest = None
        if cond.startswith("moongate") and len(parts) >= 3:
            try:
                target_dest = (int(parts[1]) & 0xFF, int(parts[2]) & 0xFF)
            except ValueError:
                self.last_error = f"wait_until: 'moongate x y' needs integer coords, got {condition!r}"
                return self.observe()

        def holds():
            if cond.startswith("moongate"):
                if not moongate.gate_adjacent(g):
                    return False
                return target_dest is None or moongate.gate_destination(g) == target_dest
            if cond == "moons_dark":
                return (p.trammel | p.felucca) == 0
            if cond.startswith("trammel"):
                return p.trammel == int(parts[1])
            if cond.startswith("felucca"):
                return p.felucca == int(parts[1])
            return None

        self.game.catch_up_moons()
        try:
            if holds() is None:
                self.last_error = f"unknown wait_until condition {condition!r}"
                return self.observe()
        except (IndexError, ValueError):
            self.last_error = f"wait_until: bad condition {condition!r} (want 'trammel N'/'felucca N')"
            return self.observe()
        if g.mode != MOD_OUTDOORS:
            obs = self.observe()
            obs["wait_reason"] = "not on the overworld (the moons only run outdoors)"
            obs["waited_seconds"] = 0.0
            return obs

        waited, reason, animated, anim_budget = 0.0, "condition met", 0, 40
        seen_dests = set()                           # destinations offered while the gate was open
        while not holds():
            if moongate.gate_adjacent(g):
                d = moongate.gate_destination(g)
                if isinstance(d, tuple):
                    seen_dests.add(d)
            if waited >= max_seconds:
                reason = f"timeout after {int(max_seconds)}s of game-time"
                break
            self.game.advance_moon_seconds(0.25)
            waited += 0.25
            if animated < anim_budget:               # animate the glide, then fast-forward the rest
                animated += 1
                yield
        obs = self.observe()
        obs["wait_reason"] = reason
        obs["waited_seconds"] = round(waited, 2)
        if target_dest is not None and reason.startswith("timeout"):
            # help the agent: which destinations THIS gate site actually reaches (it wasn't the ask).
            obs["reachable_destinations"] = [{"x": x, "y": y} for x, y in sorted(seen_dests)]
        return obs

    def play_steps(self, actions: List[str]):
        """Generator form of `play`: apply each action, yielding after each so a window animates the
        sequence; returns the observation after the last action."""
        last = None
        for a in actions:
            last = self.act(a)
            yield
        return last if last is not None else self.observe()

    # --- traversal (walk a path in ONE call, stopping on anything interesting) ---------------
    def _walkable(self, x: int, y: int) -> bool:
        """Can the party step onto (x, y) right now, given its transport (C: _move_overworld /
        _move_building rules)?"""
        g = self.game
        if g.mode == MOD_OUTDOORS:
            t = g.world.tile_at(x & 0xFF, y & 0xFF)
            return t == LB_CASTLE_ENTRANCE or transport.can_move_onto(g.party.tile, t)
        t = g.location.tile_at(x, y)               # town/castle interior
        return t is not None and is_walkable(t) and g.location.npc_at(x, y) is None

    def _bfs_path(self, tx: int, ty: int, max_nodes: int = 40000):
        """Shortest 4-neighbour path (list of (x,y) after the start) from the party to (tx,ty),
        honouring walkability for the current transport. If (tx,ty) itself isn't walkable, aim for
        a tile adjacent to it. Returns None if unreachable within `max_nodes` explored."""
        from collections import deque
        g = self.game
        outdoors = g.mode == MOD_OUTDOORS
        wrap = (lambda v: v & 0xFF) if outdoors else (lambda v: v)
        goal = (wrap(tx), wrap(ty))
        goal_walkable = self._walkable(*goal)
        start = (g.party.x, g.party.y)

        def neighbours(p):
            for _, dx, dy in _STEP_DIRS:
                yield (wrap(p[0] + dx), wrap(p[1] + dy))

        def is_goal(p):
            return p == goal or (not goal_walkable and goal in set(neighbours(p)))

        prev = {start: None}
        q = deque([start])
        nodes = 0
        while q and nodes < max_nodes:
            cur = q.popleft()
            nodes += 1
            if is_goal(cur):
                path = []
                while cur is not None and prev[cur] is not None:
                    path.append(cur)
                    cur = prev[cur]
                path.reverse()
                return path
            for nb in neighbours(cur):
                if nb not in prev and self._walkable(*nb):
                    prev[nb] = cur
                    q.append(nb)
        return None

    def _dir_key(self, a, b) -> str:
        outdoors = self.game.mode == MOD_OUTDOORS
        dx, dy = b[0] - a[0], b[1] - a[1]
        if outdoors:                                # normalise wrap-around to -1/0/+1
            dx = ((dx + 128) & 0xFF) - 128
            dy = ((dy + 128) & 0xFF) - 128
        for key, sdx, sdy in _STEP_DIRS:
            if (dx, dy) == (sdx, sdy):
                return key
        return "UP"                                 # unreachable; BFS only yields 4-neighbours

    def travel_to(self, x: int, y: int, max_steps: int = 100) -> Dict[str, Any]:
        """Walk toward (x, y) over multiple turns in ONE call, so an agent doesn't spend a round-trip
        per step crossing open terrain. Paths around obstacles (BFS honouring the party's transport)
        and takes real turns (food drains, monsters roam). STOPS early — returning the observation
        plus `travel_reason` and `steps_taken` — on: arrival (or adjacent, if the target tile isn't
        walkable), combat/entering a location, a dialog opening, taking damage, a genuine block, or
        `max_steps`. Overworld and town only (not dungeons). Animates step-by-step in a window."""
        return _drive(self.travel_steps(x, y, max_steps))

    def travel_steps(self, x: int, y: int, max_steps: int = 100):
        """Generator form of `travel_to`: yields after each step so a window can animate the walk;
        returns the final observation. See `travel_to` for behaviour."""
        self.last_error = None
        g = self.game
        if g.mode not in (MOD_OUTDOORS, MOD_BUILDING):
            obs = self.observe()
            obs["travel_reason"] = "travel only works on the overworld or in a town"
            obs["steps_taken"] = 0
            return obs
        base_mode = g.mode
        wrap = (lambda v: v & 0xFF) if base_mode == MOD_OUTDOORS else (lambda v: v)
        goal = (wrap(x), wrap(y))
        path = self._bfs_path(x, y)                  # None = unreachable; [] = already there
        if path is None:
            obs = self.observe()
            obs["travel_reason"] = "no_path"
            obs["steps_taken"] = 0
            return obs

        hp0 = sum(c.hp for c in g.party.members)
        steps, stuck, recomputed, reason = 0, 0, False, "arrived"
        cur = (g.party.x, g.party.y)
        i = 0
        while i < len(path):
            if steps >= max_steps:
                reason = "max_steps"
                break
            before = (g.party.x, g.party.y)
            g.handle(self._dir_key(cur, path[i]))
            steps += 1
            yield                                   # animate: let the render loop draw this step
            if g.mode != base_mode:                 # combat started / entered/left a map
                reason = f"interrupted: now {MODE_NAMES.get(g.mode, '?')}"
                break
            if g.active is not None:                # a dialog/shop opened
                reason = "interaction opened"
                break
            if sum(c.hp for c in g.party.members) < hp0:
                reason = "took damage"
                break
            pos = (g.party.x, g.party.y)
            if pos == before:                       # blocked or rough-terrain ate the move
                stuck += 1
                if stuck >= 3:
                    if not recomputed:              # an NPC may have drifted onto the path — retry
                        recomputed = True
                        new = self._bfs_path(x, y)
                        if new:
                            path, i, cur, stuck = new, 0, pos, 0
                            continue
                    reason = "blocked"
                    break
                continue                            # retry the same step
            stuck, cur, i = 0, pos, i + 1
            if pos == goal:
                reason = "arrived"
                break
        obs = self.observe()
        obs["travel_reason"] = reason
        obs["steps_taken"] = steps
        return obs

    def play(self, actions: List[str]) -> List[Dict[str, Any]]:
        """Apply a sequence of actions, returning the observation after each (for replay)."""
        return [self.act(a) for a in actions]
