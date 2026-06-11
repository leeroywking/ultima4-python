"""Tile identity table + terrain predicates, ported from U4_SHAPE.H and U4_MAP.C.

Tile ids are bytes 0x00..0xFF; in the C source `TIL_xx == 0xxx`. Names come from the
U4_SHAPE.H comments. This table is heavily used by the tutor ("you're standing on a
moongate") and the editor ("place a town tile here"), so it lives in its own module.
"""

# id -> human name (C: U4_SHAPE.H comments). Only the meaningful tiles are named;
# unnamed ids fall back to f"tile_{id:02X}".
TILE_NAMES = {
    0x00: "deep water", 0x01: "medium water", 0x02: "shallow water",
    0x03: "swamp", 0x04: "grass", 0x05: "scrub", 0x06: "forest", 0x07: "hills",
    0x08: "mountains", 0x09: "dungeon entrance", 0x0A: "town", 0x0B: "castle",
    0x0C: "village", 0x0D: "LB castle left wing", 0x0E: "LB castle entrance",
    0x0F: "LB castle right wing",
    0x10: "ship (W)", 0x11: "ship (N)", 0x12: "ship (E)", 0x13: "ship (S)",
    0x14: "horse (W)", 0x15: "horse (E)", 0x16: "tiled floor", 0x17: "bridge",
    0x18: "balloon", 0x19: "bridge (top)", 0x1A: "bridge (bottom)",
    0x1B: "ladder up", 0x1C: "ladder down", 0x1D: "ruins",
    0x1E: "shrine", 0x1F: "avatar (on foot)",
    0x20: "mage", 0x22: "bard", 0x24: "fighter", 0x26: "druid", 0x28: "tinker",
    0x2A: "paladin", 0x2C: "ranger", 0x2E: "shepherd",
    # 0x30-0x36: best-guess names from map-usage + sprite analysis (no source names exist).
    # 0x30 is solid (a barrier); 0x31-0x34 are sight-passable energy (combat lets line-of-
    # sight through them, and they cluster in the Abyss); 0x35-0x36 are solid wooden features
    # seen on the decks of the ship-combat maps. Refine if play proves otherwise.
    0x30: "force_field", 0x31: "force_field_1", 0x32: "force_field_2",
    0x33: "force_field_3", 0x34: "force_field_4",
    0x35: "ship_rail", 0x36: "ship_mast", 0x37: "rocks",
    0x38: "body", 0x39: "cobblestones", 0x3A: "locked door", 0x3B: "door",
    0x3C: "chest", 0x3D: "ankh", 0x3E: "brick floor", 0x3F: "wood floor",
    0x40: "moongate (phase 0)", 0x41: "moongate (phase 1)",
    0x42: "moongate (phase 2)", 0x43: "moongate (phase 3)",
    0x44: "poison field", 0x45: "energy field", 0x46: "fire field",
    0x47: "sleep field", 0x48: "white", 0x49: "secret door (brick)",
    0x4A: "altar", 0x4B: "spit roast", 0x4C: "lava", 0x4D: "missile",
    0x4E: "magic burst", 0x4F: "magic burst2",
    0x7F: "brick",
    0x50: "guard", 0x52: "merchant", 0x54: "bard (npc)", 0x56: "jester",
    0x58: "beggar", 0x5A: "child", 0x5C: "bull", 0x5E: "Lord British",
    0x80: "pirate ship", 0x84: "nixie", 0x86: "squid", 0x88: "sea serpent",
    0x8A: "seahorse", 0x8C: "whirlpool", 0x8E: "twister",
    0x90: "rat", 0x94: "bat", 0x98: "spider", 0x9C: "ghost", 0xA0: "slime",
    0xA4: "troll", 0xA8: "gremlin", 0xAC: "mimic", 0xB0: "reaper", 0xB4: "insects",
    0xB8: "gazer", 0xBC: "phantom", 0xC0: "orc", 0xC4: "skeleton", 0xC8: "rogue",
    0xCC: "python", 0xD0: "ettin", 0xD4: "headless", 0xD8: "cyclops", 0xDC: "wisp",
    0xE0: "mage (monster)", 0xE4: "lich", 0xE8: "lava lizard", 0xEC: "zorn",
    0xF0: "daemon", 0xF4: "hydra", 0xF8: "dragon", 0xFC: "balron",
}

