"""Extract the intro/tarot text + layout from the ORIGINAL title source -> editable JSON.

Import-time tool (like convert_graphics): parses u4/SRC-TITLE/TITLE_1.C and TITLE_0.C and
writes data/intro/*.json, the single runtime source of truth for the intro. Run `./run intro`.
We parse the original C string tables verbatim (no hand-transcription drift, CLAUDE.md rule #1);
the few control-flow facts (scene backgrounds, the pair->question map) are taken from the cited
functions and recorded as small tables here.

Sources (all cited):
  - TITLE_1.C  D_2EE6[0x43]  : every intro string (questions 0x01-0x1C, narrative 0x1D-0x34,
                               card-place 0x35-0x38, virtue names 0x39-0x40, finale 0x42-0x43).
  - TITLE_1.C  D_30CA[]      : pair->question index, STR(D_30CA[a] + b) for virtues a<b.
  - TITLE_1.C  C_2C12 casting: A => virtue a (loc_B), B => virtue b (loc_C); chosen +5 karma.
  - TITLE_1.C  D_307E[]      : 4 pair-card images (HONCOM,VALJUS,SACHONOR,SPIRHUM); virtue v is
                               drawn from D_307E[v/2], left half if v even else right (C_2B6D).
  - TITLE_1.C  C_2883        : the 0x1D..0x34 narrative loop + which .ega backdrop is loaded when.
  - TITLE_0.C  C_0B45        : the title-screen menu — C_0B1E(row, col, "text").
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # u4py/
SRC_TITLE = ROOT.parent / "u4" / "SRC-TITLE"
OUT = ROOT / "data" / "intro"

# --- the 8 virtues, in their canonical index order (TITLE_1.C STR(0x39+i)). -----------------
# (We read the names from D_2EE6 below; this is just the count/order for the bracket math.)
N_VIRTUES = 8

# pair -> question: STR index (1-based) = D_30CA[a] + b, for the pair (a, b) with a < b.
# C: TITLE_1.C D_30CA[] = {0x01-1, 0x08-2, 0x0e-3, 0x13-4, 0x17-5, 0x1a-6, 0x1c-7}.
D_30CA = [0x01 - 1, 0x08 - 2, 0x0e - 3, 0x13 - 4, 0x17 - 5, 0x1a - 6, 0x1c - 7]

# 4 pair-card images; virtue v -> image D_307E[v//2], side left(even)/right(odd). C: D_307E / C_2B6D.
CARD_IMAGES = ["honcom", "valjus", "sachonor", "spirhum"]

# The 0x1D..0x34 narrative scenes and which backdrop is on screen for each, plus any animation
# that plays AFTER the scene. Derived from C_2883 (the switch fires on the index just shown, so
# a load affects the *following* scenes). Backdrop files are the lowercased .ega stems.
SCENE_BG = {  # str index (hex) -> backdrop stem
    0x1d: "tree", 0x1e: "tree", 0x1f: "tree", 0x20: "tree", 0x21: "tree", 0x22: "tree",
    0x23: "portal",
    0x24: "tree", 0x25: "tree", 0x26: "tree", 0x27: "tree", 0x28: "tree",
    0x29: "outside", 0x2a: "outside", 0x2b: "outside", 0x2c: "outside",
    0x2d: "inside", 0x2e: "inside",
    0x2f: "wagon", 0x30: "wagon", 0x31: "wagon",
    0x32: "gypsy",
    0x33: "abacus", 0x34: "abacus",
}
SCENE_AFTER = {0x20: "moongate_anim_1", 0x22: "moongate_anim_2"}  # C_273E / C_27E0


def _parse_c_string(s: str, i: int):
    """Parse one C string literal beginning at s[i]=='"'; return (text, index-after-close).
    Handles \\n \\t \\r \\" \\\\ \\xHH and backslash-newline line continuations."""
    assert s[i] == '"'
    i += 1
    out = []
    while s[i] != '"':
        c = s[i]
        if c == "\\":
            n = s[i + 1]
            if n == "\n":            # line continuation -> nothing
                i += 2
                continue
            simple = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "0": "\0"}
            if n in simple:
                out.append(simple[n])
                i += 2
                continue
            if n == "x":             # hex escape: consume up to 2 hex digits
                j = i + 2
                while j < i + 4 and s[j] in "0123456789abcdefABCDEF":
                    j += 1
                out.append(chr(int(s[i + 2:j], 16)))
                i = j
                continue
            out.append(n)            # unknown escape: drop the backslash
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out), i + 1


