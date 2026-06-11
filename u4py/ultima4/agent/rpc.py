"""GameRPC — the state-query/mutate interface both agents use.

The architectural keystone: it exposes the live game as clean serializable data (for the
tutor to read) and a small set of guarded mutations + content primitives (for the editor to
write), so neither agent reaches into engine internals. The engine state is already legible
(state.Party is a dataclass; tiles/dialogue are plain data), so this is thin projection +
validated assignment.
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..constants import VIRTUES, MODE_NAMES, ST_BELL, ST_BOOK, ST_CANDLE, ST_HORN, ST_WHEEL, \
    ST_SKULL, ST_KEY_C, ST_KEY_L, ST_KEY_T
from ..lb import level_for_xp
from ..spells import REAGENT_NAMES

_ITEM_BITS = {"bell": ST_BELL, "book": ST_BOOK, "candle": ST_CANDLE, "horn": ST_HORN,
              "wheel": ST_WHEEL, "skull": ST_SKULL, "key_c": ST_KEY_C, "key_l": ST_KEY_L,
              "key_t": ST_KEY_T}


def _clamp(v, lo, hi):
    return max(lo, min(hi, int(v)))


class GameRPC:
    def __init__(self, game):
        self.game = game

    # --- READ ---------------------------------------------------------------
    def snapshot(self) -> Dict[str, Any]:
        g, p = self.game, self.game.party
        return {
            "mode": MODE_NAMES.get(g.mode, "?"),
            "position": {"x": p.x, "y": p.y, "loc": p.loc},
            "member_count": p.member_count,
            "gold": p.gold,
            "food": p.food // 100,
            "party": self.party(),
            "virtues": dict(zip(VIRTUES, p.karma)),
            "elevated": sorted(VIRTUES[i] for i in g.elevated),
            "inventory": {"torches": p.torches, "gems": p.gems, "keys": p.keys,
                          "sextants": p.sextants,
                          "reagents": dict(zip(REAGENT_NAMES, p.reagents))},
            "items": [n for n, b in _ITEM_BITS.items() if p.items & (1 << b)],
            "moons": {"trammel": p.trammel, "felucca": p.felucca},
            "won": g.won,
        }

    def party(self) -> List[Dict[str, Any]]:
        return [{"name": c.name, "class": c.char_class, "hp": c.hp, "hp_max": c.hp_max,
                 "mp": c.mp, "str": c.str_, "dex": c.dex, "int": c.intel, "xp": c.xp,
                 "level": level_for_xp(c.xp), "status": c.status}
                for c in self.game.party.members]

    def query(self, path: str) -> Any:
        node: Any = self.snapshot()
        for part in path.split("."):
            node = node[int(part)] if isinstance(node, list) else node[part]
        return node

    # --- WRITE (guarded) ----------------------------------------------------
    def set(self, path: str, value: Any) -> None:
        p = self.game.party
        parts = path.split(".")
        if path == "gold":
            p.gold = _clamp(value, 0, 9999)
        elif path == "food":
            p.food = _clamp(value, 0, 9999) * 100
        elif parts[0] == "virtues":
            p.karma[VIRTUES.index(parts[1].capitalize())] = _clamp(value, 0, 99)
        elif parts[0] == "party" and len(parts) == 3:           # party.<i>.<stat>
            c = p.chara[int(parts[1])]
            attr = {"str": "str_", "dex": "dex", "int": "intel", "hp": "hp",
                    "hp_max": "hp_max", "mp": "mp", "xp": "xp"}[parts[2]]
            setattr(c, attr, _clamp(value, 0, 9999 if attr in ("hp", "hp_max", "mp", "xp") else 99))
        else:
            raise KeyError(f"unknown or read-only path: {path}")

    # --- editor primitives --------------------------------------------------
    def max_stats(self) -> None:
        for c in self.game.party.members or self.game.party.chara[:1]:
            c.str_ = c.dex = c.intel = 99
            c.hp = c.hp_max = max(c.hp_max, 800)
            c.mp = 99

    def heal_party(self) -> None:
        for c in self.game.party.members:
            if c.status != "D":
                c.status, c.hp = "G", c.hp_max

    def grant_item(self, name: str) -> None:
        self.game.party.items |= (1 << _ITEM_BITS[name])

    def add_moongate(self, phase: int, x: int, y: int) -> None:
        from ..data_tables import MOONGATE_X, MOONGATE_Y
        MOONGATE_X[phase & 7] = x & 0xFF
        MOONGATE_Y[phase & 7] = y & 0xFF

    def add_npc(self, x: int, y: int, tile: int, name: str, lines: list) -> None:
        """Drop an NPC into the current town with inline dialogue (job/look text)."""
        from ..location import NPC
        from ..dialogue import Dialogue
        loc = self.game.location
        if loc is None:
            raise RuntimeError("not in a location")
        job = lines[0] if lines else "I dwell here."
        d = Dialogue(name=name, pronoun="They", look=f"a {name}", job=job, health="Fine.",
                     answer1="", answer2="", question="", yes="", no="", keyword1="", keyword2="",
                     question_trigger=0, humility_test=0, turn_away=0)
        loc.npcs.append(NPC(slot=31, x=x, y=y, tile=tile, gtile=tile, tlkidx=0, var=0,
                            dialogue=d))
