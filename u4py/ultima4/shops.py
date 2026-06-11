"""Shops (U4_SHOPS.C) — talk to a shopkeeper behind a sign and buy/sell.

In the original you Talk toward an "alphabet" sign tile (0x60..0x7E) with a merchant
(tile 0x52) behind it; CMD_Talk routes to C_A686, which maps the sign's row to one of
eight shop slots (weapon/armor/food/pub/reagent/healer/inn/guild) and runs that shop.

Each shop is a small menu state machine. Like Conversation, a session is rendering-free:
it exposes intro()/prompt/respond(text)/done so the same engine backs the pygame shop box,
the headless self-test, and (later) an agent. Shop rosters/prices/keepers are plain tables
here — Phase-3 fodder for "make the Britain weapon shop sell magic swords".

Ported faithfully from U4_SHOPS.C; tables cite their C globals.
"""
from __future__ import annotations

from typing import List, Optional

# --- item names (C: U4_CSTES.C D_1E98) --------------------------------------
WEAPON_NAMES = ("Hands", "Staff", "Dagger", "Sling", "Mace", "Axe", "Sword", "Bow",
                "Crossbow", "Flaming Oil", "Halberd", "Magic Axe", "Magic Sword",
                "Magic Bow", "Magic Wand", "Mystic Sword")          # index = weapon id
ARMOR_NAMES = ("Skin", "Cloth", "Leather", "Chain Mail", "Plate Mail",
               "Magic Chain", "Magic Plate", "Mystic Robe")          # index = armor id
REAGENT_NAMES = ("Sulfur Ash", "Ginseng", "Garlic", "Spider Silk",
                 "Blood Moss", "Black Pearl", "Nightshade", "Mandrake")

# --- which shop slot each sign row selects (C: U4_TALK.C D_2CD4) -------------
# Per location (index loc-1): 8 slots [weapon, armor, food, pub, reagent, healer, inn,
# guild]; the value is the sign tile's y-row, 0 == no such shop here.
SHOP_SIGN_Y = (
    (0x00, 0x00, 0x00, 0x00, 0x00, 0x1A, 0x00, 0x00),  # LB
    (0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x00, 0x00),  # Lycaeum
    (0x00, 0x00, 0x00, 0x00, 0x00, 0x0F, 0x00, 0x00),  # Empath
    (0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x00, 0x00),  # Serpent
    (0x00, 0x00, 0x0E, 0x00, 0x1A, 0x1B, 0x02, 0x00),  # Moonglow
    (0x03, 0x07, 0x06, 0x02, 0x00, 0x1D, 0x0C, 0x00),  # Britain
    (0x09, 0x05, 0x00, 0x13, 0x00, 0x06, 0x1A, 0x00),  # Jhelom
    (0x00, 0x00, 0x18, 0x00, 0x00, 0x19, 0x00, 0x00),  # Yew
    (0x1C, 0x00, 0x00, 0x00, 0x00, 0x00, 0x03, 0x00),  # Minoc
    (0x14, 0x18, 0x00, 0x02, 0x00, 0x00, 0x03, 0x00),  # Trinsic
    (0x00, 0x00, 0x11, 0x00, 0x04, 0x1B, 0x0D, 0x00),  # Skara Brae
    (0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00),  # Magincia
    (0x00, 0x04, 0x1A, 0x05, 0x07, 0x00, 0x00, 0x00),  # Paws
    (0x0B, 0x11, 0x00, 0x19, 0x08, 0x00, 0x00, 0x07),  # Den
    (0x14, 0x00, 0x00, 0x16, 0x00, 0x00, 0x15, 0x1A),  # Vesper
    (0x00, 0x00, 0x00, 0x00, 0x00, 0x1A, 0x00, 0x00),  # Cove
)
SLOT_WEAPON, SLOT_ARMOR, SLOT_FOOD, SLOT_PUB, \
    SLOT_REAGENT, SLOT_HEALER, SLOT_INN, SLOT_GUILD = range(8)

# --- weapon shop (C: D_46A2/D_46AE/D_46BA/D_46D2/D_46F2/D_4702) --------------
WEAPON_SHOP_NAMES = ("Windsor Weaponry", "Willard's Weaponry", "The Iron Works",
                     "Duelling Weapons", "Hook's Arms", "Village Arms")
