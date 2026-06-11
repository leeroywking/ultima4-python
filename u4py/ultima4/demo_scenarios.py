"""The live-demo scenario suite — short scripts that play the real game through a notable
moment and assert it happened. Each is written against the Director's verbs (demo.py) and
runs headlessly in milliseconds, producing a transcript. Add one by writing a function and
registering it in SCENARIOS; the CLI (`./run demo`) and the live-demo skill pick it up.

These mirror the verified flows in tools/selftest.py, but framed as a watchable playthrough.
"""
from __future__ import annotations

from typing import Callable, Dict

from .constants import MOD_OUTDOORS, MOD_DUNGEON, MOD_COMBAT
from .demo import Director
from .tiles import LORD_BRITISH, MERCHANT


# --- scenarios ---------------------------------------------------------------
def lord_british_heal(d: Director) -> None:
    """Visit Lord British in his throne room and have him heal a wounded companion."""
    d.narrate("Enter Lord British's Castle and climb to the throne room.")
    d.enter("lcb", "castle")
    d.goto(27, 3)                                   # a ladder up to the upper floor
    d.do("K", label="Klimb the ladder")

    def stand_by_lb(dd: Director):
        lb = next(n for n in dd.game.location.npcs if n.tile == LORD_BRITISH)
        dd.game.party.x, dd.game.party.y = lb.x, lb.y + 1     # just south -> Talk North
        dd.game.party.met_lb = 1
        dd.game.party.member_count = 1
        c = dd.game.party.chara[0]
        c.xp, c.hp_max, c.hp, c.status = 0, 100, 5, "G"       # gravely wounded (5/100)
    d.setup(stand_by_lb, "a companion at 5/100 HP, standing before the throne")
    d.minimap(label="throne room")

    d.narrate('Talk to Lord British and answer "health".')
    d.talk("N", "health", "N")
    d.expect(d.party.chara[0].hp == 100, "Lord British fully heals the wounded companion")
    d.say("bye")


def talk_to_townsfolk(d: Director) -> None:
    """Walk up to a citizen of Britain and chat — ask their name and job."""
    d.narrate("Enter Britain and find someone to talk to.")
    d.enter("britain")

    chosen = {}

    def find_npc(dd: Director):
        loc = dd.game.location
        for n in loc.npcs:
            if n.tlkidx <= 0 or n.tile in (MERCHANT, LORD_BRITISH):
                continue
            for dx, dy, toward in ((0, 1, "N"), (0, -1, "S"), (1, 0, "W"), (-1, 0, "E")):
                px, py = n.x + dx, n.y + dy
                t = loc.tile_at(px, py)
                if t is not None and loc.npc_at(px, py) is None and _walkable(t):
                    dd.game.party.x, dd.game.party.y = px, py
                    chosen["dir"] = toward
                    chosen["name"] = n
                    return
        raise RuntimeError("no reachable talkable NPC found in Britain")
    d.setup(find_npc, "stand next to a citizen")
    d.minimap(label="a street in Britain")

    d.narrate("Strike up a conversation.")
    d.talk(chosen["dir"], "name", "job", "bye")
    d.expect(d.game.active is None, "the conversation opens and closes cleanly")


def buy_a_weapon(d: Director) -> None:
    """Talk into a weapon shop's sign-board and buy a dagger."""
    d.narrate("Enter Britain and step up to the weapon shop's sign.")
    d.enter("britain")
    d.goto(5, 4)                                    # just south of the weapon sign at (5,3)
    d.setup(lambda dd: setattr(dd.game.party, "gold", 100), "100 gold in pocket")

    d.narrate("Talk north into the sign to open the shop, then buy one dagger.")
    d.talk("N", "B", "C", "1", "N")                 # Buy, dagger (id 'C'=2gp), one, then leave
    d.expect(d.party.weapons[2] >= 1, "a dagger is now in the pack")
    d.expect(d.party.gold == 98, "2 gold was deducted")


def heal_at_the_inn(d: Director) -> None:
    """Rest at Britain's inn to recover to full health."""
    d.narrate("Enter Britain; a companion is wounded.")
    d.enter("britain")

    def setup(dd: Director):
        p = dd.game.party
        p.loc, p.member_count, p.gold = 6, 1, 50
        c = p.chara[0]
        c.status, c.hp, c.hp_max = "G", 20, 100
        from .shops import InnShop
        dd.game._begin(InnShop(dd.game, 1))         # step up to the inn desk (slot 1 = 15gp)
    d.setup(setup, "20/100 HP, 50 gold, at the inn desk")

    d.narrate("Pay for a night's rest.")
    d.say("Y", label="Yes, rest")
    d.expect(d.party.chara[0].hp == 100, "a night's rest restores full HP")
    d.expect(d.party.gold == 35, "the room cost 15 gold")


