"""Loader for the editable intro/tarot JSON — the single runtime source of truth.

The game reads data/intro/*.json (generated once from the original by tools/extract_intro.py,
C: SRC-TITLE/TITLE_1.C + TITLE_0.C). Editing a question's text or a menu label in the JSON
changes what renders in-game — no code change. There is no .C fallback at runtime; the source
is an import source only (CLAUDE.md rule #1, single-source-of-truth pattern).
"""
import json
from functools import lru_cache
from pathlib import Path

INTRO_DIR = Path(__file__).resolve().parent.parent / "data" / "intro"


@lru_cache(maxsize=None)
def _load(name: str):
    return json.loads((INTRO_DIR / f"{name}.json").read_text())


def questions() -> list:
    """The 28 virtue-pair moral questions: {a_index,b_index,a_virtue,b_virtue,text}."""
    return _load("questions")


def question_for(a: int, b: int) -> dict:
    """The question for the unordered virtue pair (a, b). A => virtue a, B => virtue b
    (the original orders the pair a<b before lookup; C: TITLE_1.C STR(D_30CA[a]+b))."""
    lo, hi = (a, b) if a < b else (b, a)
    for q in questions():
        if q["a_index"] == lo and q["b_index"] == hi:
            return q
    raise KeyError((a, b))


def cards() -> list:
    """Per-virtue tarot card art: {index,virtue,image,side}. C: TITLE_1.C D_307E / C_2B6D."""
    return _load("cards")


def card_for(virtue: int) -> dict:
    return cards()[virtue]


def narrative() -> dict:
    """Intro scenes (0x1D..0x34 with backdrops) + casting/finale fragments. C: TITLE_1.C C_2883/C_2C12."""
    return _load("narrative")


def menus() -> dict:
    """Title-screen menu layout (Option C): lines with row/col, selectable options. C: TITLE_0.C C_0B45."""
    return _load("menus")
