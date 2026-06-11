"""The intro / launch sequence — title menu → new game → gypsy casting → Britannia.

Faithful to SRC-TITLE/TITLE_0.C (title + menu) and TITLE_1.C (narrative + casting). All text
comes from the editable intro JSON (intro_data); all rendering is the original CHARSET font with
word-wrap + keypress pagination (textwin). This module is the *logic/state machine*; play.py is
the pygame driver that blits backdrops/cards and the paginated text and feeds it keys — so the
whole flow is headless-testable.

Control flow (cited):
  - Title menu: the player presses a letter — (R)eturn to view, (I)nitiate new game, (J)ourney
    onward (load save). C: TITLE_0.C main() switch on KBD_R/KBD_I/KBD_J.
  - New game narrative: scenes 0x1D..0x34 shown in order over their backdrops, a keypress between
    each. C: TITLE_0.C? no — TITLE_1.C C_2883.
  - Casting: a single-elimination bracket over the 8 virtues, 7 questions (8->4->2->1). Each
    question pits two not-yet-eliminated virtues; A keeps the first, B the second; the loser is
    eliminated; winners reseed into the next round (reset at q4 and q6). The survivor is the class.
    C: TITLE_1.C C_2C12. The chosen virtue gains +5 karma and stat increments (D_30B2/BA/C2).
  - Finale: "Thy path is chosen" (STR 0x42) then the moongate transport (STR 0x43, PORTAL). C: C_2C12.
"""
from . import intro_data
from .character_creation import build_party
from .constants import VIRTUES
from .data_tables import CLASS_NAMES, CLASS_HOME
from .textwin import pages_for, INTRO_COLS, INTRO_ROWS


class CastingBracket:
    """The gypsy's 7-question elimination over the 8 virtues. C: TITLE_1.C C_2C12.

    Pairings are random among the not-yet-eliminated virtues (seeded via game.rng for
    reproducibility). Reseed at questions 4 and 6 returns that round's winners to the pool,
    giving the 8->4->2->1 bracket. A => first virtue (a) wins, B => second (b) wins."""
    N = 8

    def __init__(self, rng):
        self.rng = rng
        self.elim = [0] * self.N        # 0 available, 1 won-this-round, 0xff eliminated (loc_D)
        self.qi = 0                     # curQuestionIndex 0..6
        self.champion = None
        self.cur = None                 # (a, b) with a < b
        self._next_pair()

    def _avail(self):
        return [i for i in range(self.N) if self.elim[i] == 0]

    def _next_pair(self):
        # reseed: returns this round's temp winners (==1) to the pool. C: C_2C12 q==4||q==6.
        if self.qi == 4 or self.qi == 6:
            for i in range(self.N):
                if self.elim[i] < 0x80:
                    self.elim[i] = 0
        avail = self._avail()
        a = avail[self.rng.randrange(len(avail))]
        b = a
        while b == a:
            b = avail[self.rng.randrange(len(avail))]
        self.cur = (a, b) if a < b else (b, a)

    def question(self) -> dict:
        """The current question record from the editable JSON (verbatim prose + virtues)."""
        a, b = self.cur
        return intro_data.question_for(a, b)

    def answer(self, choice: str) -> None:
        """choice 'A' keeps virtue a, 'B' keeps virtue b. Eliminate the loser; advance."""
        a, b = self.cur
        chosen, discarded = (a, b) if choice.upper() == "A" else (b, a)
        self.elim[chosen] = 1
        self.elim[discarded] = 0xff
        self.qi += 1
        if self.qi == 7:
            self.champion = chosen      # lastVirtue -> class
        else:
            self._next_pair()

    @property
    def done(self) -> bool:
        return self.champion is not None


def _scene_pages(text):
    """Wrap+paginate a narrative string to the intro window (40x6). C: txt_Y=19 window."""
    return pages_for(text, INTRO_COLS, INTRO_ROWS)