# --- Animation / direction frames (detected from the sprite sheet) -----------
# Many creatures occupy several consecutive tile slots that hold extra frames of the same
# sprite. Rather than list each by hand, derive the frame names from the base tile (the
# grouping was confirmed by measuring per-tile sprite differences in SHAPES.EGA):
#   town person NPCs 0x20-0x2F & 0x50-0x5F : 2 animation frames each
#   sea creatures    0x84-0x8F             : 2 animation frames each
#   land monsters    0x90-0xFF             : 4 animation frames each
# The pirate ship (0x80-0x83) is the exception: 4 *directional* frames like the avatar
# ship, named by facing (verified against ship 0x10-0x13: 0x80=W 0x81=N 0x82=E 0x83=S).
for _facing, _id in zip("WNES", range(0x80, 0x84)):
    TILE_NAMES[_id] = f"pirate ship ({_facing})"
for _start, _stop, _frames in ((0x20, 0x30, 2), (0x50, 0x60, 2), (0x84, 0x90, 2), (0x90, 0x100, 4)):
    for _base in range(_start, _stop, _frames):
        if _base in TILE_NAMES:
            for _f in range(1, _frames):
                TILE_NAMES.setdefault(_base + _f, f"{TILE_NAMES[_base]}{_f + 1}")
# Sign-board glyphs (see is_sign_glyph): 0x60-0x79 are the letters A-Z; 0x7A-0x7E are
# the remaining punctuation/space glyphs.
for _id in range(0x60, 0x7A):
    TILE_NAMES.setdefault(_id, f"letter {chr(ord('A') + _id - 0x60)}")
# 0x7A-0x7E are the sign-board frame/spacer glyphs (deduced from how town signs are drawn:
# "THE[7A]INN" -> 0x7A is the blank spacer; "[7C]VESPER[7B]" -> 0x7C/0x7B left/right borders;
# "[7E][7E][7E]" along the top -> 0x7E top border; 0x7D the remaining (bottom) edge).
for _id, _nm in ((0x7A, "sign_blank"), (0x7B, "sign_border_right"), (0x7C, "sign_border_left"),
                 (0x7D, "sign_border_bottom"), (0x7E, "sign_border_top")):
    TILE_NAMES.setdefault(_id, _nm)
del _nm
del _facing, _id, _start, _stop, _frames, _base, _f

# Normalize every name to a snake_case identifier so tile names are safe to reference in
# code (no spaces/punctuation): "ship (W)" -> "ship_w", "Lord British" -> "lord_british".
import re as _re
TILE_NAMES = {_k: _re.sub(r"[^a-z0-9]+", "_", _v.lower()).strip("_") for _k, _v in TILE_NAMES.items()}
del _re


def tile_name(tile_id: int) -> str:
    return TILE_NAMES.get(tile_id, f"tile_{tile_id:02X}")