WEAPON_KEEPERS = ("Winston", "Willard", "Peter", "Jumar", "Hook", "Wendy")
WEAPON_ROSTER = ((1, 2, 3, 6), (5, 6, 8, 10), (4, 10, 11, 12),
                 (4, 5, 6, 7), (8, 9, 13, 14), (2, 3, 7, 9))
WEAPON_PRICES = (0, 20, 2, 25, 100, 225, 300, 250, 600, 5, 350, 1500, 2500, 2000, 5000, 7000)
WEAPON_LOC = (0, 0, 0, 0, 0, 1, 2, 0, 3, 4, 0, 0, 0, 5, 6, 0)        # 1-based; 0 == none

# --- armor shop (C: D_4BAE/D_4BB8/D_4BC4/D_4BDC/D_4BEC) ----------------------
ARMOR_SHOP_NAMES = ("Windsor Armour", "Valiant's Armour", "Duelling Armour",
                    "Light Armour", "Basic Armour")
ARMOR_KEEPERS = ("Winston", "Valiant", "Jean", "Pierre", "Limpy")
ARMOR_ROSTER = ((1, 2, 3), (3, 4, 5, 6), (1, 3, 5), (1, 2), (1, 2, 3))
ARMOR_PRICES = (0, 50, 200, 600, 2000, 4000, 7000, 9000)
ARMOR_LOC = (0, 0, 0, 0, 0, 1, 2, 0, 0, 3, 0, 0, 4, 5, 0, 0)

# --- food shop (C: D_6386/D_6390/D_637C/D_636C) -----------------------------
FOOD_SHOP_NAMES = ("The Sage Deli", "Adventure Food", "The Dry Goods",
                   "Food for Thought", "The Market")
FOOD_KEEPERS = ("Shaman", "Windrick", "Donnar", "Mintol", "Max")
FOOD_PRICE = (25, 40, 35, 20, 30)                                    # per 25 rations
FOOD_LOC = (0, 0, 0, 0, 1, 2, 0, 3, 0, 0, 4, 0, 5, 0, 0, 0)

# --- reagent shop (C: D_4180/D_4188/D_4190/D_4170) --------------------------
REAGENT_SHOP_NAMES = ("Magical Herbs", "Herbs and Spice", "The Magics", "Magic Mentar")
REAGENT_KEEPERS = ("Margot", "Sasha", "Shiela", "Shannon")
REAGENT_PRICES = ((2, 5, 6, 3, 6, 9), (2, 4, 9, 6, 4, 8),
                  (3, 4, 2, 9, 6, 7), (6, 7, 9, 9, 9, 1))            # 4 shops x 6 reagents
REAGENT_LOC = (0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 2, 0, 3, 4, 0, 0)

# karma indices into Party.karma (constants.VIRTUES order)
K_HONESTY, K_COMPASSION, K_JUSTICE, K_HONOR = 0, 1, 3, 5


def _ask_int(text: str) -> Optional[int]:
    try:
        return int(text.strip())
    except ValueError:
        return None


class _Shop:
    """Base shop session: intro lines + a prompt + a state-dispatched respond()."""
    def __init__(self, game):
        self.game = game
        self.party = game.party
        self.done = False
        self.state = "greet"
        self.prompt = ""

    def intro(self) -> List[str]:
        return []

    def respond(self, text: str) -> List[str]:
        handler = getattr(self, f"_st_{self.state}", None)
        if handler is None:
            self.done = True
            return []
        return handler(text.strip())

    def _finish(self, *lines: str) -> List[str]:
        self.done = True
        return list(lines)


