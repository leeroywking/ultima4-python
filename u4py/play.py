"""Interactive Ultima IV — boot the game and play.

    python play.py [cga|ega] [--town NAME]

Arrow keys move. Letter keys are commands (E=enter, T=talk, Q=quit; others are stubs).
Talk: press T then a direction toward an NPC; then type a keyword (name/job/health/join/
bye) and Enter. Walk up to a shop sign and Talk into it to buy/sell. `--town NAME` boots
straight inside a town (e.g. `--town britain`) so you can test NPCs and shops immediately.
"""
import sys
from pathlib import Path

import pygame

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ultima4.constants import DIR_DX, DIR_DY, MOD_OUTDOORS
from ultima4.data_tables import LOCATION_FILES, MOON_PHASE_NAMES
from ultima4.game import Game
from ultima4.tiles import is_walkable, anim_frame
from ultima4.textwin import wrap_text

ASSETS = Path(__file__).resolve().parent / "assets"   # PNG = the single source of truth

_DIR_WORD = {0: "West", 1: "North", 2: "East", 3: "South"}

TILE = 16
SCALE = 3
RADIUS = 5                     # 11x11 viewport
VIEW = (2 * RADIUS + 1) * TILE  # 176 px
PANEL_H = 200
AVATAR_TILE = 0x1F
CHAR_PX = 8 * SCALE        # moon glyph display size (8x8 charset glyph, scaled)
FONT_SCALE = 2             # in-game text: the original 8x8 CHARSET font, 2x for readability
FONT_PX = 8 * FONT_SCALE   # 16px per glyph

# Arrow keys -> movement tokens; letter keys pass straight through as commands.
ARROWS = {pygame.K_UP: "UP", pygame.K_DOWN: "DOWN", pygame.K_LEFT: "LEFT", pygame.K_RIGHT: "RIGHT"}


# The animation/redraw tick. The DOS game animates off int 0x1C, the BIOS timer at 18.2 Hz
# (u4/SRC/LOW.ASM) — NOT a modern 60 fps. We run the loop at that rate.
DOS_TIMER_HZ = 18      # int 0x1C ~= 18.2 Hz
MOON_GLYPH_BASE = 0x14  # C: U4_ANIM.C C_3A80 draws a moon as charset glyph 0x14+((phase-1)&7)


def _load_sheet(name: str):
    return pygame.image.load(str(ASSETS / name)).convert()


