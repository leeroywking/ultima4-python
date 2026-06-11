"""Items & their use (U4_USE.C / U4_GET.C / U4_SRCH.C / U4_HOLE.C / U4_PEER.C).

The inventory-facing commands that aren't shops/combat. Each handler takes the live `game`
and mutates `state.Party`. Commands that need a direction set `game.pending_dir` and are
finished in `game._resolve_dir`; the rest act immediately.
"""
from __future__ import annotations

from .constants import (DIR_DX, DIR_DY, MOD_OUTDOORS, MOD_BUILDING, MOD_COMBAT, VIRTUES,
                        ST_SKULL, ST_CAST_SKULL, ST_BELL, ST_BOOK, ST_CANDLE,
                        ST_HORN, ST_WHEEL, ST_USE_BELL, ST_USE_BOOK, ST_USE_CANDLE,
                        ST_KEY_T, ST_KEY_L, ST_KEY_C)
from .tiles import CHEST, BRICK_FLOOR


# --- Get (U4_GET.C) ---------------------------------------------------------
def cmd_get(game) -> None:
    """C: U4_GET.C CMD_Get — get the chest you face (gold)."""
    if game.mode != MOD_BUILDING or game.location is None:
        game.message("Nothing here to get.")
        return
    game.message("Get- Dir?")
    game.pending_dir = "get"


def get_dir(game, direction: int) -> None:
    dx, dy = DIR_DX[direction], DIR_DY[direction]
    tx, ty = game.party.x + dx, game.party.y + dy
    if game.location.tile_at(tx, ty) == CHEST:
        amount = 100 + game.rng.randint(0, 150)          # C: random chest gold
        game.party.gold = min(9999, game.party.gold + amount)
        game.location.tiles[ty * 32 + tx] = BRICK_FLOOR  # chest is emptied
        game.message(f"You open the chest and find {amount} gold!")
    else:
        game.message("Nothing to get there.")


# --- Ready weapon / Wear armor (U4_USE.C CMD_Ready / CMD_Wear) ---------------
def cmd_ready(game) -> None:
    """C: CMD_Ready — ready a weapon for the avatar (defaults to the best owned)."""
    from .shops import WEAPON_NAMES
    p = game.party
    owned = [i for i in range(1, 16) if p.weapons[i] > 0]
    if not owned:
        game.message("You own no weapons!")
        return
    wid = owned[-1]
    p.chara[0].weapon = wid
    game.message(f"{p.chara[0].name or 'Avatar'} readies the {WEAPON_NAMES[wid]}.")


def cmd_wear(game) -> None:
    """C: CMD_Wear — wear armor on the avatar (defaults to the best owned)."""
    from .shops import ARMOR_NAMES
    p = game.party
    owned = [i for i in range(1, 8) if p.armors[i] > 0]
    if not owned:
        game.message("You own no armor!")
        return
    aid = owned[-1]
    p.chara[0].armor = aid
    game.message(f"{p.chara[0].name or 'Avatar'} wears the {ARMOR_NAMES[aid]}.")


# --- Ignite torch (U4_USE.C CMD_Ignite) -------------------------------------
TORCH_TURNS = 100      # C: torch light duration


def cmd_ignite(game) -> None:
    p = game.party
    if p.torches <= 0:
        game.message("Thou hast no torches!")
        return
    p.torches -= 1
    game.torchlight = TORCH_TURNS
    game.message("Ignite torch!")


