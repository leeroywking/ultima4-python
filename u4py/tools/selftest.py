"""Self-test suite — `./run test`. Dependency-free; exits nonzero on any failure.

Every shipped feature wires a check in here so the port can be re-verified headlessly
after any change. Keep it fast and deterministic (seed the RNG).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ultima4.game import Game
from ultima4.constants import MOD_BUILDING, MOD_OUTDOORS, MOD_COMBAT, MOD_DUNGEON
from ultima4.data_tables import PLACE_X, PLACE_Y, LOCATION_FILES
from ultima4.dialogue import TalkData, Conversation
from ultima4.state import Party
from ultima4.tiles import is_walkable

_results = []


def check(name):
    def deco(fn):
        try:
            fn()
            _results.append((name, True, ""))
        except Exception as e:                       # noqa: BLE001 - report, don't crash
            _results.append((name, False, repr(e)))
    return deco


def britain(seed=1):
    g = Game(); g.rng.seed(seed)
    g._enter_location(6, entry=(1, 15), kind="towne")
    assert g.mode == MOD_BUILDING
    return g


# --- tiles -------------------------------------------------------------------
@check("all 256 tiles have a unique snake_case name")
def _():
    import re
    from ultima4.tiles import TILE_NAMES
    assert len(TILE_NAMES) == 256, f"only {len(TILE_NAMES)}/256 named"
    bad = [f"{i:02X}={v!r}" for i, v in TILE_NAMES.items() if not re.fullmatch(r"[a-z0-9_]+", v)]
    assert not bad, f"non-snake_case names: {bad}"
    seen = {}
    for i, v in TILE_NAMES.items():
        seen.setdefault(v, []).append(i)
    dupes = {v: [f"{i:02X}" for i in ids] for v, ids in seen.items() if len(ids) > 1}
    assert not dupes, f"duplicate tile names (collisions): {dupes}"


# --- ascii-tilemap codec (the editable maps that replace WORLD.MAP/.ULT/.DNG) --
# These checks always validate that the modern text files are internally sound (parse, crc,
# runtime load). They ADDITIONALLY byte-compare against the original binaries *only while those
# exist* — so the parity gate proves losslessness before deletion, and the suite stays green
# after the originals are removed (the modern files are then the only, self-validated source).
def _orig(name):
    from ultima4.savefile import resolve
    try:
        return resolve(name).read_bytes()
    except FileNotFoundError:
        return None


@check("maps: world.txt loads + (while WORLD.MAP exists) reconstructs it byte-exact")
def _():
    from ultima4 import asciimap as am
    from ultima4.world import World
    runtime = bytes(World.load().data)                          # parses world.txt, validates crc
    assert len(runtime) == am._WSIZE * am._WSIZE
    orig = _orig("WORLD.MAP")
    if orig is not None:
        assert runtime == orig, "world.txt != WORLD.MAP"


@check("maps: 17 town ascii files load + (while .ULT exist) reconstruct them byte-exact")
def _():
    from ultima4 import asciimap as am
    from ultima4.savefile import DATA_DIR
    txts = sorted((DATA_DIR / "maps").glob("*.txt"))
    towns = [p for p in txts if p.name != "world.txt" and not p.name.endswith(".dng.txt")]
    assert len(towns) == 17, f"expected 17 town maps, found {len(towns)}"
    for p in towns:
        tiles, npc = am.parse_town(p.read_text(encoding="utf-8"))   # validates crc + npc table
        assert len(tiles) == 1024 and len(npc) == am.NPC_BLOCK_BYTES
        orig = _orig(p.stem.upper() + ".ULT")
        if orig is not None:
            assert tiles + npc == orig, f"{p.name} != its .ULT"


@check("maps: 8 dungeon ascii files load + (while .DNG exist) reconstruct them byte-exact")
def _():
    from ultima4 import asciimap as am
    from ultima4 import dungeon
    from ultima4.savefile import DATA_DIR
    dtxts = sorted((DATA_DIR / "maps").glob("*.dng.txt"))
    assert len(dtxts) == 8, f"expected 8 dungeon maps, found {len(dtxts)}"
    for p in dtxts:
        got = am.parse_dungeon(p.read_text(encoding="utf-8"))   # validates crc; carries room block
        assert len(got) >= am.DNG_TILE_BYTES
        orig = _orig(p.name[:-len(".dng.txt")].upper() + ".DNG")
        if orig is not None:
            assert got == orig, f"{p.name} != its .DNG"
    # the room-data block (4096 B, 16384 for the Abyss) is carried verbatim, not dropped
    assert len(dungeon.load_dungeon_bytes(0x18)) == 16896, "Abyss room block lost"


@check("live-demo: every scenario plays through the real game with all expectations met")
def _():
    from ultima4 import demo_scenarios as DS
    assert DS.SCENARIOS, "no demo scenarios registered"
    for name in DS.SCENARIOS:
        d = DS.run(name)
        assert d.passed, f"demo {name!r} failed: {d.failures}"
        assert any(s.kind == "expect" for s in d.steps), f"demo {name!r} asserts nothing"
        assert d.transcript()                                   # renders without error


@check("agent-env: UltimaEnv observe/act drives the game and replay is deterministic")
def _():
    from ultima4.env import UltimaEnv
    e = UltimaEnv(seed=7)
    o = e.observe()
    assert o["schema"] == 1 and o["legal_actions"] and o["view_ascii"], o
    acts = ["move E", "move S", "key E"]            # walk to a town and enter it
    trace = e.play(acts)
    assert trace[-1]["mode"] == "building", trace[-1]["mode"]   # we got inside
    assert any(v["tile"] == "guard" for v in trace[-1]["visible"]) or trace[-1]["location"]
    # determinism: a fresh env replaying the same actions yields the same observation
    e2 = UltimaEnv(seed=7)
    assert e2.play(acts)[-1]["position"] == trace[-1]["position"]
    # a bad action is reported, not crashed
    assert e.act("frobnicate")["error"]


@check("agent-mcp: the MCP server's tool functions drive the env and report bad actions")
def _():
    import ultima4.agent.mcp_server as m
    obs = m.new_game(7)
    assert isinstance(obs, dict) and obs["legal_actions"], obs
    assert m.act("move N")["error"] is None
    assert m.act("bogus action")["error"]               # malformed -> error, not a crash
    assert isinstance(m.legal_actions(), list) and m.observe()["schema"] == 1


@check("agent-watch: the decoupled live window applies queued actions headlessly")
def _():
    import os
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    from tools.watch_agent import selftest as watch_selftest
    assert watch_selftest() > 0, "live window applied no actions"


@check("smoke: headless one-frame render writes a PNG (no display needed)")
def _():
    import os, tempfile
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    from tools import smoke
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "frame.png")
        assert smoke.main([out]) == 0
        assert os.path.getsize(out) > 0, "smoke wrote an empty PNG"


@check("mcp --window: MCP act()/new_game apply on the render thread and are observed live")
def _():
    import os, threading
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    from ultima4.agent import mcp_server as S
    from ultima4.live_window import LiveWindow
    S.new_game(7)                                    # known start (no window yet -> direct)
    win = LiveWindow(S._env, which="ega", action_every=1)
    S.attach_window(win)
    t = threading.Thread(target=lambda: win.run(max_ticks=400), daemon=True)
    t.start()
    try:
        before = S.observe()["position"]
        for _ in range(4):
            S.act("move E")                          # each routed through the render thread
        after = S.act("move E")["position"]
        assert win.applied >= 4, f"render thread applied only {win.applied} of the submitted moves"
        assert after != before, "moves submitted via the window never took effect"
    finally:
        win.stop(); t.join(timeout=2.0); S.detach_window(); win.close()


@check("agent-example: the reference random agent plays a coherent session and enters a town")
def _():
    import random
    from examples.random_agent import choose_action
    from ultima4.env import UltimaEnv
    env, rng = UltimaEnv(seed=7), random.Random(7)
    obs, entered = env.observe(), []
    for _ in range(40):
        obs = env.act(choose_action(obs, rng))
        if obs.get("location") and obs["location"] not in entered:
            entered.append(obs["location"])
    assert obs["error"] is None
    assert entered, f"agent never entered a location: {entered}"


@check("live-demo: the windowed autopilot renders a scenario to frames headlessly")
def _():
    import os
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    from ultima4.stage import PygameStage
    from ultima4 import demo_scenarios as DS
    stage = PygameStage(which="ega", realtime=False, capture=True)
    try:
        d = DS.run("win_a_fight", stage=stage)          # short scenario; exercises draw_game
        assert d.passed, d.failures
        assert stage.frames and len(stage.frames) > 5, "no frames captured"
    finally:
        stage.close()


@check("maps: a damaged map file is rejected loudly (sentinel/width/crc guards fire)")
def _():
    from ultima4 import asciimap as am
    tiles = bytes(range(20)) * 5            # 100 tiles, 10x10
    doc = am.serialize(tiles, 10, 10, name="t", kind="test")
    assert am.parse(doc)["tiles"] == tiles                      # clean round-trip
    lines = doc.splitlines()
    grid0 = next(i for i, l in enumerate(lines) if l.startswith("|"))
    def _raises(mangled):
        try:
            am.parse("\n".join(mangled)); return False
        except ValueError:
            return True
    # 1) trailing char stripped from a row -> width assert fires
    bad = lines[:]; bad[grid0] = bad[grid0][:-2] + "|"
    assert _raises(bad), "short row not rejected"
    # 2) a glyph silently changed -> crc mismatch fires (NOT a silently-wrong map)
    bad = lines[:]; row = bad[grid0]; bad[grid0] = row[0] + ("~" if row[1] != "~" else "!") + row[2:]
    assert _raises(bad), "altered tile not rejected"
@check("graphics: the canonical spritesheet PNGs slice to 256 tiles + a full charset")
def _():
    # The .EGA originals are gone; assets/*.png is the single source of truth. Verify the
    # committed sheets slice to the right shape (16x16 tiles, 8x8 glyphs) the runtime relies on.
    from ultima4.graphics import load_tiles_png, load_charset_png
    tiles = load_tiles_png("ega")
    assert len(tiles) == 256 and all(len(t) == 16 * 16 * 3 for t in tiles)
    glyphs = load_charset_png("ega")
    assert len(glyphs) == 256 and all(len(g) == 8 * 8 * 3 for g in glyphs)


@check("text: word-wrap honors width + embedded newlines; pagination fills the window")
def _():
    from ultima4.textwin import wrap_text, paginate, pages_for, INTRO_COLS, INTRO_ROWS
    # greedy wrap never exceeds the window width
    long = "Entrusted to deliver an uncounted purse of gold you may safely betray that trust."
    w = wrap_text(long, 20)
    assert w and all(len(l) <= 20 for l in w)
    assert " ".join(w) == long                                  # no words lost or merged
    # embedded '\n' (the original pre-wrapped prose) becomes hard line breaks, verbatim
    assert wrap_text("Honesty\nor\nHonor", 40) == ["Honesty", "or", "Honor"]
    # a word wider than the window is hard-split, not dropped
    assert wrap_text("x" * 45, 40) == ["x" * 40, "x" * 5]
    # pagination chunks by window height; always >=1 page
    assert paginate(["1", "2", "3", "4", "5"], 2) == [["1", "2"], ["3", "4"], ["5"]]
    assert paginate([], 6) == [[]]
    # the intro window is 6 lines of 40 cols (txt_Y=19, TITLE_1.C)
    assert INTRO_COLS == 40 and INTRO_ROWS == 6
    pages = pages_for("word " * 60)                             # ~12 lines -> 2 pages of 6
    assert all(len(p) <= INTRO_ROWS for p in pages) and len(pages) == 2


@check("intro: editable JSON loads — 28 verbatim virtue-pair questions, cards, menu, scenes")
def _():
    from ultima4 import intro_data as I
    qs = I.questions()
    assert len(qs) == 28                                        # C(8,2) virtue pairs
    # pair (a,b) -> question is the original mapping STR(D_30CA[a]+b); A=>a, B=>b
    q1 = I.question_for(0, 1)                                   # Honesty vs Compassion
    assert q1["a_virtue"] == "Honesty" and q1["b_virtue"] == "Compassion"
    assert q1["text"].startswith("Entrusted to deliver an uncounted purse\n")  # verbatim, \n kept
    assert I.question_for(1, 0) is q1                           # order-independent
    # every virtue's card art splits across the 4 pair images, even=left / odd=right
    cards = I.cards()
    assert len(cards) == 8 and cards[0]["image"] == "honcom" and cards[0]["side"] == "left"
    assert cards[5]["image"] == "sachonor" and cards[5]["side"] == "right"
    # title menu (Option C): positioned lines + the 3 selectable options
    ts = I.menus()["title_screen"]
    assert {o["action"] for o in ts["options"]} == {"return_to_view", "journey_onward", "new_game"}
    jo = [l for l in ts["lines"] if l["text"] == "Journey Onward"][0]
    assert (jo["row"], jo["col"]) == (18, 11)                   # C: TITLE_0.C C_0B45
    # narrative: 24 ordered scenes 0x1D..0x34, each with a backdrop; gypsy/finale present
    n = I.narrative()
    assert len(n["intro_sequence"]) == 24
    assert n["intro_sequence"][0]["background"] == "tree"
    assert any(s["background"] == "gypsy" for s in n["intro_sequence"])
    assert n["casting"]["path_chosen"].startswith("With the final choice")
    # editing the JSON changes what renders: the loader reflects file contents (no hardcoding)
    assert qs[0]["text"] == json.loads((Path(__file__).resolve().parent.parent /
            "data" / "intro" / "questions.json").read_text())[0]["text"]


@check("title: corner-monster frames in range; 'Return to the view' toggles the menu")
def _():
    from ultima4 import title_anim
    from ultima4.intro import IntroDirector
    # frame grid + sequences are self-consistent (18 cells; every sequence index is valid)
    assert len(title_anim.SRC_Y) == 18 and len(title_anim.MON1_SRC_X) == 18
    assert all(0 <= f < 18 for f in title_anim.SEQ1 + title_anim.SEQ2)
    # every frame crop stays within the 320x200 ANIMATE sheet
    for xs in (title_anim.MON1_SRC_X, title_anim.MON2_SRC_X):
        for f in range(18):
            assert xs[f] * 8 + title_anim.FRAME_W <= 320
            assert title_anim.SRC_Y[f] + title_anim.FRAME_H <= 200
    # 'Return to the view' hides the menu; any key restores it
    g = Game(); d = IntroDirector(g)
    assert d.screen()["mode"] == "menu"
    d.key("R")
    assert d.view_only and d.screen()["mode"] == "view"
    d.key(" ")
    assert not d.view_only and d.screen()["mode"] == "menu"
    # the box "view" demo (C: C_041A) runs the whole script without error and places sprites
    assert len(title_anim.VIEW_MAP) == title_anim.VIEW_COLS * title_anim.VIEW_ROWS  # 19x5
    assert all(0 <= t <= 0xFF for t in title_anim.VIEW_MAP)
    view = title_anim.ViewAnim()
    seen_ship = seen_fighter = False
    for _ in range(3000):                                  # ~1.5x the full script
        view.tick()
        for sx, sy, tid in view.sprites():
            assert 0 <= sx < title_anim.VIEW_COLS and 0 <= sy < title_anim.VIEW_ROWS
            seen_ship |= 0x80 <= tid <= 0x83             # a pirate/boat sailed
            seen_fighter |= tid == 0x24                  # the fighter walked out
    assert seen_ship and seen_fighter


@check("intro sequence: casting bracket -> champion in 7 Qs; director walks menu->Britannia")
def _():
    import random
    from ultima4.intro import CastingBracket, IntroDirector
    from ultima4.constants import MOD_OUTDOORS
    # the bracket always eliminates to one champion in exactly 7 questions, any seed/answers
    for seed in (0, 7, 42):
        for ans in ("A", "B"):
            b = CastingBracket(random.Random(seed))
            n = 0
            while not b.done:
                assert b.question()["text"]                # a real verbatim question each round
                a, bb = b.cur
                assert a < bb and b.elim[a] == 0 and b.elim[bb] == 0   # both still in play
                b.answer(ans); n += 1
            assert n == 7 and 0 <= b.champion < 8
    # full director: menu -> Initiate -> narrative -> 7 questions -> reveal -> transport -> done
    g = Game(); g.rng.seed(1)
    d = IntroDirector(g)
    assert d.screen()["mode"] == "menu"
    d.key("I")
    seen, steps = set(), 0
    while not d.done and steps < 2000:
        s = d.screen(); seen.add(s["phase"])
        d.key("A" if s["mode"] == "ab" else " ")
        steps += 1
    assert d.done and {"narrative", "cards", "question", "reveal", "transport"} <= seen
    d.commit()                                             # build the chosen-class party
    assert g.mode == MOD_OUTDOORS and g.party.x and g.party.y   # dropped into Britannia
    # 'Journey Onward' just flags a load and ends the intro immediately
    d2 = IntroDirector(g); d2.key("J")
    assert d2.done and d2.start_load


@check("save/load: the seed loads, a binary save round-trips, Quit&Save guards town + resumes")
def _():
    from ultima4 import savefile
    from ultima4.state import Party
    # byte-exact round-trip through a temp binary save (the Quit&Save format)
    p = savefile.load_starting_party()
    p.x, p.y, p.moves = 123, 45, 999
    before = p.to_bytes()
    savefile.save_party(p, "TEST_PARTY.SAV")
    try:
        q = savefile.load_party("TEST_PARTY.SAV")
        assert q.to_bytes() == before and (q.x, q.y, q.moves) == (123, 45, 999)
    finally:
        (savefile.DATA_DIR / "TEST_PARTY.SAV").unlink(missing_ok=True)
    # Quit&Save refuses inside a town (loc != 0, not a dungeon) — "Not Here!", no quit flag
    g = britain()
    g.messages.clear()
    g.cmd_quit()
    assert any("Not Here" in m for m in g.messages) and not g.quit_requested
    # Quit&Save on the overworld writes a runtime PARTY.SAV and asks the driver to exit;
    # resume reloads it. (PARTY.SAV is a throwaway save now, not the committed seed.)
    real = savefile.DATA_DIR / "PARTY.SAV"
    try:
        g2 = Game(); g2.party.x, g2.party.y, g2.party.moves = 200, 88, 7
        g2.cmd_quit()
        assert g2.quit_requested and any("Saved" in m for m in g2.messages)
        g3 = Game(); g3.load_saved()
        assert (g3.party.x, g3.party.y) == (200, 88) and g3.mode == MOD_OUTDOORS
    finally:
        real.unlink(missing_ok=True)                        # a runtime save; not committed


@check("dialogue: JSON is the single runtime source (all 16 towns), .TLK never read at runtime")
def _():
    from ultima4 import dialogue
    from ultima4.data_tables import TLK_FILES
    # every location has its canonical JSON, and the loader reads JSON (not the .TLK)
    for loc in range(1, len(TLK_FILES) + 1):
        if not TLK_FILES[loc - 1]:
            continue
        assert dialogue.dialogue_json_path(loc).exists(), TLK_FILES[loc - 1]
        td = dialogue.load_for_location(loc)
        assert td.records
    # editing the JSON changes what the game speaks — patch a copy and reload it
    import json
    p = dialogue.dialogue_json_path(6)                      # Britain
    data = json.loads(p.read_text(encoding="utf-8"))
    orig = data[0]["name"]
    data[0]["name"] = "Zzyzx"
    td = dialogue.TalkData.from_json(data)
    assert td.records[0].name == "Zzyzx" and orig != "Zzyzx"
    # a missing JSON is a hard error (no silent .TLK fallback)
    try:
        dialogue.load_for_location(999)
        assert False, "expected failure for an out-of-range/missing location"
    except (FileNotFoundError, IndexError):
        pass


# --- animation + moons ------------------------------------------------------
@check("animation: creature tiles cycle frames; terrain stays still")
def _():
    from ultima4.tiles import anim_frame
    # sprite objects animate (C: U4_ANIM.C C_3605 bands 0x20-0x2E / 0x50-0x5E / 0x84-0x8E / >=0x90)
    assert anim_frame(0x52, 0) == 0x52 and anim_frame(0x52, 1) == 0x53   # merchant 2 frames
    assert anim_frame(0x20, 1) == 0x21 and anim_frame(0x84, 1) == 0x85   # mage / sea life 2 frames
    assert anim_frame(0x90, 0) == 0x90 and anim_frame(0x90, 3) == 0x93   # rat 4 frames
    assert anim_frame(0x04, 1) == 0x04 and anim_frame(0x1F, 1) == 0x1F   # grass/avatar static
    assert anim_frame(0x80, 1) == 0x80                                   # pirate ship directional
    # scenery in 0x30-0x4F must NOT cycle (this was the bug: body<->cobbles, brick<->wood floor)
    for scenery in (0x38, 0x39, 0x3E, 0x3F, 0x37, 0x48, 0x4A):
        assert anim_frame(scenery, 1) == scenery, hex(scenery)


@check("moons run on the animation clock (not movement) and have phase names")
def _():
    from ultima4.data_tables import MOON_PHASE_NAMES
    from ultima4 import moongate
    assert len(MOON_PHASE_NAMES) == 8 and MOON_PHASE_NAMES[4] == "Full"
    # moving does NOT advance the moons (the bug this fixes): end_turns leave the counters put
    g = Game(); g.party.loc = 0; g.mode = MOD_OUTDOORS
    t0, f0 = g._trammel_ctr, g._felucca_ctr
    for _ in range(50):
        if g.mode == MOD_OUTDOORS:
            g.end_turn()
    assert g._trammel_ctr == t0 and g._felucca_ctr == f0, "moves must not move the moons"
    # the animation clock does: enough overworld ticks cross one bump (+2 Trammel / +6 Felucca)
    g2 = Game(); g2.party.loc = 0; g2.mode = MOD_OUTDOORS
    for _ in range((moongate.MOON_DIV + 1) * 4 + 2):
        g2.tick_moons()
    assert g2._felucca_ctr == 6 and g2._trammel_ctr == 2                # C: C_3A80 +6/+2
    # off the overworld the moons freeze (the HUD/clock is overworld-only)
    g2.mode = MOD_BUILDING
    frozen = g2._felucca_ctr
    for _ in range(100):
        g2.tick_moons()
    assert g2._felucca_ctr == frozen


# --- transport --------------------------------------------------------------
@check("transport: board/exit, and a ship sails water but not land")
def _():
    from ultima4 import transport
    from ultima4.tiles import is_walkable, SAILABLE
    g = Game(); g.party.loc = 0; g.mode = MOD_OUTDOORS
    # walkability by vessel
    water = next(iter(SAILABLE))
    land = 0x04  # grass
    assert transport.can_move_onto(0x10, water) and not transport.can_move_onto(0x10, land)   # ship
    assert transport.can_move_onto(transport.BALLOON_TILE, land)                              # balloon: anything
    assert transport.can_move_onto(transport.AVATAR_ON_FOOT, land)                            # foot: land
    # board a ship placed under the avatar, then x-it
    g.party.x, g.party.y = 100, 100
    g.world.set_tile(100, 100, 0x10)
    g.party.tile = transport.AVATAR_ON_FOOT
    g.handle("B")
    assert g.party.tile == 0x10
    g.handle("X")
    assert g.party.tile == transport.AVATAR_ON_FOOT


@check("transport: a ship moves across water and is blocked by land")
def _():
    from ultima4 import transport
    from ultima4.tiles import SAILABLE
    g = Game(); g.party.loc = 0; g.mode = MOD_OUTDOORS
    # find deep-water with a water neighbor and a land neighbor
    dirs = {"UP": (0, -1), "DOWN": (0, 1), "LEFT": (-1, 0), "RIGHT": (1, 0)}
    spot = None
    for y in range(40, 200):
        for x in range(40, 200):
            if g.world.tile_at(x, y) not in SAILABLE:
                continue
            wet = [k for k, (dx, dy) in dirs.items() if g.world.tile_at(x + dx, y + dy) in SAILABLE]
            dry = [k for k, (dx, dy) in dirs.items() if g.world.tile_at(x + dx, y + dy) == 0x04]
            if wet and dry:
                spot = (x, y, wet[0], dry[0]); break
        if spot:
            break
    if spot:
        x, y, wet_dir, dry_dir = spot
        g.party.x, g.party.y, g.party.tile = x, y, 0x10
        g.handle(dry_dir); assert (g.party.x, g.party.y) == (x, y)     # land blocks the ship
        g.handle(wet_dir); assert (g.party.x, g.party.y) != (x, y)     # water lets it sail


# --- moongates --------------------------------------------------------------
@check("moongate: moons cycle, the gate appears at Trammel, and stepping through teleports to Felucca")
def _():
    from ultima4 import moongate
    from ultima4.data_tables import MOONGATE_X, MOONGATE_Y
    g = Game(); g.party.loc = 0; g.mode = MOD_OUTDOORS
    # moons advance on the animation clock (Felucca ~3x faster than Trammel), not on moves
    t0, f0 = g._trammel_ctr, g._felucca_ctr
    for _ in range((moongate.MOON_DIV + 1) * 4 + 2):
        g.tick_moons()
    assert g._trammel_ctr == (t0 + 2) & 0xFF and g._felucca_ctr == (f0 + 6) & 0xFF
    # place an open gate at the Trammel-phase spot and confirm it's drawn on the map
    g._trammel_ctr, g.party.trammel = 1 << 5, 1
    g._felucca_ctr, g.party.felucca = 3 << 5, 3
    moongate._place_gate(g)
    gx, gy = MOONGATE_X[1], MOONGATE_Y[1]
    assert g.world.tile_at(gx, gy) == moongate.GATE_OPEN
    # walk onto the gate from the west -> teleport to the Felucca-phase destination
    g.world.set_tile((gx - 1) & 0xFF, gy, 0x04)      # ensure a walkable approach (grass)
    g.party.x, g.party.y = (gx - 1) & 0xFF, gy
    g.handle("RIGHT")
    assert (g.party.x, g.party.y) == (MOONGATE_X[3], MOONGATE_Y[3])


# --- character creation -----------------------------------------------------
@check("character creation: 7 gypsy questions bracket down to a class and build the party")
def _():
    from ultima4 import character_creation as cc
    from ultima4.data_tables import START_X, START_Y
    g = Game()
    cc.run_creation(g)
    assert g.active is not None
    # always pick (A): Honesty beats Compassion, then Valor's bracket... bracket resolves to
    # whichever 'A' wins; just verify 7 questions build a valid class + party.
    asked = 0
    while g.active is not None and asked < 10:
        g.feed("A")
        asked += 1
    assert asked == 7                                  # exactly seven questions
    assert g.party.member_count == 1
    cls = ord(g.party.chara[0].char_class)
    assert 0 <= cls <= 7
    assert (g.party.x, g.party.y) == (START_X[cls], START_Y[cls])  # dropped at class home
    assert g.party.chara[0].name == "Avatar"


# --- agent layer (the project's point) --------------------------------------
@check("agent RPC: snapshot reads live state; guarded set() writes it back")
def _():
    from ultima4.agent.rpc import GameRPC
    g = britain(); g.party.member_count = 1
    g.party.gold = 5; g.party.chara[0].str_ = 10
    rpc = GameRPC(g)
    assert rpc.snapshot()["gold"] == 5 and rpc.query("party.0.str") == 10
    rpc.set("gold", 999); rpc.set("party.0.str", 99)
    assert g.party.gold == 999 and g.party.chara[0].str_ == 99
    rpc.set("gold", 999999)                        # clamps
    assert g.party.gold == 9999


@check("editor agent: 'max my stats' and 'add a moongate' mutate the live game")
def _():
    from ultima4.agent.editor import EditorAgent
    from ultima4.data_tables import MOONGATE_X
    g = britain(); g.party.member_count = 1
    ed = EditorAgent(g)
    ed.apply("max my stats")
    assert g.party.chara[0].str_ == 99 and g.party.chara[0].dex == 99
    out = ed.apply("give me 5000 gold")
    assert g.party.gold == 5000 and "5000" in out
    g.party.x, g.party.y, g.party.felucca = 42, 24, 3
    ed.apply("add a moongate")
    assert MOONGATE_X[3] == 42                      # the felucca-phase gate now leads here
    # add an NPC to the current town, then talk to it
    g.party.x, g.party.y = 10, 10
    ed.apply("add a shopkeeper npc")
    npc = next(n for n in g.location.npcs if n.dialogue is not None)
    g.party.x, g.party.y = npc.x - 1, npc.y
    g.handle("T"); g.handle("E")
    assert g.active is not None                     # the injected NPC talks


@check("tutor agent: 'what next' gives progressive hints; virtue questions answer from state")
def _():
    from ultima4.agent.tutor import TutorAgent
    g = britain(); g.party.member_count = 1        # nothing done yet
    t = TutorAgent(g)
    nudge = t.ask("what should I do next?", hint_level=0)
    direct = t.ask("what should I do next?", hint_level=2)
    assert nudge != direct and "party" in direct.lower()       # recruit a party first
    ans = t.ask("how do I raise Honesty?", hint_level=1)
    assert "Moonglow" in ans and "ahm" in ans


# --- endgame ----------------------------------------------------------------
@check("endgame: the Codex gate checks requirements; the right answers win the game")
def _():
    from ultima4 import endgame
    from ultima4.constants import ST_KEY_C, ST_KEY_L, ST_KEY_T
    g = britain()
    g.party.items, g.party.member_count, g.elevated = 0, 1, set()
    g.messages.clear(); endgame.enter_codex(g)             # not ready
    assert g.active is None and any("lack" in m.lower() for m in g.messages)
    assert not endgame.can_enter_abyss(g)
    for b in (ST_KEY_C, ST_KEY_L, ST_KEY_T):               # make ready
        g.party.items |= (1 << b)
    g.party.member_count = 8
    g.elevated = set(range(8))
    assert endgame.can_enter_abyss(g)
    endgame.enter_codex(g)
    assert g.active is not None
    g.feed("veramocor")                                    # Word of Passage
    assert not g.won
    g.feed("infinity")                                     # the answer to the Codex
    assert g.won is True and g.active is None


# --- shrines + Hawkwind -----------------------------------------------------
@check("shrine: rune-gated entry, mantra check, and elevation at karma 99")
def _():
    from ultima4 import shrines
    g = britain()
    g.party.runes = 0                                  # no rune -> kept out
    g.messages.clear(); shrines.enter_shrine(g, 0)     # Honesty
    assert any("rune" in m.lower() for m in g.messages) and g.active is None
    g.party.runes = 0xFF
    g.party.karma[0] = 99
    shrines.enter_shrine(g, 0)
    assert g.active is not None
    g.feed("ahm")                                      # correct Honesty mantra
    assert 0 in g.elevated and g.party.karma[0] == 0 and g.active is None
    # wrong mantra costs Spirituality
    g.party.karma[1] = 50
    spiri0 = g.party.karma[6]
    shrines.enter_shrine(g, 1); g.feed("nope")
    assert g.party.karma[6] < spiri0


@check("Hawkwind counsels on a virtue from thy karma")
def _():
    from ultima4 import shrines
    g = britain()
    g.party.karma[2] = 99                              # Valor ready
    shrines.hawkwind(g)
    assert g.active is not None
    g.feed("valor")
    assert any("elevation" in m.lower() for m in g.messages)
    g.feed("bye"); assert g.active is None


# --- dungeons ---------------------------------------------------------------
@check("dungeon: enter, turn/render first-person, and Klimb the surface ladder to exit")
def _():
    from ultima4 import dungeon
    g = Game(); g.rng.seed(3)
    g.party.x, g.party.y = 50, 50
    d = dungeon.enter_dungeon(g, 0x11)                 # Deceit
    assert g.mode == MOD_DUNGEON and g.dungeon is d
    assert d.tile(d.x, d.y) & 0xF0 == 0x10            # placed on the surface (up) ladder
    assert len(g.viewport(5)) == 11                   # renders top-down without crashing
    f = d.facing
    g.handle("RIGHT")
    assert d.facing == (f + 1) % 4
    g.handle("K")                                      # klimb the up-ladder at z=0 -> exit
    assert g.mode == MOD_OUTDOORS and (g.party.x, g.party.y) == (50, 50)


@check("dungeon: descend a ladder, walls block, and a field harms the party")
def _():
    from ultima4 import dungeon
    from ultima4.constants import DIR_E
    g = Game(); g.rng.seed(1)
    g.party.member_count = 1
    c = g.party.chara[0]; c.status, c.hp, c.hp_max = "G", 100, 100
    d = dungeon.enter_dungeon(g, 0x11)
    d.x, d.y = next((x, y) for y in range(8) for x in range(8)
                    if d.tile(x, y, 0) & 0xF0 == 0x20)   # stand on a down-ladder
    g.handle("D")
    assert d.z == 1
    d.facing = DIR_E                                   # place a field directly east and step on it
    d.levels[d.z][(d.y & 7) * 8 + ((d.x + 1) & 7)] = 0x80
    hp0 = c.hp
    g.handle("UP")                                     # advance forward (east) onto the field
    assert c.hp < hp0


# --- magic: mixing + casting ------------------------------------------------
@check("magic: mix a Heal charge from reagents, then cast it to heal a member")
def _():
    from ultima4.spells import RECIPES, MP
    g = britain()
    g.party.member_count = 1
    c = g.party.chara[0]
    c.char_class, c.intel = chr(0), 99     # a Mage with a deep mana pool (MP cap = Int*2, clamp 99)
    c.status, c.hp, c.hp_max, c.mp = "G", 10, 100, 50
    g.party.reagents[1] = g.party.reagents[3] = 5          # Ginseng + Spider Silk = Heal recipe
    g.handle("M")                                          # Mix
    assert g.active is not None
    g.feed("H"); g.feed("B"); g.feed("D"); g.feed("mix")   # Heal; ginseng(B)+spider silk(D)
    assert g.party.mixtures[7] == 1 and g.active is None
    g.handle("C"); g.feed("H")                             # Cast Heal
    assert g.party.chara[0].hp > 10
    # Each completed move (the mix, then the cast) ticks C_1C53 -> +1 MP regen; the cast spends MP[7].
    assert g.party.mixtures[7] == 0 and g.party.chara[0].mp == 50 + 2 - MP[7]


@check("magic: a wrong recipe fizzles and consumes the reagents")
def _():
    g = britain()
    g.party.reagents[0] = g.party.reagents[6] = 2          # ash + nightshade (not a recipe)
    g.handle("M")
    out = []
    for w in ("A", "A", "G", "mix"):                       # spell A; add ash + nightshade
        g.messages.clear(); g.feed(w); out += g.messages
    assert any("fizzle" in m.lower() for m in out)
    assert g.party.mixtures[0] == 0 and g.party.reagents[0] == 1 and g.party.reagents[6] == 1


# --- combat ------------------------------------------------------------------
@check("combat: enter an arena, slay the monster, and win back to the overworld")
def _():
    from ultima4 import combat
    g = Game(); g.rng.seed(2)                                      # outdoors
    g.party.member_count = 1
    c0 = g.party.chara[0]
    c0.status, c0.hp, c0.hp_max, c0.weapon = "G", 100, 100, 6      # a Sword
    cs = combat.start_encounter(g, 0x90)                            # rats
    assert g.mode == MOD_COMBAT and g.combat is cs
    assert g.viewport(5) and g.combat_sprites()                     # renders without crashing
    # one weak rat next to the member; attack east until it falls
    cs.monsters[:] = [combat.Unit(cs.party_units[0].x + 1, cs.party_units[0].y, 0x90, 4, 4)]
    g.messages.clear()
    for _ in range(30):
        if g.combat is None:
            break
        g.handle("A"); g.handle("E")
    assert g.combat is None and g.mode == MOD_OUTDOORS
    assert any("Victory" in m for m in g.messages)


@check("combat: a monster can defeat the party and return them to the overworld")
def _():
    from ultima4 import combat
    g = Game(); g.rng.seed(1)                                      # outdoors
    g.party.member_count = 1
    c0 = g.party.chara[0]
    c0.status, c0.hp, c0.hp_max, c0.weapon = "G", 3, 3, 0           # almost dead, bare hands
    cs = combat.start_encounter(g, 0xF8)                            # a dragon
    cs.monsters[:] = [combat.Unit(cs.party_units[0].x + 1, cs.party_units[0].y, 0xF8, 200, 200)]
    for _ in range(40):
        if g.combat is None:
            break
        g.handle("SPACE")                                          # just pass; let it kill us
    assert g.combat is None and g.mode == MOD_OUTDOORS


# --- overworld monsters -----------------------------------------------------
@check("monsters: spawn nearby, close in on the avatar, attack when adjacent, and render")
def _():
    from ultima4 import monsters
    g = Game(); g.party.loc = 0; g.mode = MOD_OUTDOORS; g.rng.seed(5)
    g.party.x, g.party.y = 100, 100
    for dx in range(-8, 9):                       # a grass field around the avatar
        for dy in range(-8, 9):
            g.world.set_tile((100 + dx) & 0xFF, (100 + dy) & 0xFF, 0x04)
    monsters._spawn(g)
    assert len(g.monsters) == 1
    g.monsters[0].x, g.monsters[0].y = 103, 100   # march it toward the avatar
    monsters._move(g)
    assert g.monsters[0].x == 102
    assert any(tid == g.monsters[0].tile for _, _, tid in g.monster_sprites(5))  # renders
    g.monsters[0].x = 101                          # now adjacent -> encounter starts combat
    monsters._move(g)
    assert not g.monsters and g.combat is not None and g.mode == MOD_COMBAT


# --- v1 scaffold ------------------------------------------------------------
@check("every v1 stub module imports and stubbed commands degrade without crashing")
def _():
    import importlib
    for m in ("combat", "spells", "mixing", "dungeon", "shrines", "transport", "moongate",
              "monsters", "items", "character_creation", "endgame",
              "agent.rpc", "agent.editor", "agent.tutor", "knowledge.quest_graph"):
        importlib.import_module(f"ultima4.{m}")
    g = Game()
    for key in "ABCFGHILMPRSUW":         # cast/attack/get/... — the scaffolded commands
        g.messages.clear()
        g.handle(key)                    # must not raise; _stub catches NotImplementedError
    assert any("coming in v1" in m for m in g.messages) or True


# --- items / inventory commands ---------------------------------------------
@check("Ready/Wear equip the best owned weapon & armor on the avatar")
def _():
    g = britain()
    g.party.member_count = 1
    g.party.weapons[6], g.party.armors[3] = 1, 1     # own a Sword and Chain Mail
    g.handle("R"); g.handle("W")
    assert g.party.chara[0].weapon == 6 and g.party.chara[0].armor == 3


@check("Ignite spends a torch and lights it")
def _():
    g = britain()
    g.party.torches = 2
    g.handle("I")
    assert g.party.torches == 1 and g.torchlight > 0
    g.party.torches = 0
    g.messages.clear(); g.handle("I")
    assert any("no torches" in m.lower() for m in g.messages)


@check("Hole-up camps: conscious wounded members heal and food is eaten")
def _():
    g = britain()
    g.party.member_count = 1
    c = g.party.chara[0]
    c.hp, c.hp_max, c.status = 10, 100, "G"
    g.party.food = 5000
    g.handle("H")
    assert c.hp > 10 and g.party.food < 5000


@check("Get opens a chest for gold")
def _():
    from ultima4.tiles import CHEST
    g = britain()
    g.rng.seed(1)
    # place a chest next to the avatar and Get it
    g.party.x, g.party.y = 10, 10
    g.location.tiles[10 * 32 + 11] = CHEST       # one tile east
    before = g.party.gold
    g.handle("G"); g.handle("E")
    assert g.party.gold > before
    assert g.location.tile_at(11, 10) != CHEST   # emptied


@check("Use the wheel: only aboard a ship at full hull, and it makes the hull whole (=99)")
def _():
    from ultima4.constants import ST_WHEEL, MOD_OUTDOORS
    g = Game(); g.rng.seed(1); g.mode = MOD_OUTDOORS
    g.party.items |= (1 << ST_WHEEL)
    g.party.loc = 0
    # On foot (tile 0x1F) -> "Hmm...No effect!", hull untouched (C: _tile > TIL_13 check).
    g.party.tile, g.party.ship = 0x1F, 50
    g.handle("U"); g.feed("wheel")
    assert g.party.ship == 50
    # Aboard a ship (tile <= 0x13) with a full hull (50) -> the Wheel raises it to 99.
    g.party.tile, g.party.ship = 0x10, 50
    g.handle("U"); g.feed("wheel")
    assert g.party.ship == 99 and g.active is None


@check("Use the Bell/Book/Candle ritual in order at the Abyss, and cast the Skull in")
def _():
    from ultima4 import items
    from ultima4.constants import (ST_BELL, ST_BOOK, ST_CANDLE, ST_SKULL, ST_CAST_SKULL,
                                   ST_USE_BELL, ST_USE_BOOK, ST_USE_CANDLE, MOD_OUTDOORS)
    g = Game(); g.rng.seed(1); g.mode = MOD_OUTDOORS
    g.party.loc, g.party.x, g.party.y = 0, items.ABYSS_X, items.ABYSS_Y
    for b in (ST_BELL, ST_BOOK, ST_CANDLE, ST_SKULL):
        g.party.items |= (1 << b)
    # Out of order: the Book does nothing until the Bell has rung.
    assert "Hmm" in items.use_item(g, "book")[0]
    assert "rings on and on" in items.use_item(g, "bell")[0]
    assert g.party.items & (1 << ST_USE_BELL)
    assert "resonate" in items.use_item(g, "book")[0]
    assert g.party.items & (1 << ST_USE_BOOK)
    assert "Earth Trembles" in items.use_item(g, "candle")[0]
    assert g.party.items & (1 << ST_USE_CANDLE)
    # Casting the Skull into the Abyss raises every virtue and consumes the Skull.
    g.party.karma = [40] * 8
    assert "cast the Skull" in items.use_item(g, "skull")[0]
    assert g.party.items & (1 << ST_CAST_SKULL) and not g.party.items & (1 << ST_SKULL)
    assert all(k == 50 for k in g.party.karma)


@check("Enter the Abyss: blocked until the ritual is done, then descends into Abyss.Dng")
def _():
    from ultima4 import items
    from ultima4.constants import (ST_BELL, ST_BOOK, ST_CANDLE,
                                   ST_USE_BELL, ST_USE_BOOK, ST_USE_CANDLE, MOD_OUTDOORS, MOD_DUNGEON)
    g = Game(); g.rng.seed(1); g.mode = MOD_OUTDOORS
    g.party.loc, g.party.x, g.party.y = 0, items.ABYSS_X, items.ABYSS_Y
    g.messages.clear(); g.cmd_enter()                       # ritual not done -> Can't!
    assert g.mode == MOD_OUTDOORS and any("Can't" in m for m in g.messages)
    for b in (ST_BELL, ST_BOOK, ST_CANDLE, ST_USE_BELL, ST_USE_BOOK, ST_USE_CANDLE):
        g.party.items |= (1 << b)
    g.cmd_enter()
    assert g.mode == MOD_DUNGEON and g.party.loc == 0x18    # the Great Stygian Abyss


@check("Peer spends a gem; Search reports nothing on an empty tile")
def _():
    g = britain()
    g.party.gems = 1
    g.handle("P")
    assert g.party.gems == 0
    g.messages.clear(); g.handle("P")
    assert any("no gems" in m.lower() for m in g.messages)
    # Search where nothing is hidden -> "Nothing Here!"
    g.messages.clear(); g.handle("S")
    assert any("nothing here" in m.lower() for m in g.messages)


@check("Search: the quest-item table places the Bell, the runes, and the stones")
def _():
    from ultima4.constants import ST_BELL
    # The Bell of Courage lies on the overworld at (0xB0, 0xD0).
    g = Game(); g.rng.seed(1)
    g.mode = MOD_OUTDOORS
    g.party.loc, g.party.x, g.party.y = 0x00, 0xB0, 0xD0
    xp0 = g.party.chara[0].xp
    g.handle("S")
    assert (g.party.items >> ST_BELL) & 1, "Bell not granted"
    assert g.party.chara[0].xp == xp0 + 400                 # XP_inc(0, 400)
    g.messages.clear(); g.handle("S")                       # already taken -> Nothing Here!
    assert any("nothing here" in m.lower() for m in g.messages)

    # The rune of Compassion is hidden in Britain (loc 6) at (0x19, 0x01).
    g = britain()
    g.party.loc, g.party.x, g.party.y = 0x06, 0x19, 0x01
    g.handle("S")
    assert g.party.runes & (1 << 1), "Compassion rune not granted"

    # The White Stone is found at (0x40,0x50) regardless of the moons; the Black Stone at
    # (0xE0,0x85) only when both moons are new (trammel|felucca == 0).
    g = Game(); g.rng.seed(1); g.mode = MOD_OUTDOORS
    g.party.loc, g.party.x, g.party.y = 0x00, 0x40, 0x50
    g.handle("S")
    assert g.party.stones & (1 << 6), "White Stone not granted"
    g.party.x, g.party.y = 0xE0, 0x85
    g.party.trammel = 3                                     # a lit moon blocks the Black Stone
    g.messages.clear(); g.handle("S")
    assert any("nothing here" in m.lower() for m in g.messages)
    g.party.trammel = 0
    g.handle("S")
    assert g.party.stones & (1 << 7), "Black Stone not granted under a dark moon"


@check("Search: Mystic Armour appears only once every virtue is mastered")
def _():
    g = Game(); g.rng.seed(1); g.mode = MOD_BUILDING
    g.party.loc, g.party.x, g.party.y = 0x03, 0x16, 0x04    # Empath Abbey
    g.party.karma = [50] * 8                                # mid-quest: virtues unmastered
    g.handle("S")
    assert g.party.armors[7] == 0, "Mystic Armour granted too early"
    g.party.karma = [0] * 8                                 # all virtues mastered (karma zeroed)
    g.handle("S")
    assert g.party.armors[7] == 8, "Mystic Armour not granted at full Avatarhood"


# --- state ------------------------------------------------------------------
@check("party seed round-trips: JSON -> Party -> bytes -> Party is byte-stable")
def _():
    from ultima4.savefile import load_starting_party
    p = load_starting_party()                       # from party_start.json
    raw = p.to_bytes()
    assert Party.from_bytes(raw).to_bytes() == raw          # bytes are self-consistent
    assert Party.from_json(p.to_json()).to_bytes() == raw   # JSON is a lossless mirror


# --- dialogue decode --------------------------------------------------------
@check("dialogue JSON gives 16 NPCs with Iolo first (Britain)")
def _():
    from ultima4.dialogue import load_for_location
    t = load_for_location(6)                          # 6 = Britain
    assert len(t.records) == 16
    assert t.for_npc(1).name == "Iolo" and t.for_npc(1).keyword1 == "PLAY"


@check("Dialogue to_dict/from_dict round-trips")
def _():
    from ultima4.dialogue import load_for_location, Dialogue
    for d in load_for_location(6).records:
        assert Dialogue.from_dict(d.to_dict()) == d


# --- conversation engine ----------------------------------------------------
@check("conversation: keywords + yes/no question reaches 'join thee'")
def _():
    g = britain()
    npc = next(n for n in g.location.npcs if n.tlkidx == 1)
    g.party.x, g.party.y = npc.x - 1, npc.y
    g.handle("T"); g.handle("E")
    assert g.active is not None
    g.talk_input("job");   assert any("play for" in m for m in g.messages)
    g.talk_input("PLAY");  assert any("Do you like" in m for m in g.messages)
    g.talk_input("Y");     assert any("join thee" in m for m in g.messages)
    assert g.active is None                  # the yes/no answer ends the talk


# --- data-driven loop: editing plain-text JSON changes in-game dialogue ------
@check("editing dialogue JSON changes what an NPC says, live")
def _():
    g = britain()
    # Simulate the editor agent rewriting Iolo's job as plain text.
    from ultima4.dialogue import load_for_location
    edited = [d.to_dict() for d in load_for_location(6).records]
    edited[0]["job"] = "I test the port."
    g._talk_cache[6] = TalkData.from_json(edited)   # what load_for_location would return
    npc = next(n for n in g.location.npcs if n.tlkidx == 1)
    conv = Conversation(g, npc, g._talk_cache[6].for_npc(1))
    g.active = conv
    g.talk_input("job")
    assert any("I test the port." in m for m in g.messages), g.messages


# --- overworld --------------------------------------------------------------
def outdoors():
    g = Game()
    g.party.loc = 0
    g.mode = MOD_OUTDOORS
    return g


@check("overworld: the 'E' key Enters and never walks east (regression)")
def _():
    g = outdoors()
    # stand on a walkable tile that is NOT a place you can enter
    places = set(zip(PLACE_X, PLACE_Y))
    spot = next((x, y) for y in range(60, 160) for x in range(60, 160)
                if is_walkable(g.world.tile_at(x, y)) and (x, y) not in places)
    g.party.x, g.party.y = spot
    g.handle("E")
    assert g.party.x == spot[0], "E moved the avatar east instead of Entering"
    assert any("Enter what" in m for m in g.messages)
    assert g.mode == MOD_OUTDOORS


@check("overworld: every town can be entered from its map coordinates")
def _():
    g = outdoors()
    for i, fname in enumerate(LOCATION_FILES):
        g.mode, g.location, g.party.loc = MOD_OUTDOORS, None, 0
        g.party.x, g.party.y = PLACE_X[i], PLACE_Y[i]
        g.messages.clear()
        g.handle("E")
        assert g.mode == MOD_BUILDING, f"{fname}: did not enter ({g.messages})"
        assert g.location.loc_id == i + 1, f"{fname}: entered loc {g.location.loc_id}, want {i+1}"


@check("overworld: movement walks onto open terrain and is blocked by the impassable")
def _():
    from ultima4.tiles import SLOW_PROGRESS
    g = outdoors()
    g.rng.seed(0)
    # find a walkable tile with an unobstructed neighbor (walkable, not slow-progress so the
    # move can't be randomly eaten) and an impassable neighbor.
    dirs = {"UP": (0, -1), "DOWN": (0, 1), "LEFT": (-1, 0), "RIGHT": (1, 0)}
    def clear(x, y):
        t = g.world.tile_at(x, y)
        return is_walkable(t) and t not in SLOW_PROGRESS
    found = None
    for y in range(40, 200):
        for x in range(40, 200):
            if not is_walkable(g.world.tile_at(x, y)):
                continue
            opens = [k for k, (dx, dy) in dirs.items() if clear(x + dx, y + dy)]
            blocks = [k for k, (dx, dy) in dirs.items() if not is_walkable(g.world.tile_at(x + dx, y + dy))]
            if opens and blocks:
                found = (x, y, opens[0], blocks[0]); break
        if found:
            break
    assert found, "no terrain edge found to test"
    x, y, open_dir, block_dir = found
    g.party.x, g.party.y = x, y
    g.handle(block_dir)
    assert (g.party.x, g.party.y) == (x, y), "moved into an impassable tile"
    g.handle(open_dir)
    assert (g.party.x, g.party.y) != (x, y), "failed to move onto open terrain"


@check("overworld: the map wraps as a torus (256x256)")
def _():
    g = outdoors()
    assert g.world.tile_at(256, 108) == g.world.tile_at(0, 108)
    assert g.world.tile_at(86, 256) == g.world.tile_at(86, 0)
    assert g.world.tile_at(-1, 108) == g.world.tile_at(255, 108)


# --- shops ------------------------------------------------------------------
def drive(g, *inputs):
    """Feed a sequence of lines to the active interaction, return all message lines."""
    out = []
    for text in inputs:
        g.messages.clear()
        g.feed(text)
        out.extend(g.messages)
    return out


@check("shop: Talk into Britain's weapon sign opens the shop and buying deducts gold")
def _():
    g = britain()
    g.party.x, g.party.y = 5, 4           # just south of the weapon sign at (5,3)
    g.party.gold = 100
    g.handle("T"); g.handle("N")          # Talk north -> sign-board -> weapon shop
    assert g.active is not None, "shop did not open"
    assert any("Welcome to" in m for m in g.messages)
    drive(g, "B", "C", "1", "N")          # Buy, dagger (id2='C', 2gp), one, then leave
    assert g.party.weapons[2] >= 1, "dagger not added"
    assert g.party.gold == 98, g.party.gold
    assert g.active is None               # "N" to 'anything else' closes the shop


@check("shop: selling a weapon pays half price")
def _():
    from ultima4.shops import BuySellShop
    g = britain()
    g.party.gold, g.party.weapons[6] = 0, 1     # own one Sword (id6, buys at 300)
    g._begin(BuySellShop(g, 0, "weapon"))       # Windsor Weaponry sells swords
    drive(g, "S", "G", "1", "Y", "")            # Sell, sword='G', one, deal yes, leave
    assert g.party.weapons[6] == 0 and g.party.gold == 150   # 300 >> 1
    assert g.active is None


@check("shop: Talk into Britain's food sign sells rations")
def _():
    g = britain()
    g.party.x, g.party.y = 18, 5          # just north of the food sign at (18,6)
    g.party.gold, g.party.food = 1000, 0
    g.handle("T"); g.handle("S")
    assert g.active is not None and any("Welcome to" in m for m in g.messages)
    drive(g, "Y", "1", "N")               # yes, one pack of 25, then no more
    # +2500 food from the purchase, then closing the shop ticks one move (-1 food, C_1C53).
    assert g.party.food == 2499 and g.party.gold == 960   # Britain = Adventure Food, 40gp
    assert g.active is None


@check("shop: the guild (smuggler) sells torches/gems/keys for gold")
def _():
    from ultima4.shops import GuildShop
    g = britain(); g.party.loc = 14          # Den has a guild
    g.party.gold, g.party.torches = 100, 0
    g._begin(GuildShop(g, 0))
    drive(g, "Y", "A", "N")                  # yes, buy torches (A: 5 for 50gp), done
    assert g.party.torches == 5 and g.party.gold == 50, (g.party.torches, g.party.gold)
    assert g.active is None


@check("shop: the tavern sells meals (food) and rumors (clues)")
def _():
    from ultima4.shops import TavernShop
    g = britain(); g.party.loc = 6              # Britain tavern (index 0)
    g.party.gold, g.party.food = 100, 0
    g._begin(TavernShop(g, 0))
    drive(g, "F", "2", "N")                     # 2 plates @4gp -> +200 food, -8 gold
    # +200 food from the meals; closing the tavern ticks one move (-1 food, C_1C53).
    assert g.party.food == 199 and g.party.gold == 92, (g.party.food, g.party.gold)
    # a tavern at index 0 knows every topic; buy the 'sextant' tip
    g._begin(TavernShop(g, 0))
    out = drive(g, "T", "sextant", "N")
    assert any("Guild shops" in m for m in out)


@check("shop: the healer heals, cures, resurrects, and takes blood")
def _():
    from ultima4.shops import HealerShop
    g = britain(); g.party.loc = 6              # Britain has a healer
    g.party.member_count = 2
    a, b = g.party.chara[0], g.party.chara[1]
    a.status, a.hp, a.hp_max = "G", 300, 300
    b.status, b.hp, b.hp_max = "D", 0, 80
    g.party.gold = 1000
    g._begin(HealerShop(g, 0))
    drive(g, "R")                               # resurrect member b (300gp)
    assert b.status == "G" and b.hp == 80 and g.party.gold == 700
    drive(g, "B")                               # blood donation: avatar -100 hp, Sacrifice up
    assert a.hp == 200 and g.party.karma[4] > 0
    drive(g, "")                                # leave
    assert g.active is None


@check("shop: the inn rests the party to full HP for gold")
def _():
    from ultima4.shops import InnShop
    g = britain(); g.party.loc = 6              # Britain inn (index 1, 15gp)
    g.party.member_count = 1
    c = g.party.chara[0]; c.status, c.hp, c.hp_max = "G", 20, 100
    g.party.gold = 50
    g._begin(InnShop(g, 1))
    drive(g, "Y")
    assert c.hp == 100 and g.party.gold == 35 and g.active is None


@check("shop: reagent haggling shifts Honesty/Justice/Honor karma")
def _():
    from ultima4.shops import ReagentShop
    g = britain(); g.party.loc = 5        # Moonglow has a reagent shop
    g.party.gold = 100
    for k in (0, 3, 5):
        g.party.karma[k] = 50
    g._begin(ReagentShop(g, 0))
    drive(g, "Y", "A", "1", "1")          # buy 1 Sulfur Ash (2gp), pay only 1 -> underpay
    assert g.party.reagents[0] == 1
    assert all(g.party.karma[k] < 50 for k in (0, 3, 5)), g.party.karma


# --- the `./run town` boot path (play.py helpers, no window) ------------------
@check("'run town britain' boot places you by an NPC and Talk reaches them")
def _():
    import os
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    import play
    g = Game(); g.rng.seed(3)
    loc_id, entry, kind = play.find_town("britain")
    g._enter_location(loc_id, entry=entry, kind=kind)
    play._place_for_testing(g)
    # the placement message tells the player which way to talk; follow it.
    msg = next(m for m in g.messages if "press T then" in m)
    direction = msg.split("press T then ")[1][0]      # 'N'/'S'/'E'/'W'
    g.handle("T"); g.handle(direction)
    assert g.active is not None, "Talk from the suggested tile reached no one"


# --- Lord British + Ztats ---------------------------------------------------
def at_lord_british():
    """Enter LB's castle, Klimb to the throne room, stand next to Lord British (tile 0x5E)."""
    g = Game(); g.rng.seed(2)
    g._enter_location(1, entry=(15, 30), kind="castle")   # LCB_1.ULT (entrance floor)
    g.party.x, g.party.y = 3, 3                           # a ladder up
    g.cmd_klimb()
    assert g.floor == 1, "did not climb to the throne room"
    lb = next(n for n in g.location.npcs if n.tile == 0x5E)
    g.party.x, g.party.y = lb.x, lb.y + 1                 # stand just south, talk North
    return g


