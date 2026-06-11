"""TutorAgent — in-game guide (READ).

Answers the player's questions from the live state (GameRPC) plus the knowledge base
(knowledge.quest_graph), with **progressive hinting**: a nudge at hint_level 0, the direct
answer only at higher levels. Never reaches into engine internals. v1 is rule-based.
"""
from __future__ import annotations

from ..constants import VIRTUES
from ..knowledge.quest_graph import VIRTUE_FACTS, next_objective
from .rpc import GameRPC


class TutorAgent:
    def __init__(self, game):
        self.rpc = GameRPC(game)

    def next_step(self) -> str:
        return next_objective(self.rpc.snapshot())["advice"]

    def ask(self, question: str, hint_level: int = 0) -> str:
        """hint_level 0 = gentle nudge, 1 = pointed, 2 = direct answer."""
        q = question.lower()
        snap = self.rpc.snapshot()

        # "what should I do next?"
        if "next" in q or "what" in q and "do" in q or "stuck" in q:
            obj = next_objective(snap)
            return obj["advice"] if hint_level >= 2 else obj["nudge"]

        # a specific virtue
        for v in VIRTUES:
            if v.lower() in q:
                f = VIRTUE_FACTS[v]
                karma = snap["virtues"][v]
                state = ("already an Avatar in it" if v in snap["elevated"]
                         else f"karma {karma}")
                if hint_level >= 1:
                    return (f"{v}: its shrine is in {f['town']}, mantra '{f['mantra']}'.  "
                            f"To raise it, {f['raise']}.  (Thou art {state}.)")
                return f"Seek {v} where its virtue is honored.  Reflect on how thou dost act."

        # where is a shrine / town
        if "shrine" in q or "where" in q:
            for v in VIRTUES:
                if v.lower() in q:
                    return f"The Shrine of {v} lies near {VIRTUE_FACTS[v]['town']}."
            return "Each virtue's shrine lies near the towne that embodies it."

        return "Ask me what to do next, or about a virtue or shrine."
