"""Quest dependency graph + per-virtue facts — the tutor's domain knowledge.

What is *true about U4* (objectives, prerequisites, how to satisfy each; virtue shrines,
mantras, and karma do's/don'ts), which the tutor combines with what's *true right now* (a
GameRPC snapshot) to compute the best next step and give grounded, non-spoilery hints.
Sourced from the manual/cluebook and the decompiled tables.
"""
from __future__ import annotations

from ..constants import VIRTUES

# shrine town, mantra, and how the virtue is raised (C: U4_LB.C lore + U4_SHRIN.C mantras).
VIRTUE_FACTS = {
    "Honesty":      {"town": "Moonglow",   "mantra": "ahm",  "raise": "never steal; don't cheat merchants"},
    "Compassion":   {"town": "Britain",    "mantra": "mu",   "raise": "give gold to beggars; spare fleeing foes"},
    "Valor":        {"town": "Jhelom",     "mantra": "ra",   "raise": "defeat evil creatures in battle"},
    "Justice":      {"town": "Yew",        "mantra": "beh",  "raise": "be honest and compassionate; take only thy due"},
    "Sacrifice":    {"town": "Minoc",      "mantra": "cah",  "raise": "give blood at healers; give to the needy"},
    "Honor":        {"town": "Trinsic",    "mantra": "summ", "raise": "complete quests; never strike first"},
    "Spirituality": {"town": "Skara Brae", "mantra": "om",   "raise": "meditate at shrines; visit Hawkwind"},
    "Humility":     {"town": "Magincia",   "mantra": "lum",  "raise": "be honest and humble; shun pride"},
}

# Objectives in dependency order. Each: (id, is_done(snapshot), nudge, direct advice).
OBJECTIVES = [
    ("recruit", lambda s: s["member_count"] >= 8,
     "A lone adventurer fares poorly.  Mightst thou find companions?",
     "Recruit a party of eight: Talk to thy fellow class-mates in the townes and ask them to Join."),
    ("virtues", lambda s: all(v >= 40 or n in s["elevated"] for n, v in s["virtues"].items()),
     "Thy soul is not yet in balance.  Reflect on thy deeds.",
     "Raise every virtue (give to beggars, spare non-evil beasts, be honest) until each karma is high."),
    ("elevate", lambda s: len(s["elevated"]) >= 8,
     "The shrines call to those who are ready.",
     "Find each Rune and Mantra, then meditate three cycles at every shrine with full karma to gain Avatarhood."),
    ("key3", lambda s: all(k in s["items"] for k in ("key_c", "key_l", "key_t")),
     "A great door will bar thy way without its key.",
     "Recover the three parts of the Key of Three Parts."),
    ("bbc", lambda s: all(k in s["items"] for k in ("bell", "book", "candle")),
     "Three sacred things open the dark place.",
     "Recover the Bell of Courage, the Book of Truth, and the Candle of Love."),
    ("abyss", lambda s: s["won"],
     "When thou art whole in virtue and bear the sacred things, the Abyss awaits.",
     "Enter the Great Stygian Abyss, descend to the Codex, and answer with the Word of Passage 'veramocor'."),
]


def next_objective(snapshot: dict) -> dict:
    """The first unmet objective, with both a nudge and a direct answer."""
    for oid, done, nudge, advice in OBJECTIVES:
        if not done(snapshot):
            return {"id": oid, "nudge": nudge, "advice": advice}
    return {"id": "complete", "nudge": "Thy quest is done!", "advice": "Thou art the Avatar!"}