def mix_and_cast_heal(d: Director) -> None:
    """Mix a Heal spell from reagents, then cast it."""
    d.narrate("In Britain, prepare to do some magic.")
    d.enter("britain")

    def setup(dd: Director):
        p = dd.game.party
        p.member_count = 1
        c = p.chara[0]
        c.char_class, c.intel = chr(0), 99          # a Mage (deep mana pool)
        c.status, c.hp, c.hp_max, c.mp = "G", 10, 100, 50
        p.reagents[1] = p.reagents[3] = 5           # Ginseng + Spider Silk = the Heal recipe
    d.setup(setup, "a Mage at 10/100 HP with ginseng + spider silk")

    d.narrate("Mix the Heal spell (Ginseng + Spider Silk).")
    d.do("M", label="Mix")
    d.say("H", "B", "D", "mix", label="Heal: ginseng(B) + spider silk(D)")
    d.expect(d.party.mixtures[7] == 1, "one Heal charge is mixed")

    d.narrate("Cast it.")
    d.do("C", label="Cast")
    d.say("H", label="Heal")
    d.expect(d.party.chara[0].hp > 10, "the Heal spell restores HP")


def first_dungeon(d: Director) -> None:
    """Enter the dungeon Deceit, explore a little, descend a level, and climb back out."""
    d.narrate("Step onto the entrance to Deceit and descend into the dark.")
    d.goto(50, 50)

    def enter_deceit(dd: Director):
        from . import dungeon
        dungeon.enter_dungeon(dd.game, 0x11)        # 0x11 = Deceit
    d.setup(enter_deceit, "enter Deceit")
    d.expect(d.game.mode == MOD_DUNGEON, "we are first-person in the dungeon")
    d.minimap(label="Deceit level 1")

    d.narrate("Look around and feel for a way down.")
    d.do("RIGHT", label="turn right")
    d.do("UP", label="advance")
    d.minimap(label="after moving")

    def to_down_ladder(dd: Director):
        D = dd.game.dungeon
        for y in range(8):
            for x in range(8):
                if D.tile(x, y, 0) & 0xF0 == 0x20:  # a down-ladder
                    D.x, D.y = x, y
                    return
        raise RuntimeError("no down-ladder on level 1")
    d.setup(to_down_ladder, "walk to a ladder down")
    d.do("D", label="Descend")
    d.expect(d.game.dungeon.z == 1, "we descend to level 2")
    d.minimap(label="Deceit level 2")

    d.narrate("Enough for now — climb back out.")
    d.do("X", label="exit the dungeon")
    d.expect(d.game.mode == MOD_OUTDOORS, "back on the overworld")


def win_a_fight(d: Director) -> None:
    """Get jumped by a rat and cut it down, returning victorious to the overworld."""
    d.narrate("On the road, a monster attacks!")

    def setup(dd: Director):
        p = dd.game.party
        p.member_count = 1
        c = p.chara[0]
        c.status, c.hp, c.hp_max, c.weapon = "G", 100, 100, 6   # a Sword, full HP
    d.setup(setup, "a sword-armed fighter at full HP")

    def start(dd: Director):
        from . import combat
        cs = combat.start_encounter(dd.game, 0x90)              # rats
        # plant one weak rat right beside us so the demo is short and deterministic
        cs.monsters[:] = [combat.Unit(cs.party_units[0].x + 1, cs.party_units[0].y, 0x90, 4, 4)]
    d.setup(start, "a lone rat appears beside us")
    d.expect(d.game.mode == MOD_COMBAT, "combat begins on the arena")
    d.minimap(label="the arena")

    d.narrate("Attack east until the rat falls.")
    for _ in range(12):
        if d.game.combat is None:
            break
        d.do("A", "E", label="Attack East")
    d.expect(d.game.mode == MOD_OUTDOORS, "victory returns us to the overworld")


# --- registry ----------------------------------------------------------------
SCENARIOS: Dict[str, dict] = {
    "lord_british_heal": {
        "fn": lord_british_heal, "tags": ["castle", "talk", "heal"],
        "desc": "Lord British heals a wounded companion in his throne room."},
    "talk_to_townsfolk": {
        "fn": talk_to_townsfolk, "tags": ["town", "talk"],
        "desc": "Chat with a citizen of Britain (name / job)."},
    "buy_a_weapon": {
        "fn": buy_a_weapon, "tags": ["town", "shop"],
        "desc": "Buy a dagger from Britain's weapon shop."},
    "heal_at_the_inn": {
        "fn": heal_at_the_inn, "tags": ["town", "shop", "heal"],
        "desc": "Rest at the inn to recover full HP."},
    "mix_and_cast_heal": {
        "fn": mix_and_cast_heal, "tags": ["magic"],
        "desc": "Mix a Heal spell from reagents and cast it."},
    "first_dungeon": {
        "fn": first_dungeon, "tags": ["dungeon"],
        "desc": "Enter Deceit, descend a level, and climb back out."},
    "win_a_fight": {
        "fn": win_a_fight, "tags": ["combat"],
        "desc": "Defeat a rat in arena combat and return to the overworld."},
}


def _walkable(tile: int) -> bool:
    from .tiles import is_walkable
    return is_walkable(tile)


def run(name: str, seed: int = 7, stage=None) -> Director:
    """Run one scenario and return the finished Director (carrying the transcript).

    Pass a `stage` (ultima4.stage.PygameStage) to play it live on screen / capture frames.
    """
    if name not in SCENARIOS:
        raise KeyError(f"unknown scenario {name!r}; known: {', '.join(sorted(SCENARIOS))}")
    d = Director(seed=seed)
    d.stage = stage
    SCENARIOS[name]["fn"](d)
    if stage is not None:
        stage.finish(d.game, banner="demo complete")
    return d


def run_all(seed: int = 7) -> Dict[str, Director]:
    return {name: run(name, seed) for name in SCENARIOS}