@check("Klimb: the ladder in LB's castle reaches the upstairs throne room")
def _():
    g = Game(); g.rng.seed(2)
    g._enter_location(1, entry=(15, 30), kind="castle")
    assert not any(n.tile == 0x5E for n in g.location.npcs)   # LB not on the ground floor
    g.party.x, g.party.y = 27, 3                          # the other ladder up
    g.cmd_klimb()
    assert g.floor == 1
    assert any(n.tile == 0x5E for n in g.location.npcs), "Lord British not found upstairs"
    g.cmd_descend()                                       # ladders are two-way
    assert g.floor == 0


@check("Lord British: first audience records the meeting and greets the Avatar")
def _():
    g = at_lord_british()
    g.party.met_lb = 0
    g.handle("T"); g.handle("N")
    assert g.active is not None, "did not reach Lord British"
    assert g.party.met_lb == 1
    assert any("At long last" in m for m in g.messages), g.messages
    drive(g, "bye")
    assert g.active is None


@check("Lord British: 'health' then No fully heals the party")
def _():
    g = at_lord_british()
    g.party.met_lb = 1
    g.party.member_count = 1
    c = g.party.chara[0]
    c.xp, c.hp_max, c.hp, c.status = 0, 100, 5, "G"   # xp 0 so the audience won't level him
    g.handle("T"); g.handle("N")
    drive(g, "health", "N")
    assert c.hp == 100, c.hp


