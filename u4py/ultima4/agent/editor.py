"""EditorAgent — natural-language edits to the live game (WRITE).

Interprets a request, runs the matching GameRPC operations, and reports what changed. v1 is
rule-based (deterministic keyword/number matching — no LLM needed) covering the common asks;
the same GameRPC surface is what an LLM-backed planner would target. All mutation goes through
GameRPC so it stays validated.
"""
from __future__ import annotations

import re

from .rpc import GameRPC, _ITEM_BITS


class EditorAgent:
    def __init__(self, game):
        self.rpc = GameRPC(game)

    def apply(self, request: str) -> str:
        r = request.lower()
        num = int(m.group()) if (m := re.search(r"\d+", r)) else None

        if "max" in r and ("stat" in r or "me" in r or "party" in r):
            self.rpc.max_stats()
            return "Maxed the party's stats (STR/DEX/INT 99, HP 800, MP 99)."
        if "heal" in r or "full health" in r:
            self.rpc.heal_party()
            return "Healed the party to full."
        if "gold" in r:
            self.rpc.set("gold", num if num is not None else 9999)
            return f"Set gold to {self.rpc.game.party.gold}."
        if "food" in r:
            self.rpc.set("food", num if num is not None else 9999)
            return f"Set food to {self.rpc.game.party.food // 100}."
        if "moongate" in r:
            x, y = self.rpc.game.party.x, self.rpc.game.party.y
            self.rpc.add_moongate(self.rpc.game.party.felucca, x, y)
            return f"Moongates of this phase now lead to ({x},{y})."
        if ("add" in r or "spawn" in r) and ("npc" in r or "person" in r or "shopkeeper" in r):
            x, y = self.rpc.game.party.x + 1, self.rpc.game.party.y
            self.rpc.add_npc(x, y, 0x52, "shopkeeper", ["I sell wares here."])
            return f"Added a shopkeeper at ({x},{y})."
        for item in _ITEM_BITS:
            if item in r and ("give" in r or "grant" in r or "add" in r):
                self.rpc.grant_item(item)
                return f"Granted the {item}."
        return "I could not interpret that edit."

    def plan(self, request: str) -> list:
        """A dry description of what apply() would do (no mutation)."""
        return [request]
