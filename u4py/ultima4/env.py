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

from .constants import (MODE_NAMES, MOD_OUTDOORS, MOD_BUILDING, MOD_DUNGEON, MOD_COMBAT)
from .demo import _glyph
from .game import Game
from .tiles import tile_name

SCHEMA_VERSION = 1

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

    # --- lifecycle -----------------------------------------------------------
    def reset(self, seed: Optional[int] = None) -> Dict[str, Any]:
        self.seed = self.seed if seed is None else seed
        self.game = Game()
        self.game.rng.seed(self.seed)
        self._cursor = 0
        self.last_error = None
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

    def _visible(self, radius: int = 4) -> List[Dict[str, Any]]:
        g = self.game
        out = []
        for col, row, tile in (list(g.npc_sprites(radius)) + list(g.monster_sprites(radius))
                               + list(g.combat_sprites())):
            out.append({"tile": tile_name(tile), "dx": col - radius, "dy": row - radius})
        return out

    def observe(self, radius: int = 4) -> Dict[str, Any]:
        from .agent.rpc import GameRPC
        g, p = self.game, self.game.party
        snap = GameRPC(g).snapshot()
        new_msgs = [m for m in g.messages[self._cursor:] if m != ""]
        self._cursor = len(g.messages)
        loc = None
        if g.mode == MOD_BUILDING and g.location is not None:
            loc = g.location.name
        elif g.mode == MOD_DUNGEON and g.dungeon is not None:
            loc = f"dungeon z={g.dungeon.z}"
        return {
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
            "messages": new_msgs,
            "interaction": {"active": g.active is not None,
                            "prompt": getattr(g.active, "prompt", None) if g.active else None},
            "won": g.won,
            "legal_actions": self.legal_actions(),
            "error": self.last_error,
        }

    # --- legal actions (per-state) -------------------------------------------
    def legal_actions(self) -> List[str]:
        g = self.game
        if g.active is not None:                         # a Talk/shop interaction owns input
            return [f"say {h}" for h in _TALK_HINTS] + ["say <text>"]
        if g.pending_dir is not None:                    # a command is asking "which direction?"
            return ["move N", "move S", "move E", "move W"]
        if g.mode == MOD_COMBAT:
            return ["move N", "move S", "move E", "move W", "key A", "pass"]
        if g.mode == MOD_DUNGEON:
            return ["move N (advance)", "move S (retreat)", "move E (turn right)",
                    "move W (turn left)", "key K", "key D", "key X", "key C", "key Z"]
        moves = ["move N", "move S", "move E", "move W", "pass"]
        return moves + [f"key {k}" for k in _COMMANDS]   # full command set outdoors / in towns

    # --- action --------------------------------------------------------------
    def act(self, action: str) -> Dict[str, Any]:
        """Apply one action (string form: 'move N' | 'key T' | 'say health' | 'pass'), observe."""
        self.last_error = None
        verb, _, rest = action.strip().partition(" ")
        verb = verb.lower()
        try:
            if verb == "move":
                d = rest.strip().upper()[:1]
                self.game.handle({"N": "UP", "S": "DOWN", "E": "RIGHT", "W": "LEFT"}[d])
            elif verb == "key":
                self.game.handle(rest.strip()[:1].upper())
            elif verb in ("say", "feed"):
                if self.game.active is None:
                    self.last_error = "no active interaction to 'say' into"
                else:
                    self.game.feed(rest)
            elif verb in ("pass", "wait"):
                self.game.handle("SPACE")
            else:
                self.last_error = f"unknown action {action!r}"
        except (KeyError, IndexError):
            self.last_error = f"malformed action {action!r}"
        return self.observe()

    def play(self, actions: List[str]) -> List[Dict[str, Any]]:
        """Apply a sequence of actions, returning the observation after each (for replay)."""
        return [self.act(a) for a in actions]