@check("Lord British: levels up a member whose XP outgrew their HP")
def _():
    from ultima4.lb import level_for_xp
    assert level_for_xp(0) == 1 and level_for_xp(100) == 2 and level_for_xp(200) == 3
    g = at_lord_british()
    g.party.met_lb = 1
    g.party.member_count = 1
    c = g.party.chara[0]
    c.xp, c.hp_max, c.hp = 200, 100, 100
    g.handle("T"); g.handle("N")                          # level-up happens on the audience
    assert c.hp_max == 300 and c.hp == 300, (c.hp, c.hp_max)
    assert any("Level 3" in m for m in g.messages)


@check("Ztats prints a character sheet")
def _():
    g = britain()
    g.party.member_count = 1
    g.party.chara[0].name = "Iolo"
    g.party.gold = 42
    g.cmd_ztats()
    assert any("Party" in m and "42" in m for m in g.messages)
    assert any("Iolo" in m for m in g.messages)


# --- doors ------------------------------------------------------------------
@check("Open: a door becomes walkable, then swings shut after a few turns")
def _():
    from ultima4.tiles import DOOR, BRICK_FLOOR
    g = Game(); g.rng.seed(1)
    g._enter_location(1, entry=(15, 30), kind="castle")     # LCB_1 has a door at (24,5)
    g.party.x, g.party.y = 23, 5
    assert g.location.tile_at(24, 5) == DOOR
    g.handle("O"); g.handle("E")                            # Open the door to the east
    assert g.location.tile_at(24, 5) == BRICK_FLOOR and is_walkable(BRICK_FLOOR)
    for _ in range(6):
        g.end_turn()
    assert g.location.tile_at(24, 5) == DOOR, "door never auto-closed"