class BuySellShop(_Shop):
    """Weapons / armor: Buy or Sell, list roster, pick a letter, quantity, confirm.

    Sell price is half the buy price (C: price >> 1). Item letter == chr('A' + id),
    so the dummy id 0 ('A') means 'none / leave'.
    """
    def __init__(self, game, shop_index, kind):
        super().__init__(game)
        self.kind = kind                       # "weapon" or "armor"
        self.i = shop_index
        if kind == "weapon":
            self.names, self.prices = WEAPON_NAMES, WEAPON_PRICES
            self.roster = WEAPON_ROSTER[shop_index]
            self.inv = self.party.weapons
            self.shop_name = WEAPON_SHOP_NAMES[shop_index]
            self.keeper = WEAPON_KEEPERS[shop_index]
        else:
            self.names, self.prices = ARMOR_NAMES, ARMOR_PRICES
            self.roster = ARMOR_ROSTER[shop_index]
            self.inv = self.party.armors
            self.shop_name = ARMOR_SHOP_NAMES[shop_index]
            self.keeper = ARMOR_KEEPERS[shop_index]
        self.roster = [i for i in self.roster if i]     # drop 0 padding
        self.prompt = "Buy or Sell? (B/S)"
        self.item = 0
        self.unit = 0

    def intro(self) -> List[str]:
        return [f"Welcome to {self.shop_name}!",
                f"{self.keeper} says: Art thou here to Buy or Sell?"]

    # greet -> choose buy/sell
    def _st_greet(self, text):
        c = text[:1].upper()
        if c == "B":
            self.state = "buy_pick"
            return self._buy_menu()
        if c == "S":
            self.state = "sell_pick"
            self.prompt = "You sell (letter)?"
            return ["Excellent!  Which wouldst thou sell?"]
        return self._finish(f"{self.keeper} says: Fare thee well!")

    def _buy_menu(self):
        self.prompt = "Your interest (letter)?"
        lines = ["We have:"]
        for i in self.roster:
            lines.append(f"  {chr(ord('A') + i)} - {self.names[i]}  ({self.prices[i]}gp)")
        return lines

    def _st_buy_pick(self, text):
        if not text:
            return self._finish(f"{self.keeper} says: Fare thee well!")
        item = ord(text[:1].upper()) - ord("A")
        if item not in self.roster:
            return ["We do not sell that here."]
        if self.prices[item] > self.party.gold:
            return ["You have not the funds for even one!"]
        self.item = item
        self.state = "buy_qty"
        self.prompt = "How many?"
        return [f"{self.names[item]}: {self.prices[item]}gp each."]

    def _st_buy_qty(self, text):
        n = _ask_int(text)
        self.state = "buy_more"
        self.prompt = "Anything else? (Y/N)"
        if not n or n <= 0:
            return ["Too bad."]
        cost = self.prices[self.item] * n
        if cost > self.party.gold:
            return ["I fear you have not the funds, perhaps something else."]
        self.party.gold -= cost
        self.inv[self.item] = min(99, self.inv[self.item] + n)
        return [f"{self.keeper} says: A fine choice!"]

    def _st_buy_more(self, text):
        if text[:1].upper() == "Y":
            self.state = "buy_pick"
            return self._buy_menu()
        return self._finish(f"{self.keeper} says: Fare thee well!")

    def _st_sell_pick(self, text):
        if not text:
            return self._finish(f"{self.keeper} says: Fare thee well!")
        item = ord(text[:1].upper()) - ord("A")
        if not (0 < item < len(self.names)):
            return ["What is that?"]
        if self.inv[item] == 0:
            return ["Thou dost not own that.  What else?"]
        self.item = item
        self.state = "sell_qty"
        self.prompt = "How many to sell?"
        return [f"How many {self.names[item]} wouldst thou sell? (own {self.inv[item]})"]

    def _st_sell_qty(self, text):
        n = _ask_int(text)
        if not n or n <= 0:
            self.state = "sell_pick"
            self.prompt = "You sell (letter)?"
            return ["Too bad."]
        if n > self.inv[self.item]:
            self.state = "sell_pick"
            self.prompt = "You sell (letter)?"
            return ["You don't have that many!"]
        self.unit = n
        self.state = "sell_confirm"
        self.prompt = "Deal? (Y/N)"
        offer = (n * self.prices[self.item]) >> 1
        return [f"I will give you {offer}gp for {'them' if n > 1 else 'it'}.  Deal?"]

    def _st_sell_confirm(self, text):
        self.state = "sell_pick"
        self.prompt = "You sell (letter)?"
        if text[:1].upper() != "Y":
            return ["Hmmph.  What else?"]
        self.inv[self.item] -= self.unit
        self.party.gold = min(9999, self.party.gold + ((self.unit * self.prices[self.item]) >> 1))
        return ["Fine!  What else?"]


