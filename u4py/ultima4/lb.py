"""Lord British (U4_LB.C) — the throne-room audience.

Talking to the Lord British NPC (tile 0x5E) in his castle does three gameplay-critical
things beyond dialogue: on the first visit he records that you've met him; on return
visits he resurrects a dead Avatar, heals nothing by default but **levels up** any party
member whose experience has outgrown their max HP (raising HP to level*100 and boosting
STR/DEX/INT), and answers "health" by offering to fully heal the party. He also answers a
big list of lore keywords and a context-sensitive "help" hint.

Ported faithfully from U4_LB.C (C_E59B/C_E4C3/C_E408/C_E442/C_E21E). The lore answers are
plain data (LB_RESPONSES) — Phase-3 fodder, editable as text.
"""
from __future__ import annotations

from typing import List

# Lore keyword -> Lord British's answer (C: D_6FF0 keywords / D_7028 texts).
LB_RESPONSES = {
    "name": "He says: My name is Lord British, Sovereign of all Britannia!",
    "look": "Thou see the King with the Royal Sceptre.",
    "job": "He says: I rule all Britannia, and shall do my best to help thee!",
    "truth": "He says: Many truths can be learned at the Lycaeum, on the northwestern shore of Verity Isle!",
    "love": "He says: Look for the meaning of Love at Empath Abbey, on the western edge of the Deep Forest!",
    "courage": "He says: Serpent's Castle on the Isle of Deeds is where Courage should be sought!",
    "honesty": "He says: The fair towne of Moonglow on Verity Isle is where the virtue of Honesty thrives!",
    "compassion": "He says: The bards in the towne of Britain are well versed in the virtue of Compassion!",
    "valor": "He says: Many valiant fighters come from Jhelom in the Valarian Isles!",
    "justice": "He says: In the city of Yew, in the Deep Forest, Justice is served!",
    "sacrifice": "He says: Minoc, towne of self-sacrifice, lies on the eastern shores of Lost Hope Bay!",
    "honor": "He says: The Paladins who strive for Honor are oft seen in Trinsic, north of the Cape of Heroes!",
    "spirituality": "He says: In Skara Brae the Spiritual path is taught.  Find it on an isle near Spiritwood!",
    "humility": "He says: Humility is the foundation of Virtue!  The ruins of proud Magincia are a "
                "testimony unto the Virtue of Humility, far off the shores of Britannia!",
    "pride": "He says: Of the combinations of Truth, Love and Courage, that which contains none of "
             "them is Pride.  Pride must be shunned in favor of Humility, its antithesis!",
    "avatar": "Lord British says: To be an Avatar is to be the embodiment of the Eight Virtues, to "
              "live forever in the Quest to better thyself and the world in which we live.",
    "quest": "Lord British says: The Quest of the Avatar is to become the embodiment of the Eight "
             "Virtues, proven by conquering the Abyss and Viewing the Codex of Ultimate Wisdom!",
    "britannia": "He says: Though the Great Evil Lords are routed, evil yet remains.  If but one soul "
                 "could complete the Quest of the Avatar, our people would have new hope!",
    "ankh": "He says: The Ankh is the symbol of one who strives for Virtue.  Keep it with thee always, "
            "for by this mark thou shalt be known!",
    "abyss": "He says: The Great Stygian Abyss is the darkest pocket of evil in Britannia!  In its "
             "deepest recesses is the Chamber of the Codex, which only an Avatar may enter!",
    "mondain": "He says: Mondain is dead!",
    "minax": "He says: Minax is dead!",
    "exodus": "He says: Exodus is dead!",
    "virtue": "He says: The Eight Virtues of the Avatar are: Honesty, Compassion, Valor, Justice, "
              "Sacrifice, Honor, Spirituality, and Humility!",
}


def level_for_xp(xp: int) -> int:
    """C: C_E4C3 inner loop — level whose HP target (level*100) just exceeds XP."""
    target, bar = 100, 100
    while bar <= xp:
        target += 100
        bar <<= 1
    return target // 100