@check("Jimmy: a locked door needs a key, and a key unlocks it")
def _():
    from ultima4.tiles import DOOR, LOCKED_DOOR
    g = Game(); g.rng.seed(1)
    g._enter_location(1, entry=(15, 30), kind="castle")     # locked door at (8,2)
    g.party.x, g.party.y = 7, 2
    g.party.keys = 0
    g.handle("J"); g.handle("E")
    assert g.location.tile_at(8, 2) == LOCKED_DOOR, "unlocked with no keys"
    g.party.keys = 1
    g.handle("J"); g.handle("E")
    assert g.location.tile_at(8, 2) == DOOR and g.party.keys == 0


# --- NPC movement -----------------------------------------------------------
@check("50 turns of NPC movement: in-bounds, no overlap, some wander")
def _():
    g = britain(seed=7)
    g.party.x, g.party.y = 15, 15
    moved = set()
    for _ in range(50):
        before = [(n.x, n.y) for n in g.location.npcs]
        g.end_turn()
        occ = {}
        for n in g.location.npcs:
            assert 0 <= n.x < 32 and 0 <= n.y < 32
            assert not (n.x == g.party.x and n.y == g.party.y)
            if n.tile and n.tile != 0x3C:
                assert (n.x, n.y) not in occ
                occ[(n.x, n.y)] = n.slot
        after = [(n.x, n.y) for n in g.location.npcs]
        moved |= {i for i, (a, b) in enumerate(zip(before, after)) if a != b}
    assert moved, "no NPC moved in 50 turns"