class FoodShop(_Shop):
    """Food: rations sold in packs of 25 (C: Party._food stores food*100)."""
    def __init__(self, game, shop_index):
        super().__init__(game)
        self.i = shop_index
        self.price = FOOD_PRICE[shop_index]
        self.keeper = FOOD_KEEPERS[shop_index]
        self.shop_name = FOOD_SHOP_NAMES[shop_index]
        self.prompt = "Rations? (Y/N)"

    def intro(self):
        return [f"Welcome to {self.shop_name}!",
                f"{self.keeper} says: May I interest you in some rations?"]

    def _st_greet(self, text):
        if text[:1].upper() != "Y":
            return self._finish("Goodbye, come again!")
        self.state = "qty"
        self.prompt = "How many packs of 25?"
        return [f"The best rations, 25 for only {self.price}gp."]

    def _st_qty(self, text):
        n = _ask_int(text)
        if not n or n <= 0:
            return self._finish("Too bad.  Maybe next time.")
        cost = self.price * n
        if cost > self.party.gold:
            if self.price > self.party.gold:
                return self._finish("You cannot afford any!")
            return [f"You can only afford {self.party.gold // self.price} packs."]
        self.party.food = min(999900, self.party.food + 2500 * n)
        self.party.gold -= cost
        self.prompt = "Anything else? (Y/N)"
        self.state = "more"
        return ["Thank you."]

    def _st_more(self, text):
        if text[:1].upper() == "Y":
            self.state = "qty"
            self.prompt = "How many packs of 25?"
            return [f"25 for {self.price}gp."]
        return self._finish("Goodbye.  Come again!")


class ReagentShop(_Shop):
    """Reagents A-F. You name your own price; underpaying costs Honesty/Justice/Honor
    karma, paying fairly raises them (C: SHP_reagent)."""
    def __init__(self, game, shop_index):
        super().__init__(game)
        self.i = shop_index
        self.prices = REAGENT_PRICES[shop_index]
        self.keeper = REAGENT_KEEPERS[shop_index]
        self.shop_name = REAGENT_SHOP_NAMES[shop_index]
        self.prompt = "Need reagents? (Y/N)"
        self.idx = 0
        self.qty = 0
        self.cost = 0

    def intro(self):
        return [f"A blind woman turns to you: Welcome to {self.shop_name}.",
                f"I am {self.keeper}."]

    def _menu(self):
        self.state = "pick"
        self.prompt = "Your interest (A-F)?"
        return ["I have:"] + [f"  {chr(ord('A') + i)} - {REAGENT_NAMES[i]}  ({self.prices[i]}gp)"
                              for i in range(6)]

    def _st_greet(self, text):
        if text[:1].upper() != "Y":
            return self._finish(f"{self.keeper} says: Perhaps another time....")
        return self._menu()

    def _st_pick(self, text):
        if not text:
            return self._finish(f"{self.keeper} says: Perhaps another time....")
        idx = ord(text[:1].upper()) - ord("A")
        if not (0 <= idx < 6):
            return ["I do not have that."]
        self.idx = idx
        self.state = "qty"
        self.prompt = "How many?"
        return [f"We sell {REAGENT_NAMES[idx]} for {self.prices[idx]}gp."]

    def _st_qty(self, text):
        n = _ask_int(text)
        if not n or n <= 0:
            self.prompt = "Anything else? (Y/N)"
            self.state = "more"
            return ["I see, then."]
        self.qty = n
        self.cost = n * self.prices[self.idx]
        self.state = "pay"
        self.prompt = "You pay:"
        return [f"That will be {self.cost}gp.  You pay:"]

    def _st_pay(self, text):
        paid = _ask_int(text)
        self.prompt = "Anything else? (Y/N)"
        self.state = "more"
        if paid is None or paid <= 0:
            return ["I see, then."]
        if paid < self.cost:                              # haggling down = dishonest
            diff = self.cost - paid
            dec = 4 if diff < 12 else diff // 3
            for k in (K_HONESTY, K_JUSTICE, K_HONOR):
                self.party.karma[k] = max(0, self.party.karma[k] - dec)
        if paid > self.party.gold:
            return ["It seems you have not the gold!"]
        for k in (K_HONESTY, K_JUSTICE, K_HONOR):
            self.party.karma[k] = min(99, self.party.karma[k] + 2)
        self.party.gold -= paid
        self.party.reagents[self.idx] = min(99, self.party.reagents[self.idx] + self.qty)
        return ["Very good."]

    def _st_more(self, text):
        if text[:1].upper() == "Y":
            return self._menu()
        return self._finish(f"{self.keeper} says: Perhaps another time....")


