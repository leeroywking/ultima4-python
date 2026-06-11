"""Authentic character creation — the gypsy's questions (SRC-TITLE/TITLE_1.C).

The gypsy poses seven either/or moral questions pitting two virtues against each other. It is
a single-elimination bracket over the eight virtues (8 -> 4 -> 2 -> 1 = 7 questions); the
surviving virtue sets thy class, and with it thy starting stats, home towne, and the moongate
where thy quest begins. (The original's scenario text is flavour; the bracket is the mechanic.)
"""
from __future__ import annotations

from . import intro_data
from .constants import VIRTUES, MOD_OUTDOORS
from .data_tables import (CLASS_NAMES, CLASS_HOME, START_X, START_Y,
                          VIRTUE_STR_INC, VIRTUE_DEX_INC, VIRTUE_INT_INC)


def build_party(game, cls: int) -> None:
    """Set up the live party for a chosen class (C: TITLE_1.C end-of-creation)."""
    p = game.party
    c = p.chara[0]
    c.name = "Avatar"
    c.char_class = chr(cls)                 # class index stored as the class byte
    c.sex = "M"
    c.str_ = 15 + VIRTUE_STR_INC[cls] * 5   # base 15 + the class's virtue stat bias
    c.dex = 15 + VIRTUE_DEX_INC[cls] * 5
    c.intel = 15 + VIRTUE_INT_INC[cls] * 5
    c.hp = c.hp_max = 100
    c.mp = c.intel if cls in (0, 3) else 0  # mages/druids start with magic points
    c.status = "G"
    p.member_count = 1
    p.karma = [50] * 8                      # virtues all begin at 50
    p.x, p.y, p.loc = START_X[cls], START_Y[cls], 0
    game.mode = MOD_OUTDOORS


class CreationSession:
    """The gypsy's seven questions (C: TITLE_1.C). Bracket the 8 virtues down to one class."""
    def __init__(self, game):
        self.game = game
        self.done = False
        self.queue = [(0, 1), (2, 3), (4, 5), (6, 7)]   # round 1 seed pairs
        self.winners = []
        self.cur = self.queue.pop(0)
        self.prompt = "(A) or (B)?"

    def _question(self) -> str:
        # The verbatim moral dilemma for this virtue pair, from the editable intro JSON
        # (C: TITLE_1.C D_2EE6). Editing data/intro/questions.json changes what is asked.
        a, b = self.cur
        return intro_data.question_for(a, b)["text"]

    def intro(self):
        return ["The gypsy lays out her deck of virtue cards and asks...", self._question()]

    def respond(self, text):
        a, b = self.cur
        self.winners.append(a if text.strip().upper().startswith("A") else b)
        if self.queue:                                   # more matches this round
            self.cur = self.queue.pop(0)
            return [self._question()]
        if len(self.winners) > 1:                        # build the next round
            w = self.winners
            self.queue = [(w[i], w[i + 1]) for i in range(0, len(w) - 1, 2)]
            self.winners = []
            self.cur = self.queue.pop(0)
            return [self._question()]
        cls = self.winners[0]                            # champion virtue -> class
        self.done = True
        build_party(self.game, cls)
        return [f"The gypsy says: Thou art a {CLASS_NAMES[cls]}!",
                f"Thy quest begins near {CLASS_HOME[cls]}."]


def run_creation(game) -> None:
    """Begin the gypsy questionnaire as a live interaction. C: TITLE_1.C C_2E04."""
    game._begin(CreationSession(game))