class IntroDirector:
    """Drives the title/intro as a sequence of screens. play.py renders screen() and feeds key().

    A *screen* is {phase, bg, lines, page, npages, cards, options, mode}:
      mode 'menu'  -> draw the menu lines; act on the option letters
      mode 'page'  -> draw `lines`; any key advances (paginated narrative/cards/reveal)
      mode 'ab'    -> draw `lines` (a question); only A/B advance
    """
    def __init__(self, game):
        self.game = game
        self.phase = "menu"
        self.done = False               # whole intro finished -> play the game
        self.start_load = False         # 'Journey Onward' chose to load a save
        self._menu = intro_data.menus()["title_screen"]
        self._narr = intro_data.narrative()
        self.view_only = False          # 'Return to the view' hides the menu over the animated title
        self.bracket = None
        self._pages = []                # current multi-page buffer
        self._pi = 0                    # page index within the buffer
        self._scene_i = 0               # index into the narrative scene list
        self._cards = None              # (a,b) virtue indices to draw, or None
        self._champion = None

    # --- screen description for the renderer ---------------------------------------------
    def screen(self) -> dict:
        if self.phase == "menu":
            # The title backdrop is TITLE (the assembled "Ultima IV / Quest of the Avatar" logo
            # with the menu box). The two animated "monsters" (C: TITLE_0.C C_068C) frame the top
            # corners — play.py draws them whenever bg=="title". 'Return to the view' hides the menu.
            if self.view_only:                          # C: TITLE_0.C C_05A4 (view, menu hidden)
                return {"phase": "menu", "bg": "title", "mode": "view", "lines": []}
            return {"phase": "menu", "bg": "title", "mode": "menu",
                    "lines": self._menu["lines"], "options": self._menu["options"]}
        if self.phase == "question":
            last = self._pi == len(self._pages) - 1     # A/B only accepted on the final page
            return {"phase": "question", "bg": "gypsy", "mode": "ab" if last else "page",
                    "lines": self._pages[self._pi], "page": self._pi,
                    "npages": len(self._pages), "cards": self._cards}
        # narrative / cards / reveal / transport: a paginated 'page' screen
        bg = self._bg
        return {"phase": self.phase, "bg": bg, "mode": "page",
                "lines": self._pages[self._pi], "page": self._pi,
                "npages": len(self._pages), "cards": self._cards}

    # --- input ---------------------------------------------------------------------------
    def key(self, ch: str) -> None:
        ch = (ch or "").upper()
        if self.phase == "menu":
            if self.view_only:                          # any key leaves the view, restores the menu
                self.view_only = False
            else:
                self._menu_key(ch)
        elif self.phase == "question":
            if self._pi < len(self._pages) - 1:         # page through a long question first
                self._pi += 1
            elif ch in ("A", "B"):
                self._answer(ch)
        else:
            self._advance_page()

    def _menu_key(self, ch):
        action = next((o["action"] for o in self._menu["options"]
                       if o["label"][0].upper() == ch), None)
        if action == "new_game":
            self._begin_narrative()
        elif action == "journey_onward":
            self.start_load = True
            self.done = True
        elif action == "return_to_view":                # hide the menu, watch the animated title
            self.view_only = True

    # --- narrative -----------------------------------------------------------------------
    def _begin_narrative(self):
        self.phase = "narrative"
        self._scene_i = 0
        self._cards = None
        self._load_scene()

    def _load_scene(self):
        scene = self._narr["intro_sequence"][self._scene_i]
        self._bg = scene["background"]
        self._pages = _scene_pages(scene["text"])
        self._pi = 0

    def _advance_page(self):
        self._pi += 1
        if self._pi < len(self._pages):
            return
        # finished this buffer; move to the next thing in the current phase
        if self.phase == "narrative":
            self._scene_i += 1
            if self._scene_i < len(self._narr["intro_sequence"]):
                self._load_scene()
            else:
                self._begin_casting()
        elif self.phase == "cards":
            self._show_question()
        elif self.phase == "reveal":
            self._begin_transport()
        elif self.phase == "transport":
            self.done = True            # -> drop into Britannia

    # --- casting -------------------------------------------------------------------------
    def _begin_casting(self):
        self.bracket = CastingBracket(self.game.rng)
        self._show_cards()

    def _show_cards(self):
        """The 'gypsy places the cards ... they are the cards of X and Y' beat before a question."""
        c = self._narr["casting"]
        qi = self.bracket.qi
        place = (c["place_first_two"] if qi == 0 else
                 c["place_last_two"] if qi == 6 else c["place_two_more"])
        a, b = self.bracket.cur
        text = place + c["are_the_cards_of"] + VIRTUES[a] + c["and"] + VIRTUES[b] + c["consider"]
        self.phase = "cards"
        self._bg = "gypsy"
        self._cards = (a, b)
        self._pages = _scene_pages(text)
        self._pi = 0

    def _show_question(self):
        self.phase = "question"
        self._pages = _scene_pages(self.bracket.question()["text"])
        self._pi = 0
        # cards stay drawn alongside the question

    def _answer(self, ch):
        self.bracket.answer(ch)
        if self.bracket.done:
            self._begin_reveal()
        else:
            self._show_cards()

    # --- finale --------------------------------------------------------------------------
    def _begin_reveal(self):
        cls = self.bracket.champion
        self._champion = cls
        c = self._narr["casting"]
        text = (c["path_chosen"] + "\n\n" +
                "Thou art a " + CLASS_NAMES[cls] + "!\n" +
                "Thy quest begins near " + CLASS_HOME[cls] + ".")
        self.phase = "reveal"
        self._bg = "gypsy"
        self._cards = None
        self._pages = _scene_pages(text)
        self._pi = 0

    def _begin_transport(self):
        self.phase = "transport"
        self._bg = "portal"             # the moongate cinematic backdrop (PORTAL.EGA)
        self._pages = _scene_pages(self._narr["casting"]["transport"])
        self._pi = 0

    def commit(self) -> None:
        """Build the party for the chosen class (call once self.done and a new game was played)."""
        if self._champion is not None:
            build_party(self.game, self._champion)