# --- remaining shop types (v1 stubs; need HP/rest/time/item systems first) ---------------
# These mirror BuySellShop/FoodShop/ReagentShop but touch systems not built yet, so for now
# open_shop() returns a "coming soon" message instead of instantiating them. C functions noted.
class TavernShop(_Shop):
    """C: SHP_pub — buy plates of the house specialty (food) or pay for a rumor/clue."""
    LOC = (0, 0, 0, 0, 0, 1, 2, 0, 0, 3, 0, 0, 4, 5, 6, 0)   # C: D_5EE8
    SHOP_NAMES = ("Jolly Spirits", "The Bloody Pub", "The Keg Tap", "Folley Tavern",
                  "Captain Black Tavern", "Axe 'n Ale")
    KEEPERS = ("Sam", "Celestial", "Terran", "Greg 'n Rob", "The Cap'n", "Arron")
    SPECIALTY = ("Lamb Chops", "Dragon Tartar", "Brown Beans", "Folley Filet",
                 "Dog Meat Pie", "Green Granukit")
    PLATE_PRICE = (4, 2, 3, 2, 4, 2)                          # C: D_5F28
    TIP_TOPICS = ("black stone", "sextant", "white stone", "mandrake", "skull", "nightshade")
    TIP_PRICE = (20, 30, 10, 40, 99, 25)                     # C: D_5EF8
    TIP_CLUES = (                                            # C: D_5F42
        "Ah, the Black Stone.  Only the wizard Merlin knows where it lies.",
        "For navigation a Sextant is vital -- ask for item 'D' in the Guild shops!",
        "The White Stone?  The old Hermit Sloven knows; he lives near Lock Lake.",
        "The last to hold Mandrake was an old alchemist named Calumny.",
        "That evilest of things?  Find the beggar Jude -- he is very, very poor!",
        "Of Nightshade: seek out Virgil, in Trinsic!",
    )

    def __init__(self, game, i):
        super().__init__(game)
        self.i = i
        self.keeper = self.KEEPERS[i]
        self.shop_name = self.SHOP_NAMES[i]
        self.prompt = "Food or a Tip? (F/T)"

    def intro(self):
        return [f"Welcome to {self.shop_name}.", f"{self.keeper} says: What'll it be?"]

    def _st_greet(self, text):
        c = text[:1].upper()
        if c == "F":
            self.state = "food_qty"
            self.prompt = "How many plates?"
            return [f"Our specialty is {self.SPECIALTY[self.i]}, {self.PLATE_PRICE[self.i]}gp a plate."]
        if c == "T":
            self.state = "tip"
            self.prompt = "What subject?"
            return ["What'd ya like to know? (e.g. " + ", ".join(self.TIP_TOPICS) + ")"]
        return self._finish(f"{self.keeper} says: Bye!")

    def _st_food_qty(self, text):
        n = _ask_int(text)
        self.prompt = "Anything else? (F/T)"
        self.state = "more"
        if not n or n <= 0:
            return ["Too bad."]
        price = self.PLATE_PRICE[self.i]
        n = min(n, self.party.gold // price) if price else n
        if n <= 0:
            return ["Ya cannot afford any!"]
        self.party.gold -= price * n
        self.party.food = min(999900, self.party.food + 100 * n)
        return [f"{self.keeper} serves {n} plate(s).  Enjoy!"]

    def _st_tip(self, text):
        self.prompt = "Anything else? (F/T)"
        self.state = "more"
        probe = text.strip().lower()
        topic = next((k for k, t in enumerate(self.TIP_TOPICS) if t.startswith(probe[:5])), None)
        if topic is None or topic < self.i:               # C: loc_C < D_9142 -> can't help
            return ["'Fraid I can't help ya there, friend!"]
        if self.party.gold < self.TIP_PRICE[topic]:
            return [f"That subject's a bit foggy... it'd cost {self.TIP_PRICE[topic]}gp."]
        self.party.gold -= self.TIP_PRICE[topic]
        return [f"{self.keeper} says: {self.TIP_CLUES[topic]}"]

    def _st_more(self, text):
        c = text[:1].upper()
        if c == "F":
            self.state = "food_qty"; self.prompt = "How many plates?"
            return [f"{self.PLATE_PRICE[self.i]}gp a plate."]
        if c == "T":
            self.state = "tip"; self.prompt = "What subject?"
            return ["What'd ya like to know?"]
        return self._finish(f"{self.keeper} says: Bye!")


class HealerShop(_Shop):
    """C: SHP_healer — Cure poison (100gp), Heal HP (200gp), Resurrect (300gp), or donate
    blood (Sacrifice karma). Acts on the first party member who needs it."""
    LOC = (1, 2, 3, 4, 5, 6, 7, 8, 0, 0, 9, 0, 0, 0, 0, 10)  # C: D_5788
    SHOP_NAMES = ("The Royal Healer", "The Truth Healer", "The Love Healer", "Courage Healer",
                  "The Healer", "Wound Healing", "Heal and Health", "Just Healing",
                  "The Mystic Heal", "The Healer Shop")
    KEEPERS = ("Pendragon", "Starfire", "Salle'", "Windwalker", "Harmony", "Celest",
               "Triplet", "Justin", "Spiran", "Quat")
    K_SACRIFICE = 4                                          # constants.VIRTUES index

    def __init__(self, game, i):
        super().__init__(game)
        self.keeper = self.KEEPERS[i]
        self.shop_name = self.SHOP_NAMES[i]
        self.prompt = "Cure, Heal, Resurrect, or give Blood? (C/H/R/B)"

    def intro(self):
        return [f"Welcome to {self.shop_name}.", f"I am {self.keeper}.  How may I aid thee?"]

    def _members(self):
        return self.party.members

    def _st_greet(self, text):
        c = text[:1].upper()
        p = self.party
        self.prompt = "Anything else? (C/H/R/B)"
        if c == "C":                                        # Cure poison (free if you can't pay)
            m = next((ch for ch in self._members() if ch.status == "P"), None)
            if not m:
                return ["None here suffer from Poison."]
            if p.gold >= 100:
                p.gold -= 100
            m.status = "G"
            return ["Thou art cured!"]
        if c == "H":                                        # Heal HP, 200gp
            m = next((ch for ch in self._members() if ch.alive and ch.hp < ch.hp_max), None)
            if not m:
                return ["Thou art already quite healthy!"]
            if p.gold < 200:
                return ["Thou hast not enough gold (200gp)."]
            p.gold -= 200; m.hp = m.hp_max
            return ["Thy wounds are healed!"]
        if c == "R":                                        # Resurrect the dead, 300gp
            m = next((ch for ch in self._members() if ch.status == "D"), None)
            if not m:
                return ["None here are dead, fool!"]
            if p.gold < 300:
                return ["Thou hast not enough gold (300gp)."]
            p.gold -= 300; m.status = "G"; m.hp = m.hp_max
            return [f"{m.name} shall live again!"]
        if c == "B":                                        # Blood donation -> Sacrifice karma
            avatar = p.chara[0]
            if avatar.hp <= 100:
                return ["Thou art too weak to give blood."]
            avatar.hp -= 100
            p.karma[self.K_SACRIFICE] = min(99, p.karma[self.K_SACRIFICE] + 5)
            return ["Thou art a great help.  We are in dire need!"]
        return self._finish(f"{self.keeper} says: Fare thee well.")

    _st_more = _st_greet
class InnShop(_Shop):
    """C: SHP_inn — rest the night: pay, and conscious members wake fully healed."""
    LOC = (0, 0, 0, 0, 1, 2, 3, 0, 4, 5, 6, 0, 0, 0, 7, 0)   # C: D_5484
    COST = (20, 15, 10, 30, 15, 5, 1)                        # C: D_54A4
    SHOP_NAMES = ("The Honest Inn", "Britannia Manor", "The Inn of Ends", "Wayfarer's Inn",
                  "Honorable Inn", "The Inn of the Spirits", "The Sleep Shop")

    def __init__(self, game, i):
        super().__init__(game)
        self.cost = self.COST[i]
        self.shop_name = self.SHOP_NAMES[i]
        self.prompt = f"Rest the night for {self.cost}gp? (Y/N)"

    def intro(self):
        return [f"Welcome to {self.shop_name}.  Wouldst thou stay the night?"]

    def _st_greet(self, text):
        if text[:1].upper() != "Y":
            return self._finish("Perhaps another time.")
        if self.party.gold < self.cost:
            return self._finish("Thou hast not the gold.")
        self.party.gold -= self.cost
        for c in self.party.members:                        # a night's rest = full heal
            if c.status == "G":
                c.hp = c.hp_max
        return self._finish("Thou dost sleep soundly and awake refreshed!")
class GuildShop(_Shop):
    """C: SHP_guild — the smuggler's black market: torches, gems, keys, a sextant."""
    SHOP_NAMES = ("Pirate's Guild", "The Guild Shop")
    KEEPERS = ("One Eyed Willey", "Long John Leary")
    LOC = (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 0)   # C: D_5196 (Den, Vesper)
    PRICES = (50, 60, 60, 900)                                # C: D_51A6
    QTY = (5, 5, 6, 1)                                        # C: D_51AE
    GOODS = ("torches", "gems", "keys", "sextants")           # C: A/B/C/D -> Party fields
    PITCH = ("5 long-lasting Torches for 50gp.", "5 magical mapping Gems for 60gp.",
             "Magical Keys, 6 for 60gp.", "A Sextant... 900 gold!")

    def __init__(self, game, i):
        super().__init__(game)
        self.keeper = self.KEEPERS[i]
        self.shop_name = self.SHOP_NAMES[i]
        self.prompt = "See my goods? (Y/N)"

    def intro(self):
        return [f"Avast ye mate!  Welcome to {self.shop_name}.", f"I am {self.keeper}."]

    def _menu(self):
        self.state = "pick"
        self.prompt = "What'll it be? (A-D)"
        return ["I gots:"] + [f"  {chr(ord('A') + i)} - {self.PITCH[i]}" for i in range(4)]

    def _st_greet(self, text):
        if text[:1].upper() != "Y":
            return self._finish(f"{self.keeper} says: See ya, matie!")
        return self._menu()

    def _st_pick(self, text):
        if not text:
            return self._finish(f"{self.keeper} says: See ya, matie!")
        idx = ord(text[:1].upper()) - ord("A")
        if not (0 <= idx < 4):
            return ["I don't sell that."]
        if self.party.gold < self.PRICES[idx]:
            self.prompt = "What'll it be? (A-D)"
            return ["What? Can't pay!  Buzz off, swine!"]
        self.party.gold -= self.PRICES[idx]
        cur = getattr(self.party, self.GOODS[idx])
        setattr(self.party, self.GOODS[idx], min(99, cur + self.QTY[idx]))
        self.prompt = "See more? (Y/N)"
        self.state = "more"
        return ["Fine... fine..."]

    def _st_more(self, text):
        if text[:1].upper() == "Y":
            return self._menu()
        return self._finish(f"{self.keeper} says: See ya, matie!")
class StableShop(_Shop):      # C: SHP_horse — buy a horse (needs transport.py)
    def __init__(self, game, i): raise NotImplementedError


# --- factory: build the right session for a shop slot (C: C_A686 / D_2D54) ---
_NOT_YET: dict = {}     # all 8 sign-board shop slots are implemented; stable/hawkwind are
                        # the C "patch" slots (8/9), reached by their own paths, not signs.


def open_shop(game, slot: int):
    """Return a shop session for `slot` at the party's location, or (None, message)."""
    loc = game.party.loc
    if slot == SLOT_WEAPON and WEAPON_LOC[loc - 1]:
        return BuySellShop(game, WEAPON_LOC[loc - 1] - 1, "weapon"), None
    if slot == SLOT_ARMOR and ARMOR_LOC[loc - 1]:
        return BuySellShop(game, ARMOR_LOC[loc - 1] - 1, "armor"), None
    if slot == SLOT_FOOD and FOOD_LOC[loc - 1]:
        return FoodShop(game, FOOD_LOC[loc - 1] - 1), None
    if slot == SLOT_REAGENT and REAGENT_LOC[loc - 1]:
        return ReagentShop(game, REAGENT_LOC[loc - 1] - 1), None
    if slot == SLOT_GUILD and GuildShop.LOC[loc - 1]:
        return GuildShop(game, GuildShop.LOC[loc - 1] - 1), None
    if slot == SLOT_PUB and TavernShop.LOC[loc - 1]:
        return TavernShop(game, TavernShop.LOC[loc - 1] - 1), None
    if slot == SLOT_HEALER and HealerShop.LOC[loc - 1]:
        return HealerShop(game, HealerShop.LOC[loc - 1] - 1), None
    if slot == SLOT_INN and InnShop.LOC[loc - 1]:
        return InnShop(game, InnShop.LOC[loc - 1] - 1), None
    if slot in _NOT_YET:
        return None, f"(The {_NOT_YET[slot]} is not yet open — coming soon.)"
    return None, "Funny, no response!"