def load_tiles(which: str):
    """256 tiles sliced from the canonical spritesheet PNG (assets/shapes.png), pre-scaled."""
    sheet = _load_sheet("shapes_cga.png" if which == "cga" else "shapes.png")
    out = []
    for i in range(256):
        cell = sheet.subsurface(((i % 16) * TILE, (i // 16) * TILE, TILE, TILE))
        out.append(pygame.transform.scale(cell, (TILE * SCALE, TILE * SCALE)))
    return out


def load_font_glyphs(which: str):
    """All 256 CHARSET glyphs (8x8) from the canonical font sheet, scaled to FONT_PX.
    Indexed by byte value: glyph[ord(ch)] is that ASCII character (verified ASCII-laid-out;
    'A'==0x41). The original renders every in-game string with this font (u4/SRC charset)."""
    sheet = _load_sheet("charset_cga.png" if which == "cga" else "charset.png")
    n = (sheet.get_width() // 8) * (sheet.get_height() // 8)   # CGA font is only 128 glyphs
    out = []
    for i in range(n):
        cell = sheet.subsurface(((i % 16) * 8, (i // 16) * 8, 8, 8))
        out.append(pygame.transform.scale(cell, (FONT_PX, FONT_PX)))
    return out


def blit_text(screen, glyphs, text: str, x: int, y: int) -> None:
    """Draw a string at (x,y) using the CHARSET font, one glyph per byte. Bytes past the
    font's glyph count render as space. The font is its native EGA color (white) — the
    original used a single font color, so we don't recolor."""
    for ch in text:
        i = ord(ch)
        if i < len(glyphs):
            screen.blit(glyphs[i], (x, y))
        x += FONT_PX


def load_moon_glyphs(which: str):
    """The 8 moon-phase glyphs from the font sheet (chars 0x14..0x1B). C: U4_ANIM.C C_3A80."""
    sheet = _load_sheet("charset_cga.png" if which == "cga" else "charset.png")
    out = []
    for i in range(8):
        idx = MOON_GLYPH_BASE + i
        cell = sheet.subsurface(((idx % 16) * 8, (idx // 16) * 8, 8, 8))
        out.append(pygame.transform.scale(cell, (CHAR_PX, CHAR_PX)))
    return out


def load_picture(name: str):
    """A full-screen 320x200 intro picture from its canonical PNG (assets/<name>.png)."""
    return pygame.image.load(str(ASSETS / f"{name}.png")).convert()


class Assets:
    """The scaled sprite/font/moon sheets a game frame needs. Built once per window."""
    def __init__(self, which: str = "ega"):
        self.tiles = load_tiles(which)
        self.font_glyphs = load_font_glyphs(which)
        self.moon_glyphs = load_moon_glyphs(which)


def draw_game(screen, A: "Assets", game, phase: int = 0, banner: str = None,
              input_text: str = None) -> None:
    """Render one in-game frame (viewport + sprites + avatar + moons + message panel).

    Shared by interactive play (play.main) and the scripted live demo (the autopilot stage),
    so what an agent-driven playthrough shows on screen is pixel-identical to real play. A
    `banner` draws a caption strip over the top (the demo narration); `input_text` is the
    talk/shop input line.
    """
    px = TILE * SCALE
    screen.fill((0, 0, 0))
    for j, row in enumerate(game.viewport(RADIUS)):
        for i, tid in enumerate(row):
            screen.blit(A.tiles[tid], (i * px, j * px))
    if game.mode == 4:                              # MOD_COMBAT: draw the arena combatants
        for col, row, tid in game.combat_sprites():
            screen.blit(A.tiles[anim_frame(tid, phase)], (col * px, row * px))
    else:
        for col, row, tid in game.npc_sprites(RADIUS) + game.monster_sprites(RADIUS):
            screen.blit(A.tiles[anim_frame(tid, phase)], (col * px, row * px))
        screen.blit(A.tiles[AVATAR_TILE], (RADIUS * px, RADIUS * px))
    if game.mode == MOD_OUTDOORS:
        cx = (VIEW * SCALE - 2 * CHAR_PX) // 2
        for k, ph in enumerate((game.party.trammel & 7, game.party.felucca & 7)):
            screen.blit(A.moon_glyphs[(ph - 1) & 7], (cx + k * CHAR_PX, 2))
    y0 = VIEW * SCALE + 6
    blit_text(screen, A.font_glyphs, game.status_line(), 6, y0)
    cols = (VIEW * SCALE - 12) // FONT_PX
    lines = []
    for msg in game.messages:
        for seg in (msg.split("\n") if msg else [""]):
            lines.extend(wrap_text(seg, cols))
    max_rows = (PANEL_H - FONT_PX - 8 - (FONT_PX + 4 if game.active else 0)) // FONT_PX
    for k, line in enumerate(lines[-max_rows:]):
        blit_text(screen, A.font_glyphs, line, 6, y0 + FONT_PX + 4 + k * FONT_PX)
    if game.active is not None and input_text is not None:
        blit_text(screen, A.font_glyphs, "> " + input_text + "_", 6,
                  VIEW * SCALE + PANEL_H - FONT_PX - 2)
    if banner:                                       # demo caption strip over the top of the map
        bar = pygame.Surface((VIEW * SCALE, FONT_PX + 6)); bar.set_alpha(210); bar.fill((0, 0, 40))
        screen.blit(bar, (0, 0))
        blit_text(screen, A.font_glyphs, banner[:cols], 6, 3)
    pygame.display.flip()


def load_native_glyphs(which: str):
    """The CHARSET font at native 8x8 (unscaled) — the intro composes at 320x200 then scales
    the whole frame, so glyphs stay pixel-aligned with the picture. C: intro draws at 8px cells."""
    sheet = _load_sheet("charset_cga.png" if which == "cga" else "charset.png")
    n = (sheet.get_width() // 8) * (sheet.get_height() // 8)
    return [sheet.subsurface(((i % 16) * 8, (i // 16) * 8, 8, 8)) for i in range(n)]


def _native_text(surf, glyphs, text: str, col: int, row: int) -> None:
    """Blit a string at char (col,row) on a 320x200 surface, 8px per cell. C: txt_X/txt_Y."""
    x = col * 8
    for ch in text:
        i = ord(ch)
        if i < len(glyphs):
            surf.blit(glyphs[i], (x, row * 8))
        x += 8


def run_title(screen, which: str, game, scripted=None) -> bool:
    """The faithful title + intro/launch sequence (C: TITLE_0.C / TITLE_1.C), driven by
    IntroDirector. Everything composes on a native 320x200 surface (picture backdrop + CHARSET
    text window at row 19 + the gypsy's virtue cards) and is scaled up to the window. Returns
    True to start the game, False if the player quit. `scripted` (an iterator of key chars) drives
    it headlessly for tests."""
    from ultima4.intro import IntroDirector
    from ultima4 import intro_data, title_anim
    director = IntroDirector(game)
    glyphs = load_native_glyphs(which)
    W = screen.get_width()
    SH = W * 200 // 320                                  # scaled intro height (keep 320:200)
    clock = pygame.time.Clock()
    cache = {}
    def pic(name):
        if name not in cache:
            cache[name] = load_picture(name)
        return cache[name]
    mon1, mon2 = title_anim.crop_frames(pic("animate"))  # the two title "monsters"
    sheet = _load_sheet("shapes_cga.png" if which == "cga" else "shapes.png")
    ntiles = [sheet.subsurface(((t % 16) * TILE, (t // 16) * TILE, TILE, TILE)) for t in range(256)]
    view = title_anim.ViewAnim()                         # the animated overworld demo in the box
    step = [0]                                            # animation counter (advances per tick)

    def render():
        s = director.screen()
        surf = pygame.Surface((320, 200))
        if s.get("bg"):
            surf.blit(pic(s["bg"]), (0, 0))
        if s.get("bg") == "title":                       # animated title: the box "view" + monsters
            vx, vy = title_anim.VIEW_DST
            for r in range(title_anim.VIEW_ROWS):        # the static overworld base map (LB castle)
                for c in range(title_anim.VIEW_COLS):
                    surf.blit(ntiles[title_anim.VIEW_MAP[r * title_anim.VIEW_COLS + c]],
                              (vx + c * TILE, vy + r * TILE))
            for sx, sy, tid in view.sprites():           # the moving sprites (fighter, ships, ...)
                surf.blit(ntiles[anim_frame(tid, step[0] >> 2)], (vx + sx * TILE, vy + sy * TILE))
            i1, i2 = title_anim.frame_indices(step[0] // 3)   # ~6 Hz idle cycle (C: C_068C loop)
            surf.blit(mon1[i1], title_anim.DST1)
            surf.blit(mon2[i2], title_anim.DST2)
        if s.get("cards"):                              # the two virtue tarot cards (C: C_2B6D)
            # Each card is a 96x124 region of its pair image at src x=8 (left virtue) or x=216
            # (right virtue), y=12 (C: TITLE_1.C C_2B6D Gra_3(12,124,1|27,12,...)). Draw the
            # chosen pair side by side at those same columns over the gypsy scene.
            a, b = s["cards"]
            for card, dst_x in ((intro_data.card_for(a), 8), (intro_data.card_for(b), 216)):
                src_x = 8 if card["side"] == "left" else 216
                surf.blit(pic(card["image"]), (dst_x, 12), (src_x, 12, 96, 124))
        if s["mode"] == "menu":
            for ln in s["lines"]:                       # Option C menu at its source row/col
                _native_text(surf, glyphs, ln["text"], ln["col"], ln["row"])
        elif s["mode"] == "view":
            pass                                        # menu hidden — just the animated title
        else:                                           # narrative/question/reveal: window at row 19
            # The original blits the picture only 152px tall and clears the bottom 48px to black
            # as the text window (C: TITLE_1.C Gra_3(40,152,..) + Gra_5). Match it so text is always
            # legible on a black strip, not over bright art.
            surf.fill((0, 0, 0), (0, 19 * 8, 320, 200 - 19 * 8))
            for k, line in enumerate(s["lines"]):
                _native_text(surf, glyphs, line, 0, 19 + k)
        screen.fill((0, 0, 0))
        screen.blit(pygame.transform.scale(surf, (W, SH)), (0, 0))
        pygame.display.flip()

    while not director.done:
        render()
        step[0] += 1                                    # advance the title-monster animation
        if step[0] % 2 == 0:                            # advance the box "view" demo (~9 Hz)
            view.tick()
        if scripted is not None:
            ch = next(scripted, None)
            if ch is None:
                return False
            director.key(ch)
            continue
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return False
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    return False
                if ev.unicode:
                    director.key(ev.unicode)
        clock.tick(DOS_TIMER_HZ)

    if director.start_load:                             # 'Journey Onward' -> resume the saved game
        try:
            game.load_saved()                           # C: U4_INIT.C Load("PARTY.SAV")
        except FileNotFoundError:
            game.message("No saved game found — starting anew.")
    else:
        director.commit()                               # build the party for the chosen class
    return True


def find_town(name: str):
    """Map a town name to (loc_id, entry, kind) for a debug start-in-town boot."""
    name = name.lower()
    for i, fname in enumerate(LOCATION_FILES):
        stem = fname.split(".")[0].lower().replace("_1", "").replace("_2", "")
        if stem.startswith(name) or name.startswith(stem):
            kind = "castle" if i < 4 else "towne"
            entry = (15, 30) if kind == "castle" else (1, 15)
            return i + 1, entry, kind
    return None


def _place_for_testing(game) -> None:
    """Debug aid for `--town`: stand the avatar next to a talkable NPC so Talk works
    immediately, and say which way to talk."""
    for npc in game.location.npcs:
        if npc.tlkidx == 0:
            continue
        for d in range(4):
            sx, sy = npc.x - DIR_DX[d], npc.y - DIR_DY[d]   # tile from which to face the NPC
            tile = game.location.tile_at(sx, sy)
            if tile is not None and is_walkable(tile) and game.location.npc_at(sx, sy) is None:
                game.party.x, game.party.y = sx, sy
                game.party.gold = 500                       # walking-around money for shops
                game.message(f"An NPC is {_DIR_WORD[d]} of you — press T then "
                             f"{_DIR_WORD[d][0]} to talk. (You have 500 gold.)")
                return


def main(which: str = "ega", town: str = None) -> None:
    pygame.init()
    W, H = VIEW * SCALE, VIEW * SCALE + PANEL_H
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("Ultima IV (Python port)")
    clock = pygame.time.Clock()

    A = Assets(which)
    game = Game()
    if town:                                         # debug boot: skip the title, drop into a town
        spot = find_town(town)
        if spot:
            loc_id, entry, kind = spot
            game._enter_location(loc_id, entry=entry, kind=kind)
            _place_for_testing(game)
    else:                                            # normal boot: the title + intro/launch sequence
        if not run_title(screen, which, game):
            pygame.quit()
            return
    game.message("Arrows=move  T=talk (+dir)  E=enter  Q=quit.")

    talk_buf = [""]            # mutable cell so nested draw()/handlers can see edits

    def draw(phase=0):
        draw_game(screen, A, game, phase, input_text=talk_buf[0])
    anim = 0
    running = True
    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type != pygame.KEYDOWN:
                continue
            # --- interaction mode (talk/shop): type a word, Enter submits, Esc leaves ---
            elif game.active is not None:
                if ev.key == pygame.K_RETURN:
                    word = talk_buf[0]; talk_buf[0] = ""
                    game.messages.clear()
                    game.feed(word)
                elif ev.key == pygame.K_ESCAPE:
                    talk_buf[0] = ""
                    game.messages.clear()
                    game.feed("")                 # empty line == leave/bye
                elif ev.key == pygame.K_BACKSPACE:
                    talk_buf[0] = talk_buf[0][:-1]
                elif ev.unicode and ev.unicode.isprintable():
                    talk_buf[0] += ev.unicode
            # --- normal mode: arrows move, letters are commands ---
            elif ev.key in (pygame.K_ESCAPE,):
                running = False
            elif ev.key in ARROWS:
                game.messages.clear()
                game.handle(ARROWS[ev.key])
            elif ev.unicode and ev.unicode.isalpha():
                game.messages.clear()
                game.handle(ev.unicode)
        if game.quit_requested:                         # Quit & Save (Q) -> draw the save msg, exit
            draw(anim // 4)
            pygame.time.wait(600)
            running = False
        # Redraw on the original's animation tick (int 0x1C, 18.2 Hz), not 60 fps. The DOS game
        # had no fixed frame rate: `speed_info` is a CPU-speed calibration (LOW.ASM busy-loop)
        # whose only job is to hold animation at a constant *real-time* rate on any machine. A
        # fixed 18.2 Hz tick is the modern equivalent; ~4-tick divisor = the gentle creature shuffle.
        anim += 1
        game.tick_moons()                               # moons run on this clock, not on movement
        draw(anim // 4)
        clock.tick(DOS_TIMER_HZ)
    pygame.quit()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:]]
    town = None
    if "--town" in args:
        ti = args.index("--town")
        town = args[ti + 1] if ti + 1 < len(args) else "britain"
        del args[ti:ti + 2]
    main(args[0] if args else "ega", town)