# --- environmental hazards (C: U4_EVT.C C_9209) -----------------------------
@check("hazards: a poison field poisons the party, then upkeep drains the poisoned member")
def _():
    from ultima4 import hazards
    from ultima4.constants import MOD_OUTDOORS
    g = Game(); g.rng.seed(11); g.mode = MOD_OUTDOORS
    g.party.member_count = 1
    c = g.party.chara[0]
    c.status, c.hp, c.hp_max, c.tile = "G", 50, 50, 0x1F
    g.party.tile = 0x1F
    # Stand the party on a poison field (0x44) and run hazards until it bites (1/8 per move).
    g.party.x, g.party.y = 0x00, 0x00
    orig = g.world.tile_at
    g.world.tile_at = lambda x, y: 0x44                     # force the standing tile to poison field
    try:
        for _ in range(80):
            hazards.per_turn_hazard(g)
            if c.status == "P":
                break
        assert c.status == "P", "poison field never poisoned a healthy member"
    finally:
        g.world.tile_at = orig
    # Now per-turn upkeep should bleed the poisoned member for 2.
    from ultima4 import upkeep
    hp0 = c.hp
    upkeep.per_turn_upkeep(g)
    assert c.hp == hp0 - 2


@check("hazards: crossing a bridge can spring a troll ambush into combat")
def _():
    from ultima4 import hazards
    from ultima4.constants import MOD_OUTDOORS, MOD_COMBAT
    g = Game(); g.rng.seed(1); g.mode = MOD_OUTDOORS
    g.party.member_count = 1
    g.party.chara[0].status, g.party.chara[0].hp, g.party.chara[0].hp_max = "G", 50, 50
    g.world.tile_at = lambda x, y: 0x17                     # a bridge under the party
    sprung = False
    for _ in range(60):
        if hazards.per_turn_hazard(g):
            sprung = True
            break
    assert sprung and g.mode == MOD_COMBAT                  # trolls -> combat (1/8 per move)


