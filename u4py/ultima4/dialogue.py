"""NPC dialogue (.TLK files), ported from U4_TALK.C.

A .TLK file is a flat array of 288-byte (0x120) records, one per talkable NPC, indexed
1-based by `tNPC.tlkidx` (idx 0 == "no dialogue"). Each record is:

    byte 0   question_trigger  -- which keyword index (into KEYWORDS) makes the NPC ask
                                  its yes/no question after answering (C: D_95CE[0])
    byte 1   humility_test     -- nonzero => the yes/no answer adjusts Humility karma
    byte 2   turn_away         -- temperament; rand(0..255) < this => NPC takes offence
    byte 3.. twelve NUL-terminated strings:
        name, pronoun, look, job, health, answer1, answer2,
        question, yes, no, keyword1, keyword2

At RUNTIME the game speaks only from `data/dialogue/<Town>.json` (the single source of truth);
the .TLK binary is an import source, decoded once by tools/dump_dialogue.py — never read while
playing (same single-source rule as .EGA->PNG; CLAUDE.md). Editing the JSON changes NPC lines live.

This module does two things, both central to the project's data-driven goal:
  1. decode the opaque binary into a clean, serialisable `Dialogue` (see to_dict /
     tools/dump_dialogue.py -> JSON; this is the form the tutor/editor agents read & write);
  2. run a faithful keyword conversation (`Conversation`) matching C_A4B4 / CMD_Talk.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import List, Optional

REC_BYTES = 0x120          # 288: one NPC's dialogue record
_NUM_STRINGS = 12

# Fixed keyword table (C: U4_TALK.C D_2A90). Slots 5 & 6 are filled per-NPC from the
# record's keyword1/keyword2. Matching is by case-insensitive 4-char prefix.
BYE, NAME, LOOK, JOB, HEALTH, KW1, KW2, JOIN, GIVE = range(9)


def _sentence(text: str) -> str:
    """Lowercase the first letter and end with a period, as C_A443 + TLK_look do."""
    text = (text[:1].lower() + text[1:]).rstrip()
    return text if text[-1:] in ".!?" else text + "."


def _strings_from(rec: bytes) -> List[str]:
    out, i = [], 3
    while len(out) < _NUM_STRINGS:
        j = rec.index(0, i)
        out.append(rec[i:j].decode("latin-1"))
        i = j + 1
    return out


@dataclass
class Dialogue:
    """One NPC's conversation, as plain data."""
    name: str
    pronoun: str
    look: str
    job: str
    health: str
    answer1: str
    answer2: str
    question: str
    yes: str
    no: str
    keyword1: str
    keyword2: str
    question_trigger: int   # byte 0
    humility_test: int      # byte 1
    turn_away: int          # byte 2

    @classmethod
    def parse(cls, rec: bytes) -> "Dialogue":
        if len(rec) != REC_BYTES:
            raise ValueError(f".TLK record must be {REC_BYTES} bytes, got {len(rec)}")
        s = _strings_from(rec)
        return cls(*s, question_trigger=rec[0], humility_test=rec[1], turn_away=rec[2])

    def to_dict(self) -> dict:
        """JSON-ready form — the editor/tutor surface (see tools/dump_dialogue.py)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Dialogue":
        """Inverse of to_dict() — load an NPC from edited JSON."""
        return cls(**d)


class TalkData:
    """All dialogue records for one location (one .TLK file), indexed by tlkidx."""

    def __init__(self, records: List[Dialogue]):
        self.records = records

    @classmethod
    def parse(cls, data: bytes) -> "TalkData":
        n = len(data) // REC_BYTES
        return cls([Dialogue.parse(data[i * REC_BYTES:(i + 1) * REC_BYTES]) for i in range(n)])

    @classmethod
    def load(cls, filename: str) -> "TalkData":
        from .savefile import load_bytes
        return cls.parse(load_bytes(filename))

    @classmethod
    def from_json(cls, records: list) -> "TalkData":
        return cls([Dialogue.from_dict(r) for r in records])

    def for_npc(self, tlkidx: int) -> Optional[Dialogue]:
        """C: dlseek(File_TLK, (tlkidx-1)*0x120). tlkidx 0 => no dialogue."""
        if tlkidx <= 0 or tlkidx > len(self.records):
            return None
        return self.records[tlkidx - 1]


def dialogue_json_path(loc_id: int):
    """Path to a location's canonical dialogue JSON. C: TLK_FILES[loc-1] -> <Town>.json."""
    from .data_tables import TLK_FILES
    from .savefile import DATA_DIR
    tlk = TLK_FILES[loc_id - 1]
    return DATA_DIR / "dialogue" / f"{tlk.split('.')[0].title()}.json"


