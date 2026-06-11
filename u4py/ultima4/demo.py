"""Live-demo framework: drive the real game like a player and record what happens.

A `Director` wraps a headless `Game` and plays it through the *same* input path a person at
the keyboard uses — `game.handle(key)` for commands/movement and `game.feed(line)` for talk &
shop interactions — capturing every message the game emits into a structured, replayable
transcript. Scenarios (demo_scenarios.py) are short scripts written against the Director's
verbs; the CLI (`./run demo`) runs them and prints the transcript, and the live-demo skill
lets the agent map a natural-language request ("take me through Lord British healing you")
to a scenario or compose a new one.

Pure and pygame-free: the transcript carries an ASCII minimap of the viewport, so a demo is
fully observable headlessly (CI, the agent, a terminal) without a window. A windowed visual
playback is a separate, optional front-end (see tools/demo.py --watch).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .constants import MODE_NAMES, MOD_BUILDING, MOD_OUTDOORS, MOD_DUNGEON, MOD_COMBAT
from .data_tables import LOCATION_FILES
from .game import Game
from .tiles import tile_name

# Town/castle name -> location id (1-based, matches LOCATION_FILES order). "lcb" == Lord
# British's castle. Lets scenarios say enter("britain") instead of juggling ids.
PLACE_BY_NAME: Dict[str, int] = {
    fn.split(".")[0].split("_")[0].lower(): i + 1 for i, fn in enumerate(LOCATION_FILES)
}
PLACE_BY_NAME["lcb"] = 1
PLACE_BY_NAME["britannia"] = PLACE_BY_NAME["britain"]

# Castles use a different entry tile than townes/villages (C: CMD_Enter coords).
_CASTLE_LOCS = {1, 2, 3, 4}

# Compact, stable glyphs for the ASCII minimap (terrain reads at a glance; '@' = the party).
_MINI = {0x00: "~", 0x01: "~", 0x02: ",", 0x03: "&", 0x04: ".", 0x05: "'", 0x06: "%",
         0x07: "n", 0x08: "^", 0x09: "O", 0x0A: "T", 0x0B: "C", 0x0C: "V", 0x17: "=",
         0x1B: "<", 0x1C: ">", 0x1E: "$", 0x3A: "+", 0x3B: "/", 0x3E: ".", 0x3F: ".",
         0x7F: "#"}


def _glyph(tile: int) -> str:
    if tile in _MINI:
        return _MINI[tile]
    if (tile & 0xF0) == 0xF0:           # dungeon wall band
        return "#"
    name = tile_name(tile)
    return name[0].upper() if name and name[0].isalpha() else "?"


@dataclass
class Step:
    kind: str                 # "narrate" | "do" | "say" | "expect" | "frame"
    label: str
    lines: List[str] = field(default_factory=list)   # game messages produced (or frame text)
    ok: Optional[bool] = None                         # for expectations


class Director:
    """Plays a `Game` and records a transcript. Verbs mirror real player input."""

    def __init__(self, seed: int = 0):
        self.game = Game()
        self.game.rng.seed(seed)
        self.steps: List[Step] = []
        self._cursor = len(self.game.messages)
        self.stage = None          # an optional PygameStage (ultima4/stage.py) for live playback
        self._banner = ""          # current caption shown over the live screen

    # --- live-playback pacing (no-op when headless) --------------------------
    def _beat(self, hold: float, input_text: str = "") -> None:
        if self.stage is not None:
            self.stage.present(self.game, banner=self._banner, hold=hold, input_text=input_text)

    # --- short-hands ---------------------------------------------------------
    @property
    def party(self):
        return self.game.party

    def _drain(self) -> List[str]:
        """All game messages emitted since the last drain (non-destructive)."""
        out = [m for m in self.game.messages[self._cursor:] if m != ""]
        self._cursor = len(self.game.messages)
        return out

    # --- narration & assertions ---------------------------------------------
    def narrate(self, text: str) -> "Director":
        self.steps.append(Step("narrate", text))
        self._banner = text
        self._beat(1.3)                       # hold so a watcher can read the caption
        return self

    def expect(self, cond: bool, desc: str) -> "Director":
        self.steps.append(Step("expect", desc, ok=bool(cond)))
        return self

    def expect_message(self, substr: str, desc: str = "") -> "Director":
        """Assert some message since the last drain contains `substr` (case-insensitive)."""
        recent = self._last_lines
        hit = any(substr.lower() in m.lower() for m in recent)
        return self.expect(hit, desc or f"game said something containing {substr!r}")

    # --- input verbs (the real player path) ----------------------------------
    def do(self, *keys: str, label: str = "") -> "Director":
        """Press one or more command/movement keys via game.handle()."""
        for k in keys:
            self.game.handle(k)
            self._beat(0.5)
        self._last_lines = self._drain()
        self.steps.append(Step("do", label or " ".join(keys), self._last_lines))
        self._beat(0.5)
        return self

    def say(self, *lines: str, label: str = "") -> "Director":
        """Feed lines into the active Talk/shop interaction via game.feed()."""
        for ln in lines:
            self.game.feed(ln)
            self._beat(0.9, input_text=ln)         # show the word "typed" into the interaction
        self._last_lines = self._drain()
        self.steps.append(Step("say", label or " / ".join(lines), self._last_lines))
        return self

    def move(self, direction: str, n: int = 1) -> "Director":
        d = {"N": "UP", "S": "DOWN", "E": "RIGHT", "W": "LEFT",
             "UP": "UP", "DOWN": "DOWN", "LEFT": "LEFT", "RIGHT": "RIGHT"}[direction.upper()]
        for _ in range(n):
            self.game.handle(d)
            self._beat(0.22)                       # per-step, so the walk animates tile by tile
        self._last_lines = self._drain()
        self.steps.append(Step("do", f"move {direction}x{n}", self._last_lines))
        return self

    def talk(self, direction: str, *lines: str) -> "Director":
        """Talk to the NPC in `direction`, then feed the conversation lines."""
        self.do("T", direction.upper(), label=f"Talk {direction.upper()}")
        if lines:
            self.say(*lines)
        return self

    # --- setup helpers (narrated as scene-setting, not player input) ----------
    def enter(self, name_or_loc, kind: Optional[str] = None) -> "Director":
        loc = PLACE_BY_NAME[name_or_loc.lower()] if isinstance(name_or_loc, str) else name_or_loc
        if kind is None:
            kind = "castle" if loc in _CASTLE_LOCS else "towne"
        entry = (15, 30) if kind == "castle" else (1, 15)
        self.game._enter_location(loc, entry=entry, kind=kind)
        self._last_lines = self._drain()
        nm = LOCATION_FILES[loc - 1].split(".")[0].title()
        self.steps.append(Step("do", f"enter {nm} ({kind})", self._last_lines))
        self._beat(0.8)
        return self

    def goto(self, x: int, y: int) -> "Director":
        """Place the party at (x, y) — a scene-cut to that spot (not a step-by-step walk)."""
        self.game.party.x, self.game.party.y = x, y
        self.steps.append(Step("narrate", f"(move to {x},{y})"))
        self._beat(0.4)
        return self

    def setup(self, fn: Callable[["Director"], None], note: str = "") -> "Director":
        """Run an arbitrary setup tweak on the game (party HP, reagents, class…)."""
        fn(self)
        if note:
            self.steps.append(Step("narrate", f"(setup: {note})"))
        self._beat(0.5)
        return self

    # --- observation ---------------------------------------------------------
    def minimap(self, radius: int = 4, label: str = "") -> "Director":
        """Capture an ASCII minimap of the current viewport into the transcript."""
        self.steps.append(Step("frame", label or MODE_NAMES[self.game.mode],
                               self._render_minimap(radius)))
        return self

    def _render_minimap(self, radius: int) -> List[str]:
        g = self.game
        grid = [row[:] for row in g.viewport(radius)]
        chars = [[_glyph(t) for t in row] for row in grid]
        for col, row, tile in (list(g.npc_sprites(radius)) + list(g.monster_sprites(radius))
                               + list(g.combat_sprites())):
            if 0 <= row < len(chars) and 0 <= col < len(chars[0]):
                chars[row][col] = _glyph(tile)
        mid = len(chars) // 2
        if chars:
            chars[mid][len(chars[0]) // 2] = "@"      # the party / avatar
        return ["".join(r) for r in chars]

    # --- results -------------------------------------------------------------
    @property
    def failures(self) -> List[str]:
        return [s.label for s in self.steps if s.kind == "expect" and s.ok is False]

    @property
    def passed(self) -> bool:
        return not self.failures

    def transcript(self, show_frames: bool = True) -> str:
        out: List[str] = []
        for s in self.steps:
            if s.kind == "narrate":
                out.append(f"\n  {s.label}")
            elif s.kind == "expect":
                out.append(f"      {'✓' if s.ok else '✗'} expect: {s.label}")
            elif s.kind == "frame":
                if show_frames:
                    out.append(f"      ┌─ {s.label} " + "─" * max(0, 18 - len(s.label)))
                    for ln in s.lines:
                        out.append(f"      │ {ln}")
                    out.append("      └" + "─" * 20)
            else:  # do / say
                arrow = "»" if s.kind == "do" else "›"
                out.append(f"    {arrow} {s.label}")
                for ln in s.lines:
                    out.append(f"        {ln}")
        n_ok = sum(1 for s in self.steps if s.kind == "expect" and s.ok)
        n_tot = sum(1 for s in self.steps if s.kind == "expect")
        out.append(f"\n  result: {n_ok}/{n_tot} expectations met"
                   + ("" if self.passed else f"  — FAILED: {self.failures}"))
        return "\n".join(out)