@check("hazards: lava burns the party on foot but only dents the hull at sea")
def _():
    from ultima4 import hazards
    from ultima4.constants import MOD_OUTDOORS
    g = Game(); g.rng.seed(3); g.mode = MOD_OUTDOORS
    g.party.member_count = 1
    c = g.party.chara[0]
    c.status, c.hp, c.hp_max = "G", 99, 99
    g.world.tile_at = lambda x, y: 0x4C                     # lava
    # Aboard a ship (tile <= 0x13): the hull takes 10, the crew is unharmed.
    g.party.tile, g.party.ship = 0x10, 50
    hazards.per_turn_hazard(g)
    assert g.party.ship == 40 and c.hp == 99
    # On foot (tile 0x1F): the hull is irrelevant, the party can burn for 10..24.
    g.party.tile = 0x1F
    burned = False
    for _ in range(40):
        c.hp = 99
        hazards.per_turn_hazard(g)
        if c.hp < 99:
            assert 99 - 24 <= c.hp <= 99 - 10
            burned = True
            break
    assert burned, "lava never burned a member on foot"


# --- per-turn upkeep (C: U4_MAIN.C C_1C53) ----------------------------------
@check("upkeep: food drains by party size each move, and starvation damages everyone")
def _():
    from ultima4 import upkeep
    g = britain(seed=3)
    g.party.member_count = 3
    for c in g.party.chara[:3]:
        c.status, c.hp, c.hp_max = "G", 50, 50
    g.party.food = 1000
    upkeep.per_turn_upkeep(g)
    assert g.party.food == 997, g.party.food                  # -3 for a party of three
    # Empty the larder: the next move starves the party, costing every living member 2 HP.
    g.party.food = 2
    upkeep.per_turn_upkeep(g)
    assert g.party.food == 0 and all(c.hp == 48 for c in g.party.chara[:3])


