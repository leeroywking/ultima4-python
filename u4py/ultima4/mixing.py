"""Reagent mixing (U4_MIX.C CMD_Mix) — prepare spell charges.

Choose a spell, add reagents one at a time, then finish: if the reagents added exactly match
that spell's recipe (spells.RECIPES) you gain one castable mixture (Party.mixtures[idx], cap
99); otherwise it fizzles. Either way the reagents are spent (C: decremented as added).
"""
from __future__ import annotations

from .spells import RECIPES, REAGENT_NAMES, SPELL_NAMES


class MixSession:
    """Interactive mix: pick a spell, add reagents A-H, 'mix' to finish."""
    def __init__(self, game):
        self.game = game
        self.done = False
        self.spell = None
        self.mask = 0
        self.prompt = "Mix for which spell? (A-Z)"

    def intro(self):
        return ["Mix Reagents"]

    def respond(self, text):
        c = text.strip().upper()
        if self.spell is None:
            if not c[:1].isalpha():
                self.done = True
                return ["Nevermind."]
            self.spell = ord(c[:1]) - ord("A")
            self.prompt = "Add a reagent (A-H), or 'mix' to finish"
            return [f"Mixing for {SPELL_NAMES[self.spell % 26]}..."]
        if c in ("", "MIX", "DONE"):
            return self._finish()
        ri = ord(c[:1]) - ord("A")
        if not (0 <= ri < 8):
            return ["No such reagent."]
        if self.game.party.reagents[ri] == 0:
            return [f"Thou hast no {REAGENT_NAMES[ri]}!"]
        self.game.party.reagents[ri] -= 1            # spent as added (C: U4_MIX.C)
        self.mask |= (0x80 >> ri)
        return [f"Added {REAGENT_NAMES[ri]}."]

    def _finish(self):
        self.done = True
        if self.mask == 0:
            return ["Nothing mixed!"]
        if 0 <= self.spell < 26 and RECIPES[self.spell] == self.mask:
            m = self.game.party.mixtures
            m[self.spell] = min(99, m[self.spell] + 1)
            return ["You mix the reagents, and... Success!"]
        return ["You mix the reagents, and... It fizzles!"]


def cmd_mix(game) -> None:          # C: U4_MIX.C CMD_Mix
    game._begin(MixSession(game))
