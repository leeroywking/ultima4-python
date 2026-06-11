"""Endgame — the Abyss & the Codex (U4_END.C / U4_Q_N_V.C).

The win condition. At the bottom of the Great Stygian Abyss you reach the Chamber of the
Codex. Entry demands the Key of Three Parts, a party of eight, and partial Avatarhood in all
eight virtues (every karma elevated). A voice asks the Word of Passage ("veramocor"); then,
after the virtue/principle questions, the final riddle — the one thing that is the whole of
all Truth, Love and Courage — whose answer is "infinity". Answer it and the Quest is won.
"""
from __future__ import annotations

from .constants import ST_KEY_C, ST_KEY_L, ST_KEY_T

WORD_OF_PASSAGE = "veramocor"
CODEX_ANSWER = "infinity"


def _has(party, bit: int) -> bool:
    return bool(party.items & (1 << bit))


def abyss_requirements(game) -> list:
    """Unmet requirements for the Codex chamber (empty list = ready). C: U4_END.C checks."""
    p = game.party
    missing = []
    if not all(_has(p, b) for b in (ST_KEY_C, ST_KEY_L, ST_KEY_T)):
        missing.append("the Key of Three Parts")
    if p.member_count < 8:
        missing.append("a party of eight")
    if len(game.elevated) < 8:
        missing.append("Avatarhood in all eight virtues")
    return missing


def can_enter_abyss(game) -> bool:
    return not abyss_requirements(game)


class CodexSession:
    """The Codex chamber Q&A (C: U4_END.C). Assumes requirements are already met."""
    def __init__(self, game):
        self.game = game
        self.done = False
        self.stage = "word"
        self.prompt = "The Word of Passage?"

    def intro(self):
        return ["You enter the Chamber of the Codex of Ultimate Wisdom.",
                "A voice rings out: What is the Word of Passage?"]

    def respond(self, text):
        t = text.strip().lower()
        if self.stage == "word":
            if t != WORD_OF_PASSAGE:
                self.done = True
                return ["The voice: Thy quest is not yet complete."]
            self.stage = "codex"
            self.prompt = "...what is the one thing?"
            return ["Passage is granted.",
                    "The voice asks: what is the one thing which is the whole of all "
                    "Truth, Love and Courage?"]
        self.done = True
        if t == CODEX_ANSWER:
            self.game.won = True
            return ["The boundless knowledge of the Codex is revealed unto thee!",
                    "Thou hast completed the Quest of the Avatar!", "*** THE END ***"]
        return ["The voice: Thy thoughts are not pure."]


def enter_codex(game) -> None:
    """Reach the Codex chamber (bottom of the Abyss). C: U4_END.C."""
    missing = abyss_requirements(game)
    if missing:
        game.message("There is a sudden darkness; thou art in an empty chamber.  "
                     "Thou lackest " + ", ".join(missing) + ".")
        return
    game._begin(CodexSession(game))
