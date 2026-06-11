"""Spells (U4_SPELL.C) — cast a prepared mixture for an effect.

The 26 spells A-Z. Each must first be mixed from reagents (mixing.py); casting spends one
prepared mixture (Party.mixtures[idx]) and the caster's MP, then applies the effect. Recipe
table (D_277E) and MP costs (D_208C) are ported verbatim. v1 implements the utility spells
that work anywhere (Awaken/Cure/Heal/Resurrect/Light) fully; the rest acknowledge their cast
(combat-targeted damage is a refinement once combat-casting input is wired).
"""
from __future__ import annotations

SPELL_NAMES = (
    "Awaken", "Blink", "Cure", "Dispel", "Energy Field", "Fireball", "Gate Travel", "Heal",
    "Iceball", "Jinx", "Kill", "Light", "Magic Missile", "Negate", "Open", "Protection",
    "Quickness", "Resurrect", "Sleep", "Tremor", "Undead", "View", "Winds", "X-it", "Y-up",
    "Z-down",
)
REAGENT_NAMES = ("Sulfur Ash", "Ginseng", "Garlic", "Spider Silk",
                 "Blood Moss", "Black Pearl", "Nightshade", "Mandrake")

# Reagent bits: ash=0x80 .. mandrake=0x01 (C: 0x80 >> reagent_index), in Party.reagents order.
ASH, GINSENG, GARLIC, SILK, MOSS, PEARL, NIGHTSHADE, MANDRAKE = (0x80 >> i for i in range(8))

# Recipe per spell A-Z as a reagent bitmask (C: U4_MIX.C D_277E).
RECIPES = (
    GINSENG | GARLIC,                                   # A Awaken
    SILK | MOSS,                                        # B Blink
    GINSENG | GARLIC,                                   # C Cure
    ASH | GARLIC | PEARL,                               # D Dispel
    ASH | SILK | PEARL,                                 # E Energy Field
    ASH | PEARL,                                        # F Fireball
    ASH | PEARL | MANDRAKE,                             # G Gate Travel
    GINSENG | SILK,                                     # H Heal
    PEARL | MANDRAKE,                                   # I Iceball
    PEARL | NIGHTSHADE | MANDRAKE,                      # J Jinx
    PEARL | NIGHTSHADE,                                 # K Kill
    ASH,                                                # L Light
    ASH | PEARL,                                        # M Magic Missile
    ASH | GARLIC | MANDRAKE,                            # N Negate
    ASH | MOSS,                                         # O Open
    ASH | GINSENG | GARLIC,                             # P Protection
    ASH | GINSENG | MOSS,                               # Q Quickness
    ASH | GINSENG | GARLIC | SILK | MOSS | MANDRAKE,    # R Resurrect
    GINSENG | SILK,                                     # S Sleep
    ASH | MOSS | MANDRAKE,                              # T Tremor
    ASH | GARLIC,                                       # U Undead
    NIGHTSHADE | MANDRAKE,                              # V View
    ASH | MOSS,                                         # W Winds
    ASH | SILK | MOSS,                                  # X X-it
    SILK | MOSS,                                        # Y Y-up
    SILK | MOSS,                                        # Z Z-down
)

# MP cost per spell (C: U4_SPELL.C D_208C).
MP = (5, 15, 5, 20, 10, 15, 40, 10, 20, 30, 25, 5, 5, 20, 5, 15, 20, 45, 15, 30, 15, 15,
      10, 15, 10, 5)


def cast(game, idx: int) -> list:
    """Cast spell `idx` (0..25): spend a mixture + MP, apply the effect. C: U4_SPELL.C."""
    p = game.party
    if not (0 <= idx < 26):
        return ["No such spell."]
    caster = p.chara[0]
    if p.mixtures[idx] == 0:
        return [f"Thou hast no {SPELL_NAMES[idx]} mixture!"]
    if caster.mp < MP[idx]:
        return ["Not enough magic points!"]
    p.mixtures[idx] -= 1
    caster.mp -= MP[idx]
    return [f"{SPELL_NAMES[idx]}!"] + _effect(game, idx)


def _effect(game, idx: int) -> list:
    p = game.party
    letter = chr(ord("A") + idx)
    if letter == "A":                                   # Awaken
        woke = [c for c in p.members if c.status == "S"]
        for c in woke:
            c.status = "G"
        return ["Thy companions awaken!" if woke else "None sleep."]
    if letter == "C":                                   # Cure poison
        c = next((c for c in p.members if c.status == "P"), None)
        if c:
            c.status = "G"
            return ["Cured!"]
        return ["None are poisoned."]
    if letter == "H":                                   # Heal
        c = next((c for c in p.members if c.alive and c.hp < c.hp_max), None)
        if c:
            c.hp = min(c.hp_max, c.hp + 75)
            return ["Healed!"]
        return ["None need healing."]
    if letter == "R":                                   # Resurrect
        c = next((c for c in p.members if c.status == "D"), None)
        if c:
            c.status, c.hp = "G", c.hp_max
            return ["Thou hast resurrected a companion!"]
        return ["None are dead."]
    if letter == "L":                                   # Light
        game.torchlight = 100
        return ["The area is lit!"]
    return ["The spell takes effect."]


class CastSession:
    """'Cast which spell?' -> resolve (shares the game.feed interaction protocol)."""
    def __init__(self, game):
        self.game = game
        self.done = False
        self.prompt = "Cast which spell? (A-Z)"

    def intro(self):
        return ["Cast-"]

    def respond(self, text):
        self.done = True
        c = text.strip().upper()[:1]
        if not c.isalpha():
            return ["Nevermind."]
        return cast(self.game, ord(c) - ord("A"))


def cmd_cast(game) -> None:          # C: U4_SPELL.C CMD_Cast
    game._begin(CastSession(game))