# --- Named tile constants -----------------------------------------------------
# Plain-English names for the tile ids the game logic actually keys off, so code reads
# `tile == LORD_BRITISH` instead of `tile == 0x5E`. Names mirror TILE_NAMES above.
DEEP_WATER = 0x00
SWAMP = 0x03
GRASS = 0x04
SCRUB = 0x05
FOREST = 0x06
HILLS = 0x07
MOUNTAINS = 0x08
DUNGEON_ENTRANCE = 0x09
TOWN = 0x0A
CASTLE = 0x0B
VILLAGE = 0x0C
LB_CASTLE_ENTRANCE = 0x0E       # the enterable doorway tile of Lord British's castle
LADDER_UP = 0x1B
LADDER_DOWN = 0x1C
RUINS = 0x1D
SHRINE = 0x1E
LOCKED_DOOR = 0x3A              # needs a key (Jimmy) before it can be Opened
DOOR = 0x3B                     # closed door: blocks until Opened
CHEST = 0x3C
BRICK_FLOOR = 0x3E             # what an opened door becomes (walkable) until it auto-closes
FIRE_FIELD = 0x46
MERCHANT = 0x52                 # a shopkeeper NPC standing behind a sign
BEGGAR = 0x58                   # the only NPC that accepts "give" (gold)
LORD_BRITISH = 0x5E
SIGN_GLYPH_FIRST = 0x60         # 0x60..0x7E are the "alphabet" sign-board glyph tiles
SIGN_GLYPH_LAST = 0x7E


def is_sign_glyph(tile_id: int) -> bool:
    """True for the letter tiles that label a shop's sign-board (C: TIL_60..TIL_7E)."""
    return SIGN_GLYPH_FIRST <= tile_id <= SIGN_GLYPH_LAST


def anim_frame(tile_id: int, phase: int) -> int:
    """The animation frame of a *sprite object* (NPC/monster) at animation `phase`.

    C: U4_ANIM.C C_3605 — exactly these bands animate, and ONLY for sprite objects (the map
    scenery itself never frame-cycles):
      - 2-frame (base..base+1): people 0x20-0x2E, town NPCs 0x50-0x5E, sea life 0x84-0x8E.
      - 4-frame (base..base+3): land monsters tile >= 0x90.
      - the pirate ship 0x80-0x83 and everything else are static.
    Note this band is deliberately NOT 0x30-0x4F: those are scenery (body 0x38, cobbles 0x39,
    brick/wood floor 0x3E/0x3F, fields, altar) which must stay still."""
    if 0x20 <= tile_id <= 0x2F or 0x50 <= tile_id <= 0x5F or 0x84 <= tile_id <= 0x8F:
        return (tile_id & ~1) + (phase & 1)
    if tile_id >= 0x90:
        return (tile_id & ~3) + (phase & 3)
    return tile_id


# Tiles passable on foot (C: U4_MAP.C D_0904, used by C_2999 "isBrickSolid").
# You are BLOCKED moving onto a tile not in this set (with special-case exceptions).
WALKABLE_ON_FOOT = frozenset({
    0x03, 0x04, 0x05, 0x06, 0x07, 0x09, 0x0A, 0x0B, 0x0C,
    0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18,
    0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E,
    0x3C, 0x3E, 0x3F, 0x43, 0x44, 0x46, 0x47, 0x49, 0x4A, 0x4C,
    0x8E, 0x8F,
})

# Tiles a ship may sail onto (C: U4_MAP.C C_2A38: tile < 0x02, or 0x8C..0x8F).
SAILABLE = frozenset({0x00, 0x01, 0x8C, 0x8D, 0x8E, 0x8F})

# "Slow progress" terrain that may cost the move (C: U4_MAP.C C_29EF).
#   swamp(0x03): 1/8 slow; scrub/forest(0x05,0x06): 3/4; hills/fire(0x07,0x46): 1/2.
SLOW_PROGRESS = {0x03, 0x05, 0x06, 0x07, 0x46}

# Tiles the original continuously animates via procedural pixel-flow (C: U4_ANIM.C C_34EA
# Gra_animFlow): the three waters, lava, and the four magic fields. The DOS game scrambles
# their pixels each animation tick; we don't do the per-pixel shimmer yet (see ROADMAP).
ANIMATED_FLOW = {DEEP_WATER, 0x01, 0x02, 0x4C, 0x44, 0x45, 0x46, 0x47}


def is_walkable(tile_id: int) -> bool:
    return tile_id in WALKABLE_ON_FOOT