class LordBritish:
    """An audience with Lord British — same interaction protocol as Conversation/shops."""

    def __init__(self, game):
        self.game = game
        self.party = game.party
        self.done = False
        self.prompt = "Say:"
        self._await_health = False

    # --- mechanics ----------------------------------------------------------
    def _heal_party(self) -> None:                       # C: C_E408
        for c in self.party.members:
            if c.status != "D":
                c.status = "G"
                c.hp = c.hp_max

    def _level_up(self) -> List[str]:                    # C: C_E4C3
        lines = []
        for c in self.party.members:
            target = level_for_xp(c.xp) * 100
            if c.hp_max < target:
                c.hp_max = c.hp = target
                c.status = "G"
                for attr in ("str_", "dex", "intel"):
                    setattr(c, attr, min(50, getattr(c, attr) + self.game.rng.randint(1, 8)))
                lines.append(f"{c.name}\nThou art now Level {target // 100}!")
        return lines

    # --- session ------------------------------------------------------------
    def intro(self) -> List[str]:
        p = self.party
        name = (p.chara[0].name or "Avatar") if p.chara else "Avatar"
        lines: List[str] = []
        if not p.met_lb:                                 # C: first meeting (f_1e4 == 0)
            p.met_lb = 1
            lines += [
                "Lord British rises and says: At long last!",
                f"{name}, thou hast come!  We have waited such a long, long time...",
                "Lord British sits and says: A new age is upon Britannia.  A champion of "
                "virtue is called for.  Thou may be this champion, but only time shall tell.",
                "How may I help thee?",
            ]
        else:
            if p.member_count and p.chara[0].status == "D":   # resurrection
                p.chara[0].status = "G"
                lines.append(f"{name}, thou shalt live again!")
                self._heal_party()
            welcome = f"Lord British says: Welcome {name}"
            if p.member_count >= 3:
                welcome += " and thy worthy Adventurers!"
            elif p.member_count == 2:
                welcome += f" and thee also {p.chara[1].name}!"
            lines.append(welcome)
            lines += self._level_up()
            lines.append("What would thou ask of me?")
        return lines

    def respond(self, text: str) -> List[str]:
        if self._await_health:
            return self._answer_health(text)
        kw = self._match(text)
        self.prompt = "What else?"
        if not text.strip() or kw == "bye":
            self.done = True
            suffix = "s" if self.party.member_count > 1 else ""
            return [f"Lord British says: Fare thee well my friend{suffix}!"]
        if kw is None:
            return ["He says: I cannot help thee with that."]
        if kw == "health":
            self._await_health = True
            self.prompt = "Art thou well? (Y/N)"
            return ["He says: I am well, thank ye.", "He asks: Art thou well?"]
        if kw == "help":
            return self._help()
        return [LB_RESPONSES[kw]]

    def _answer_health(self, text: str) -> List[str]:    # C: C_E442
        self._await_health = False
        self.prompt = "What else?"
        if text[:1].upper() == "N":
            self._heal_party()
            return ["He says: Let me heal thy wounds!"]
        return ["He says: That is good."]

    _KEYWORDS = ("bye", "help", "health") + tuple(LB_RESPONSES)

    def _match(self, text: str):
        probe = text.strip().lower()
        if not probe:
            return None
        for kw in self._KEYWORDS:
            if probe == kw or (len(probe) >= 4 and probe[:4] == kw[:4]):
                return kw
        return None

    def _help(self) -> List[str]:                        # C: C_E21E (context-sensitive)
        p = self.party
        if p.moves < 1000:
            return ["He says: To survive in this hostile land thou must first know thyself!  "
                    "Until thou dost well know thyself, travel not far from the safety of the townes!"]
        if p.member_count <= 1:
            return ["He says: Travel not the open lands alone.  Build thy party unto eight "
                    "travellers, for only a true leader can win the Quest!"]
        if p.runes == 0:
            return ["He says: Learn ye the paths of virtue.  Find the Runes and Mantras, and seek "
                    "entry unto the eight shrines!"]
        if not all(p.karma):                              # some virtue still un-elevated
            return ["He says: Visit the Seer Hawkwind often; when ready he will advise thee to seek "
                    "the Elevation unto partial Avatarhood in a virtue."]
        if p.stones == 0:
            return ["He says: Go into the depths of the dungeons and recover the 8 colored stones "
                    "from the altar pedestals."]
        return ["He says: Find ye the Bell, Book and Candle, and the Key of Three Parts, then thou "
                "mayst enter the Great Stygian Abyss!  Go only with a party of eight!"]
