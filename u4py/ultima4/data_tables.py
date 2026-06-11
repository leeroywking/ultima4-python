"""Static world data tables, ported verbatim from U4_MAIN2.C.

These are the hardcoded constants that, in Phase 2, become editable data files —
they are exactly the surface the editor agent touches for asks like
"add a moongate" or "add a new town". Kept faithful (same values, same order) for now.
"""

# Moongate destination positions on the world map (C: U4_MAIN2.C D_0814 / D_081C).
# Indexed by moon phase (Trammel selects X via _trammel, Felucca via _felucca).
# Lists (not tuples) so the editor agent can rewrite a moongate destination in place.
MOONGATE_X = [0xE0, 0x60, 0x26, 0x32, 0xA6, 0x68, 0x17, 0xBB]  # C: D_0814
MOONGATE_Y = [0x85, 0x66, 0xE0, 0x25, 0x13, 0xC2, 0x7E, 0xA7]  # C: D_081C

# Town/castle map files (C: U4_MAIN2.C D_0824). Index = location id - 1.
# Loading a .ULT enters MOD_BUILDING. Order is load-bearing (matches place ids).
LOCATION_FILES = (
    # Castles
    "LCB_1.ULT",     # Lord British's Castle
    "LYCAEUM.ULT",
    "EMPATH.ULT",    # Empath Abbey
    "SERPENT.ULT",   # Serpent's Hold
    # Townes
    "MOONGLOW.ULT",
    "BRITAIN.ULT",
    "JHELOM.ULT",
    "YEW.ULT",
    "MINOC.ULT",
    "TRINSIC.ULT",
    "SKARA.ULT",     # Skara Brae
    "MAGINCIA.ULT",
    # Villages
    "PAWS.ULT",
    "DEN.ULT",
    "VESPER.ULT",
    "COVE.ULT",
)

# World-map coordinates of each place (C: U4_MAIN2.C D_0844 = X, D_0864 = Y).
# 32 entries; parallel arrays. Used to detect entering a location from the overworld.
PLACE_X = (
    0x56, 0xDA, 0x1C, 0x92, 0xE8, 0x52, 0x24, 0x3A, 0x9F, 0x6A, 0x16, 0xBB,
    0x62, 0x88, 0xC9, 0x88, 0xF0, 0x5B, 0x48, 0x7E, 0x9C, 0x3A, 0xEF, 0xE9,
    0xE9, 0x80, 0x24, 0x49, 0xCD, 0x51, 0xE7, 0xE7,
)  # C: D_0844
PLACE_Y = (
    0x6B, 0x6B, 0x32, 0xF1, 0x87, 0x6A, 0xDE, 0x2B, 0x14, 0xB8, 0x80, 0xA9,
    0x91, 0x9E, 0x3B, 0x5A, 0x49, 0x43, 0xA8, 0x14, 0x1B, 0x66, 0xF0, 0xE9,
    0x42, 0x5C, 0xE5, 0x0B, 0x2D, 0xCF, 0xD8, 0xD8,
)  # C: D_0864

# Locations with multiple stacked floors connected by ladders (tile 0x1B up / 0x1C down).
# loc_id -> floor .ULT files, bottom-to-top. Anything not listed is single-floor
# (its LOCATION_FILES entry). Lord British's Castle: entrance level + throne room upstairs.
MULTI_FLOOR = {
    1: ("LCB_1.ULT", "LCB_2.ULT"),
}

# Dungeon map files (C: U4_MAIN2.C D_0894). Location ids 0x11..0x18.
DUNGEON_FILES = (
    "Deceit.Dng",
    "Despise.Dng",
    "Destard.Dng",
    "Wrong.Dng",
    "Covetous.Dng",
    "Shame.Dng",
    "Hythloth.Dng",
    "Abyss.Dng",
)

# Moongate / moon-phase color names (C: U4_MAIN2.C D_0884).
MOON_COLORS = (
    "Blue", "Yellow", "Red", "Green", "Orange", "Purple", "White", "Black",
)

# The 8 visible phases of a moon (phase 0 = new, 4 = full). Always shown on the overworld HUD.
MOON_PHASE_NAMES = (
    "New", "Waxing Crescent", "First Quarter", "Waxing Gibbous",
    "Full", "Waning Gibbous", "Last Quarter", "Waning Crescent",
)

# --- New-game starting data (C: SRC-TITLE/TITLE_1.C) ---
# Your final virtue choice picks your class; index 0..7 parallels constants.VIRTUES.
# Each class maps to a companion (PARTY.NEW template slot), a starting town, and a
# moongate drop position (C: D_30DC = start X, D_30E4 = start Y).
CLASS_NAMES = ("Mage", "Bard", "Fighter", "Druid", "Tinker", "Paladin", "Ranger", "Shepherd")
CLASS_COMPANION = ("Mariah", "Iolo", "Geoffrey", "Jaana", "Julia", "Dupre", "Shamino", "Katrina")
CLASS_HOME = ("Moonglow", "Britain", "Jhelom", "Yew", "Minoc", "Trinsic", "Skara Brae", "Magincia")
START_X = (0xE7, 0x53, 0x23, 0x3B, 0x9E, 0x69, 0x17, 0xBA)  # C: D_30DC
START_Y = (0x88, 0x69, 0xDD, 0x2C, 0x15, 0xB7, 0x81, 0xAB)  # C: D_30E4

# Stat increments applied per chosen virtue during the gypsy questions
# (C: D_30B2/D_30BA/D_30C2). Base stat is 15 each; full creation sums these over the
# seven choices. Kept here so authentic character creation can be ported later.
VIRTUE_STR_INC = (0, 0, 3, 0, 1, 1, 1, 0)
VIRTUE_DEX_INC = (0, 3, 0, 1, 1, 0, 1, 0)
VIRTUE_INT_INC = (3, 0, 0, 1, 0, 1, 1, 0)

# Talk-data (.TLK) files per location (C: U4_EXPLO.C D_1738), parallel to LOCATION_FILES.
TLK_FILES = (
    "LCB.TLK", "LYCAEUM.TLK", "EMPATH.TLK", "SERPENT.TLK",
    "MOONGLOW.TLK", "BRITAIN.TLK", "JHELOM.TLK", "YEW.TLK",
    "MINOC.TLK", "TRINSIC.TLK", "SKARA.TLK", "MAGINCIA.TLK",
    "PAWS.TLK", "DEN.TLK", "VESPER.TLK", "COVE.TLK",
)