# --- Hole up & camp (U4_HOLE.C CMD_HoleUp) ----------------------------------
def cmd_hole_up(game) -> None:
    """C: U4_HOLE.C — camp and rest: conscious members heal, the party eats."""
    p = game.party
    healed = 0
    for c in p.members:
        if c.status == "G" and c.hp < c.hp_max:
            c.hp = min(c.hp_max, c.hp + max(1, c.hp_max // 4))   # rest restores ~a quarter
            healed += 1
    p.food = max(0, p.food - 100)                                # camping consumes rations
    game.message("Hole up & camp.  Thou dost rest." if healed else "Hole up & camp.")


# --- Locate / sextant (U4_USE.C CMD_Locate) ---------------------------------
def cmd_locate(game) -> None:
    """C: CMD_Locate — a sextant reads your overworld latitude/longitude."""
    if game.mode != MOD_OUTDOORS:
        game.message("Locate position only works outdoors.")
        return
    if game.party.sextants <= 0:
        game.message("You need a sextant!")
        return
    x, y = game.party.x, game.party.y
    game.message(f"Locate position: {y // 16}{chr(ord('A') + y % 16)}'"
                 f" {x // 16}{chr(ord('A') + x % 16)}\"")


# --- Use a special item (U4_USE.C CMD_Use) ----------------------------------
# The quest items live in Party.items as a bitmask (constants.ST_*). Each Use handler ports its
# C function (D_0434 dispatch). Two stock replies: D_0100 "None owned!" (you lack the item) and
# D_00EE "Hmm...No effect!" (you have it, but not here / not the right moment).
_USABLE = ((ST_SKULL, "skull"), (ST_BELL, "bell"), (ST_BOOK, "book"),
           (ST_CANDLE, "candle"), (ST_HORN, "horn"), (ST_WHEEL, "wheel"))

ABYSS_X, ABYSS_Y = 0xE9, 0xE9       # the Great Stygian Abyss entrance on the overworld (loc 0)
_SHIP_TILE_MAX = 0x13               # C: TIL_13 — avatar _tile <= this means "aboard a ship"
_NONE_OWNED = ["None owned!"]       # C: D_0100
_NO_EFFECT = ["Hmm...No effect!"]   # C: D_00EE


def owned_items(party) -> list:
    return [name for bit, name in _USABLE if party.items & (1 << bit)]


def _has(p, bit: int) -> bool:
    return bool(p.items & (1 << bit))


def _at_abyss(p) -> bool:
    """Standing on the Abyss entrance — where the Bell/Book/Candle/Skull rituals happen."""
    return p.loc == 0 and p.x == ABYSS_X and p.y == ABYSS_Y


def _use_bell(game, p):             # C: U4_USE.C C_0487
    if not _has(p, ST_BELL):
        return _NONE_OWNED
    if not _at_abyss(p):
        return _NO_EFFECT
    p.items |= (1 << ST_USE_BELL)
    return ["The Bell rings on and on!"]


def _use_book(game, p):             # C: U4_USE.C C_04C0 (needs the Bell already rung)
    if not _has(p, ST_BOOK):
        return _NONE_OWNED
    if not _at_abyss(p) or not _has(p, ST_USE_BELL):
        return _NO_EFFECT
    p.items |= (1 << ST_USE_BOOK)
    return ["The words resonate with the ringing!"]


def _use_candle(game, p):           # C: U4_USE.C C_0501 (needs the Book already read)
    if not _has(p, ST_CANDLE):
        return _NONE_OWNED
    if not _at_abyss(p) or not _has(p, ST_USE_BOOK):
        return _NO_EFFECT
    p.items |= (1 << ST_USE_CANDLE)
    return ["As you light the Candle the Earth Trembles!"]


def _use_horn(game, p):             # C: U4_USE.C C_0553
    if not _has(p, ST_HORN):
        return _NONE_OWNED
    if p.loc != 0:
        return _NO_EFFECT
    # C: spell_sta=1, spell_cnt=10 — 10 moves of safe passage (timed spell state not yet modelled).
    return ["The Horn sounds an eerie tone!"]


def _use_wheel(game, p):            # C: U4_USE.C C_058C
    if not _has(p, ST_WHEEL):
        return _NONE_OWNED
    # Only aboard a ship, on the overworld, with a fully-repaired hull (50).
    if p.loc != 0 or p.tile > _SHIP_TILE_MAX or p.ship != 50:
        return _NO_EFFECT
    p.ship = 99                                          # the Wheel makes the hull near-invulnerable
    return ["Once mounted, the Wheel glows with a blue light!"]


def _use_skull(game, p):            # C: U4_USE.C C_05CE
    if not _has(p, ST_SKULL):
        return _NONE_OWNED
    p.items &= ~(1 << ST_SKULL)                          # the Skull is spent either way
    if _at_abyss(p):
        # The redemptive use: cast it into the Abyss, raising every virtue.
        p.items |= (1 << ST_CAST_SKULL)
        for i in range(8):
            p.karma[i] = min(99, p.karma[i] + 10)
        return ["You cast the Skull of Mondain into the Abyss!"]
    # Held aloft, it annihilates the creatures nearby — but corrupts every virtue.
    destroyed = len(game.monsters)
    game.monsters = []
    if game.mode == MOD_COMBAT and game.combat is not None:
        for u in game.combat.monsters:
            u.hp = 0
        destroyed += sum(1 for u in game.combat.monsters)
    for i in range(8):
        p.karma[i] = max(0, p.karma[i] - 5)
    return ["You hold the evil Skull of Mondain the Wizard aloft....",
            "The very air shrieks as the creatures around thee are destroyed!"]


def _use_key(game, p):              # C: U4_USE.C C_044C
    if any(_has(p, b) for b in (ST_KEY_T, ST_KEY_L, ST_KEY_C)):
        return ["No place to Use them!"]
    return _NONE_OWNED


def _use_stone(game, p):            # C: U4_USE.C C_0311 (dungeon-altar puzzle)
    # Using a colored Stone happens at a dungeon altar room (the Three Part Key puzzle);
    # altar rooms aren't modelled yet, so off an altar there is no effect.
    return _NO_EFFECT


_USE_HANDLERS = {
    "stone": _use_stone, "stones": _use_stone,
    "bell": _use_bell, "book": _use_book, "candle": _use_candle,
    "key": _use_key, "keys": _use_key,
    "horn": _use_horn, "wheel": _use_wheel, "skull": _use_skull,
}


def use_item(game, name: str) -> list:
    """Apply a named special item, faithfully. C: U4_USE.C CMD_Use (D_0434 dispatch)."""
    handler = _USE_HANDLERS.get(name.strip().lower())
    if handler is None:
        return ["Not a Usable item!"]                   # C: end of CMD_Use
    return handler(game, game.party)


def abyss_ritual_done(p) -> bool:
    """True once the Bell/Book/Candle ritual has been performed (in order) at the Abyss
    entrance — the gate that opens the Great Stygian Abyss. C: U4_EXPLO.C C_3FB9."""
    bits = (ST_BELL, ST_BOOK, ST_CANDLE, ST_USE_BELL, ST_USE_BOOK, ST_USE_CANDLE)
    return all(_has(p, b) for b in bits)


class UseSession:
    """Tiny interaction: 'Use which item?' -> apply it (shares the game.feed protocol)."""
    def __init__(self, game):
        self.game = game
        self.done = False
        self.prompt = "Use which item?"

    def intro(self) -> list:
        owned = owned_items(self.game.party)
        return ["Use-", "Thou hast: " + ", ".join(owned) if owned else "Thou hast no special items."]

    def respond(self, text: str) -> list:
        self.done = True
        return use_item(self.game, text)


def cmd_use(game) -> None:          # C: U4_USE.C CMD_Use
    game._begin(UseSession(game))


# --- Search for hidden quest items (U4_SRCH.C CMD_Search) --------------------
# Faithful port of the (loc, x, y, handler) table D_2920 — the fixed spots where the quest
# items, the two special stones, and the eight runes lie hidden. Coordinates are verbatim
# from U4_SRCH.C; loc ids are our location numbering (place index + 1), which matches the
# original Party._loc (0 = overworld). This is the key to playable progression.

_NIGHTSHADE, _MANDRAKE = 6, 7       # reagent indices (C: C_8D6D arg)
_HONOR = 5                          # karma index for the search reward (C: C_8D4B &_honor)
_NOTHING = "Nothing Here!"          # C: D_27A6
# Which virtue's rune lies in each location (C: D_2904 {loc, 1<<virtue}).
_RUNE_VIRTUE = {0x05: 0, 0x06: 1, 0x07: 2, 0x08: 3, 0x09: 4, 0x0A: 5, 0x01: 6, 0x0D: 7}


def _moons_dark(p) -> bool:
    """Both moons must be new for the moon-gated finds. C: !(trammel | felucca)."""
    return (p.trammel | p.felucca) == 0


def _found_recently(p) -> bool:
    """A reagent spot can't be re-reaped within 16 moves. C: (moves & 0xf0) == f_1e8."""
    return (p.moves & 0xF0) == p.last_found


def _find(game) -> None:
    """'You find...' + Honor karma +5 + stamp the search cooldown. C: U4_SRCH.C C_8D4B."""
    p = game.party
    game.message("You find...")
    p.karma[_HONOR] = min(99, p.karma[_HONOR] + 5)
    p.last_found = p.moves & 0xF0


def _xp(game, member: int, amount: int) -> None:    # C: U4_UTIL.C XP_inc (C_097D)
    c = game.party.chara[member]
    c.xp = min(9999, c.xp + amount)


def _reagent_find(game, idx: int, name: str) -> None:   # C: C_8DAA / C_8DE0
    p = game.party
    if not _moons_dark(p) or _found_recently(p):
        game.message(_NOTHING)
        return
    _find(game)
    game.message(name)
    p.reagents[idx] += game.rng.randint(0, 6) + 2       # C: C_8D6D — U4_RND1(7)+2
    if p.reagents[idx] > 99:
        p.reagents[idx] = 99
        game.message("Dropped some!")


def _item_find(game, bit: int, name: str, xp: int = 400, moon_gated: bool = False) -> None:
    """Grant a one-shot quest item recorded in mItems. C: C_8E16/C_8E46/C_8E77/C_8F51/C_8F81."""
    p = game.party
    if (p.items >> bit) & 1 or (moon_gated and not _moons_dark(p)):
        game.message(_NOTHING)
        return
    p.items |= (1 << bit)
    _find(game)
    game.message(name)
    _xp(game, 0, xp)


def _skull(game) -> None:           # C: U4_SRCH.C C_8EA8
    p = game.party
    # Nothing if already held, the moons aren't dark, or it was already destroyed in the Abyss.
    if ((p.items >> ST_SKULL) & 1 or not _moons_dark(p)
            or (p.items >> ST_CAST_SKULL) & 1):
        game.message(_NOTHING)
        return
    p.items |= (1 << ST_SKULL)
    _find(game)
    game.message("The Skull of Mondain the Wizard!")
    _xp(game, 0, 400)


def _stone_find(game, bit: int, name: str, moon_gated: bool) -> None:    # C: C_8EE8 / C_8F21
    p = game.party
    if (p.stones >> bit) & 1 or (moon_gated and not _moons_dark(p)):
        game.message(_NOTHING)
        return
    p.stones |= (1 << bit)
    _find(game)
    game.message(name)
    _xp(game, 0, 200)


def _mystic_find(game, slots, slot: int, name: str) -> None:
    """Mystic Armour/Weapons — found only once every virtue is fully mastered, i.e. all eight
    karma counters have been zeroed by Avatarhood. C: U4_SRCH.C C_9027 / C_9076."""
    p = game.party
    if slots[slot] or any(p.karma):
        game.message(_NOTHING)
        return
    slots[slot] = 8                                     # C: armors[7]=8 / weapons[15]=8
    _find(game)
    game.message(name)
    _xp(game, 0, 400)


def _rune(game) -> None:            # C: U4_SRCH.C C_90C5
    p = game.party
    vi = _RUNE_VIRTUE[p.loc]
    if (p.runes >> vi) & 1:
        game.message(_NOTHING)
        return
    p.runes |= (1 << vi)
    _find(game)
    game.message(f"The rune of {VIRTUES[vi]}!")
    _xp(game, 0, 100)


def _telescope(game) -> None:       # C: U4_SRCH.C C_8FB1 — peer through Lycaeum's telescope
    # The original lets you dial A-P to view any town map; the map render is a front-end
    # feature, so the headless effect is just the prompt text.
    game.message("You see a knob on the Telescope marked A-P")


# (loc, x, y) -> handler.  Verbatim from U4_SRCH.C D_2920.
SEARCH_TABLE = {
    (0x00, 0xB6, 0x36): lambda g: _reagent_find(g, _MANDRAKE, "Mandrake Root!"),
    (0x00, 0x64, 0xA5): lambda g: _reagent_find(g, _MANDRAKE, "Mandrake Root!"),
    (0x00, 0x2E, 0x95): lambda g: _reagent_find(g, _NIGHTSHADE, "Nightshade!"),
    (0x00, 0xCD, 0x2C): lambda g: _reagent_find(g, _NIGHTSHADE, "Nightshade!"),
    (0x00, 0xB0, 0xD0): lambda g: _item_find(g, ST_BELL, "The Bell of Courage!"),
    (0x00, 0x2D, 0xAD): lambda g: _item_find(g, ST_HORN, "A Silver Horn!"),
    (0x00, 0x60, 0xD7): lambda g: _item_find(g, ST_WHEEL, "The Wheel from the H.M.S. Cape!"),
    (0x00, 0xC5, 0xF5): _skull,
    (0x00, 0xE0, 0x85): lambda g: _stone_find(g, 7, "The Black Stone!", moon_gated=True),
    (0x00, 0x40, 0x50): lambda g: _stone_find(g, 6, "The White Stone!", moon_gated=False),
    (0x02, 0x06, 0x06): lambda g: _item_find(g, ST_BOOK, "The Book of Truth!"),
    (0x10, 0x16, 0x01): lambda g: _item_find(g, ST_CANDLE, "The Candle of Love!"),
    (0x02, 0x16, 0x03): _telescope,
    (0x03, 0x16, 0x04): lambda g: _mystic_find(g, g.party.armors, 7, "Mystic Armour!"),
    (0x04, 0x08, 0x0F): lambda g: _mystic_find(g, g.party.weapons, 15, "Mystic Weapons!"),
    (0x05, 0x08, 0x06): _rune,      # Honesty  (Moonglow)
    (0x06, 0x19, 0x01): _rune,      # Compassion (Britain)
    (0x07, 0x1E, 0x1E): _rune,      # Valor    (Jhelom)
    (0x08, 0x0D, 0x06): _rune,      # Justice  (Yew)
    (0x09, 0x1C, 0x1E): _rune,      # Sacrifice (Minoc)
    (0x0A, 0x02, 0x1D): _rune,      # Honor    (Trinsic)
    (0x01, 0x11, 0x08): _rune,      # Spirituality (Lord British's Castle)
    (0x0D, 0x1D, 0x1D): _rune,      # Humility (Paws)
}


def cmd_search(game) -> None:       # C: U4_SRCH.C CMD_Search (C_913A)
    game.message("Search...")
    p = game.party
    if game.mode <= MOD_BUILDING and p.flying:
        game.message("Drift Only!")                     # C: w_DriftOnly — ballooning, can't search
        return
    handler = SEARCH_TABLE.get((p.loc, p.x, p.y))
    if handler is None:
        game.message(_NOTHING)
    else:
        handler(game)


# --- Peer at a gem (U4_PEER.C CMD_Peer) -------------------------------------
def cmd_peer(game) -> None:
    """C: U4_PEER.C CMD_Peer — spend a gem to view the whole map (full-map render is a
    front-end feature; the state effect is one gem consumed)."""
    if game.party.gems <= 0:
        game.message("Thou hast no gems!")
        return
    game.party.gems -= 1
    game.message("Thou dost peer into a gem and behold the whole land!")