def _parse_string_array(text: str, decl: str) -> list:
    """Parse a C `char *NAME[...] = { "a", "b" "c", ... };` table into a list of strings,
    concatenating adjacent literals (C string concatenation) and skipping /* */ comments."""
    start = text.index(decl)
    i = text.index("{", start) + 1
    end = text.index("};", i)
    out, cur, in_entry = [], "", False
    while i < end:
        c = text[i]
        if c == '"':
            piece, i = _parse_c_string(text, i)
            cur += piece
            in_entry = True
        elif c == ",":
            out.append(cur)
            cur, in_entry = "", False
            i += 1
        elif text[i:i + 2] == "/*":
            i = text.index("*/", i) + 2
        else:
            i += 1
    if in_entry:
        out.append(cur)
    return out


def main() -> None:
    title1 = (SRC_TITLE / "TITLE_1.C").read_text(errors="replace")
    title0 = (SRC_TITLE / "TITLE_0.C").read_text(errors="replace")
    OUT.mkdir(parents=True, exist_ok=True)

    strs = _parse_string_array(title1, "D_2EE6")          # 0x43 entries, STR(i) == strs[i-1]
    def STR(i):                                            # 1-based, as the original macro
        return strs[i - 1]

    virtues = [STR(0x39 + v) for v in range(N_VIRTUES)]    # Honesty..Humility

    # questions.json: one entry per virtue PAIR, verbatim prose, A=>a_virtue B=>b_virtue.
    questions = []
    for a in range(N_VIRTUES):
        for b in range(a + 1, N_VIRTUES):
            questions.append({
                "a_index": a, "b_index": b,
                "a_virtue": virtues[a], "b_virtue": virtues[b],
                "text": STR(D_30CA[a] + b),               # STR(D_30CA[a] + b), C: TITLE_1.C:732
            })

    # cards.json: each virtue's tarot card art (image + which half). C: D_307E / C_2B6D.
    cards = [{"index": v, "virtue": virtues[v],
              "image": CARD_IMAGES[v // 2],
              "side": "left" if v % 2 == 0 else "right"} for v in range(N_VIRTUES)]

    # narrative.json: the intro scenes (0x1D..0x34) in order, each with its backdrop, plus the
    # casting/finale fragments. Text verbatim incl. original \n.
    intro_scenes = []
    for idx in range(0x1d, 0x35):
        intro_scenes.append({
            "str": idx, "background": SCENE_BG[idx],
            "after": SCENE_AFTER.get(idx), "text": STR(idx),
        })
    narrative = {
        "intro_sequence": intro_scenes,
        "casting": {                                       # C: TITLE_1.C C_2C12
            "place_first_two": STR(0x35),
            "place_two_more": STR(0x36),
            "place_last_two": STR(0x37),
            "are_the_cards_of": STR(0x38),
            "and": " and ",                                # D_308E
            "consider": ".  She says\n\"Consider this:\"",  # D_3094
            "path_chosen": STR(0x42),
            "transport": STR(0x43),
        },
        "book_of_history_placeholder": [STR(0x29), STR(0x2a)],   # the two "read the book" lines
    }

    # menus.json (Option C): the title-screen menu — C_0B1E(row, col, "text"), C: TITLE_0.C C_0B45.
    block = title0[title0.index("C_0B45"):]
    block = block[:block.index("\n}")]
    lines = []
    for m in re.finditer(r'C_0B1E\(\s*(\d+),\s*(\d+),[^"]*("(?:[^"\\]|\\.)*")\)', block):
        row, col = int(m.group(1)), int(m.group(2))
        text, _ = _parse_c_string(m.group(3), 0)
        lines.append({"row": row, "col": col, "text": text})
    # The three selectable options live on rows 17-19 (C: TITLE_0.C C_0B45). Actions per ROADMAP.
    actions = {"Return to the view": "return_to_view",
               "Journey Onward": "journey_onward",      # load PARTY.SAV
               "Initiate New Game": "new_game"}
    options = [{"row": l["row"], "label": l["text"], "action": actions[l["text"]]}
               for l in lines if l["text"] in actions]
    menus = {"title_screen": {"lines": lines, "options": options,
                              "cursor": {"row": 16, "col": 24}}}  # txt_Y=16 txt_X=24

    for name, obj in (("questions", questions), ("cards", cards),
                      ("narrative", narrative), ("menus", menus)):
        (OUT / f"{name}.json").write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
    print(f"  intro JSON -> {OUT}  ({len(questions)} questions, {len(intro_scenes)} scenes, "
          f"{len(menus['title_screen']['lines'])} menu lines)")


if __name__ == "__main__":
    main()
