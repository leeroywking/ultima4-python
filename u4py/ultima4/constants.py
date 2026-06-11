"""Core game constants, ported faithfully from the decompiled source.

C source: U4.H (struct/#define block), U4_MAIN2.C (tables live in data_tables.py).
Values are the originals — do not "tidy" them; later phases depend on them matching.
"""

# --- Facing directions (C: U4.H DIR_*) ---
DIR_W = 0
DIR_N = 1
DIR_E = 2
DIR_S = 3

# Per-direction tile deltas (C: U4_MAIN2.C D_080C / D_0810).
# Indexed by DIR_*; (dx, dy).
DIR_DX = (-1, 0, 1, 0)  # C: D_080C
DIR_DY = (0, -1, 0, 1)  # C: D_0810

# --- Game modes (C: U4.H MOD_*, held in global CurMode / D_946A) ---
MOD_VISION = 0
MOD_OUTDOORS = 1
MOD_BUILDING = 2
MOD_DUNGEON = 3
MOD_COMBAT = 4
MOD_COM_CAMP = 5
MOD_COM_ROOM = 6
MOD_SHRINE = 7

MODE_NAMES = {
    MOD_VISION: "vision",
    MOD_OUTDOORS: "outdoors",
    MOD_BUILDING: "building",
    MOD_DUNGEON: "dungeon",
    MOD_COMBAT: "combat",
    MOD_COM_CAMP: "camp",
    MOD_COM_ROOM: "room",
    MOD_SHRINE: "shrine",
}

# --- tParty.mItems bit positions (C: U4.H ST_*) ---
# The "special items" bitmask. Bit set => item possessed / used.
ST_USE_BELL = 12
ST_USE_BOOK = 11
ST_USE_CANDLE = 10
ST_WHEEL = 9
ST_HORN = 8
ST_KEY_T = 7   # three-part key: Truth
ST_KEY_L = 6   # three-part key: Love
ST_KEY_C = 5   # three-part key: Courage
ST_BELL = 4
ST_BOOK = 3
ST_CANDLE = 2
ST_CAST_SKULL = 1
ST_SKULL = 0

# --- The eight virtues, in karma-array order (C: U4_MAIN2.C pKarmas) ---
# tParty stores one karma byte-pair per virtue in this exact order.
VIRTUES = (
    "Honesty",
    "Compassion",
    "Valor",
    "Justice",
    "Sacrifice",
    "Honor",
    "Spirituality",
    "Humility",
)