def load_for_location(loc_id: int) -> TalkData:
    """Dialogue for a location, from its editable JSON — the single source of truth.

    `data/dialogue/<Town>.json` (generated once from the original .TLK by tools/dump_dialogue.py,
    then editable as plain text by the editor agent) is the ONLY runtime source: editing the JSON
    changes what NPCs say, live, with no code change. The binary .TLK is an import source only —
    never read at runtime — mirroring the .EGA->PNG single-source rule (CLAUDE.md). Regenerate a
    missing JSON with `./run dump`.
    """
    import json
    path = dialogue_json_path(loc_id)
    if not path.exists():
        raise FileNotFoundError(f"{path.name} missing — run `./run dump` to (re)generate dialogue "
                                f"JSON from the original .TLK (the import source).")
    return TalkData.from_json(json.loads(path.read_text(encoding="utf-8")))


class Conversation:
    """A live keyword conversation with one NPC (C: U4_TALK.C C_A4B4).

    Drive it by feeding player input to `respond()`, which returns the NPC's reply as a
    list of text lines. The conversation ends when `done` is True. Kept rendering-free so
    the same engine backs the pygame talk box, a headless demo, and the tutor agent.
    """

    def __init__(self, game, npc, dialogue: Dialogue):
        self.game = game
        self.npc = npc
        self.d = dialogue
        self.done = False
        self._await_yn = False       # expecting Y/N to the special question
        self._await_give = False     # expecting an amount after "give"

    # --- keyword table for this NPC (slots 5/6 are the per-NPC keywords) ---------
    def _keyword(self, idx: int) -> str:
        return {NAME: "name", LOOK: "look", JOB: "job", HEALTH: "health",
                KW1: self.d.keyword1, KW2: self.d.keyword2,
                JOIN: "join", GIVE: "give", BYE: "bye"}[idx]

    prompt = "Your interest:"          # shared interaction protocol (see game.Game._begin)

    def intro(self) -> List[str]:
        """C: 'You meet <look>' (look's first letter lowercased), 50% says name."""
        lines = [f"You meet {_sentence(self.d.look)}"]
        if self.game.rng.random() < 0.5:
            lines.append(f"{self.d.pronoun} says: I am {self.d.name}.")
        return lines

    def respond(self, text: str) -> List[str]:
        if self.done:
            return []
        text = text.strip()
        if self._await_yn:
            return self._answer_yn(text)
        if self._await_give:
            return self._answer_give(text)
        if not text:
            self.done = True
            return ["Bye."]

        # Temperament: the NPC may take offence before even hearing you out (C: D_95CE[2]).
        roll = self.game.rng.randint(0, 255)
        if roll < self.d.turn_away:
            if self.d.turn_away - roll >= 0x40:
                self.npc.var = 0xFF          # becomes hostile (C: sets _var = 0xff)
                self.done = True
                who = self.d.name or self.d.pronoun
                return [f"{who} says: On guard!  Fool!"]
            self.done = True
            return [f"{self.d.pronoun} turns away!"]

        idx = self._match(text)
        if idx is None:
            return ["That I cannot help thee with."]

        lines = self._dispatch(idx)
        # After answering, the trigger keyword makes the NPC pose its yes/no question.
        if not self.done and idx == self.d.question_trigger and self.d.question:
            self._await_yn = True
            lines = lines + ["", self.d.question, "(Y/N)"]
        return lines

    def _match(self, text: str) -> Optional[int]:
        probe = text[:4].lower()
        for idx in (BYE, NAME, LOOK, JOB, HEALTH, KW1, KW2, JOIN, GIVE):
            kw = self._keyword(idx)
            if kw and kw[:4].lower() == probe:
                return idx
        return None

    def _dispatch(self, idx: int) -> List[str]:
        d = self.d
        if idx == BYE:
            self.done = True
            return ["Bye."]
        if idx == NAME:
            return [f"{d.pronoun} says: I am {d.name}."]
        if idx == LOOK:
            return [f"You see {_sentence(d.look)}" if d.look else "You see nothing special."]
        if idx == JOB:
            return [d.job] if d.job else []
        if idx == HEALTH:
            return [d.health] if d.health else []
        if idx == KW1:
            return [d.answer1] if d.answer1 else []
        if idx == KW2:
            return [d.answer2] if d.answer2 else []
        if idx == JOIN:
            return self._join()
        if idx == GIVE:
            return self._give()
        return []

    # --- special yes/no question (C: C_A163) ---------------------------------
    def _answer_yn(self, text: str) -> List[str]:
        self._await_yn = self.done = self._await_yn and False  # clear flag
        c = text[:1].upper()
        if c not in ("Y", "N"):
            self._await_yn = True
            return ["Yes or no!"]
        p = self.game.party
        epoch = p.moves >> 4
        if c == "Y":
            if self.d.humility_test:
                p.karma[7] = max(0, p.karma[7] - 5)      # Humility down (pride)
            reply = self.d.yes
        else:
            if self.d.humility_test and epoch != p.last_karma_convo:
                p.karma[7] = min(99, p.karma[7] + 10)    # Humility up
            reply = self.d.no
        p.last_karma_convo = epoch
        self.done = True
        return [reply] if reply else []

    # --- join (C: TLK_join) --------------------------------------------------
    VIRTUE_ADJ = ("honest", "compassionate", "valiant", "just",
                  "sacrificial", "honorable", "spiritual", "humble")

    def _join(self) -> List[str]:
        p = self.game.party
        vi = p.loc - 5                                  # town -> virtue/class index 0..7
        avatar_class = ord(p.chara[0].char_class[:1] or "\x00")
        if self.npc.tlkidx != 1 or not (0 <= vi <= 7) or vi == avatar_class:
            return [f"{self.d.pronoun} says: I cannot join thee."]
        karma = p.karma[vi]
        if karma < 40 and karma != 0:
            return [f"Thou art not {self.VIRTUE_ADJ[vi]} enough for me to join thee."]
        if 100 * p.member_count + 100 > p.chara[0].hp_max:
            return ["Thou art not experienced enough for me to join thee."]
        # Pull the companion's character template from a dormant slot of matching class.
        slot = next((j for j in range(8)
                     if ord(p.chara[j].char_class[:1] or "\x00") == vi), None)
        if slot is not None and p.member_count < 8:
            import copy
            p.chara[p.member_count] = copy.deepcopy(p.chara[slot])
        p.member_count += 1
        self.npc.tile = self.npc.gtile = self.npc.var = self.npc.tlkidx = 0  # leaves the map
        self.done = True
        return ["I am honored to join thee!"]

    # --- give gold (C: TLK_give) ---------------------------------------------
    def _give(self) -> List[str]:
        from .tiles import BEGGAR
        if self.npc.tile != BEGGAR:
            return [f"{self.d.pronoun} says: I do not need thy gold.  Keep it!"]
        self._await_give = True
        return ["How much?"]

    def _answer_give(self, text: str) -> List[str]:
        self._await_give = False
        try:
            amount = int(text.strip() or "0")
        except ValueError:
            amount = 0
        if amount <= 0:
            return []
        p = self.game.party
        if p.gold < amount:
            return ["Thou hast not that much gold!"]
        p.gold -= amount
        epoch = p.moves >> 4
        if epoch != p.last_karma_convo:                 # Compassion up (C: karma_inc compa,2)
            p.karma[1] = min(99, p.karma[1] + 2)
            p.last_karma_convo = epoch
        return [f"{self.d.pronoun} says: Oh, thank thee!  I shall never forget thy kindness!"]
