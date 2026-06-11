"""Shrines & meditation (U4_SHRIN.C) + the Seer Hawkwind (U4_SHOPS.C SHP_hawkwind).

Each virtue has a shrine. Entry requires that virtue's Rune (Party.runes bitmask). Inside you
speak the virtue's Mantra and meditate; with full karma (99) three cycles grant partial
Avatarhood (karma resets to 0 and the virtue is marked elevated), otherwise you gain a vision
and Spirituality. A wrong mantra costs Spirituality. Hawkwind, in Lord British's castle, reads
your karma and counsels you toward Elevation.
"""
from __future__ import annotations

from .constants import VIRTUES        # 8 virtues, karma-array order

# C: U4_SHRIN.C mantra table, one per virtue (VIRTUES order).
MANTRAS = ("ahm", "mu", "ra", "beh", "cah", "summ", "om", "lum")
SPIRITUALITY = 6                       # VIRTUES index of Spirituality


class ShrineSession:
    """Meditate at a virtue's shrine. C: U4_SHRIN.C C_E6xx."""
    def __init__(self, game, virtue: int):
        self.game = game
        self.v = virtue
        self.done = False
        self.prompt = "Mantra?"

    def intro(self):
        return [f"You enter the ancient Shrine of {VIRTUES[self.v]} and sit before the altar.",
                "Speak the Mantra:"]

    def respond(self, text):
        self.done = True
        p = self.game.party
        if text.strip().lower() != MANTRAS[self.v]:
            p.karma[SPIRITUALITY] = max(0, p.karma[SPIRITUALITY] - 3)
            return ["Thou art not able to focus thy thoughts with that Mantra!"]
        if p.karma[self.v] == 99:                          # C: 3 cycles + karma 99 -> elevation
            p.karma[self.v] = 0
            self.game.elevated.add(self.v)
            return [f"Thou hast achieved partial Avatarhood in the Virtue of {VIRTUES[self.v]}!"]
        p.karma[SPIRITUALITY] = min(99, p.karma[SPIRITUALITY] + 9)
        return ["Thy thoughts are pure.  Thou art granted a vision!"]


def enter_shrine(game, virtue: int) -> None:
    """C: U4_SHRIN.C — require the rune of entry, then meditate."""
    if not (game.party.runes & (1 << virtue)):
        game.message("Thou dost not bear the rune of entry!  A strange force keeps thee out!")
        return
    game._begin(ShrineSession(game, virtue))


class HawkwindSession:
    """The Seer Hawkwind (C: SHP_hawkwind) — counsel on a virtue from thy karma."""
    def __init__(self, game):
        self.game = game
        self.done = False
        self.prompt = "Of which virtue? (or 'bye')"

    def intro(self):
        return ["I am Hawkwind, Seer of Souls.  I see that which is within thee.",
                "Of which virtue dost thou seek counsel?"]

    def respond(self, text):
        t = text.strip().lower()
        if t in ("", "bye"):
            self.done = True
            return ["Hawkwind says: Fare thee well, and may thou complete the Quest!"]
        vi = next((i for i, v in enumerate(VIRTUES) if v.lower().startswith(t[:4])), None)
        if vi is None:
            return ["Hawkwind knows not that path."]
        k = self.game.party.karma[vi]
        if vi in self.game.elevated:
            return [f"Thou hast already achieved Avatarhood in {VIRTUES[vi]}!"]
        if k == 99:
            return ["Thou art ready!  Seek the Elevation at the shrine of this virtue."]
        if k >= 70:
            return ["Thou hast nearly mastered this virtue.  Press on!"]
        if k >= 40:
            return ["Thou art progressing well in this virtue."]
        return ["Thou hast much to learn of this virtue.  Take care in thy deeds."]


def hawkwind(game) -> None:
    game._begin(HawkwindSession(game))