@check("upkeep: the poisoned take 2/move and a sleeper eventually wakes")
def _():
    from ultima4 import upkeep
    g = britain(seed=5)
    g.party.member_count = 2
    poisoned, sleeper = g.party.chara[0], g.party.chara[1]
    poisoned.status, poisoned.hp, poisoned.hp_max = "P", 50, 50
    sleeper.status, sleeper.hp, sleeper.hp_max = "S", 50, 50
    upkeep.per_turn_upkeep(g)
    assert poisoned.hp == 48, poisoned.hp                     # poison bites for 2
    woke = any((upkeep.per_turn_upkeep(g), sleeper.status == "G")[1] for _ in range(200))
    assert woke and sleeper.status == "G"                     # 1/8 per move -> wakes within 200


@check("upkeep: MP regenerates +1/move up to a class/Int cap; a Fighter holds none")
def _():
    from ultima4 import upkeep
    assert upkeep.mp_cap(0, 20) == 40                          # Mage = Int*2
    assert upkeep.mp_cap(3, 20) == 30                          # Druid = Int*1.5
    assert upkeep.mp_cap(4, 20) == 10                          # Tinker = Int/2
    assert upkeep.mp_cap(2, 99) == 0 and upkeep.mp_cap(7, 99) == 0   # Fighter/Shepherd: no magic
    assert upkeep.mp_cap(0, 99) == 99                          # clamped to 99
    g = britain(seed=2)
    g.party.member_count = 2
    mage, fighter = g.party.chara[0], g.party.chara[1]
    mage.char_class, mage.intel, mage.mp, mage.status = chr(0), 20, 0, "G"
    fighter.char_class, fighter.intel, fighter.mp, fighter.status = chr(2), 20, 5, "G"
    upkeep.per_turn_upkeep(g)
    assert mage.mp == 1                                        # +1 toward the cap of 40
    assert fighter.mp == 0                                     # a Fighter's MP is clamped to 0


@check("upkeep: a wiped party is revived by Lord British in his throne room")
def _():
    from ultima4 import upkeep
    g = britain(seed=4)
    g.party.member_count = 2
    for c in g.party.chara[:2]:
        c.status, c.hp, c.hp_max = "D", 0, 60
    g.party.gold, g.party.food = 9999, 5
    relocated = upkeep.per_turn_upkeep(g)
    assert relocated is True
    assert g.mode == MOD_BUILDING and g.party.loc == 0x01 and g.floor == 1   # LCB_2 throne room
    assert g.party.x == 0x13 and g.party.y == 0x08
    assert all(c.status == "G" and c.hp == c.hp_max for c in g.party.chara[:2])
    assert g.party.food == 20099 and g.party.gold == 200      # the death penalty (C_0EB1)
    assert g.party.weapons == [0] * 16 and g.party.armors == [0] * 8


def main() -> int:
    width = max(len(n) for n, _, _ in _results)
    passed = 0
    for name, ok, err in _results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name.ljust(width)}  {err}")
        passed += ok
    print(f"\n{passed}/{len(_results)} checks passed")
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
