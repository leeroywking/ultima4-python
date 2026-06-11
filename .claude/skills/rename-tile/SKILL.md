---
name: rename-tile
description: Rename one or more game tiles in the Ultima IV Python port. Use when a tile's name in tiles.py / docs/TILES.md is wrong, unclear, or should change (e.g. "rename 0x4A to stone_altar", "force_field_1 is actually poison_gas", "these tile names are bad"). Updates TILE_NAMES (the single source of truth), keeps names snake_case, cascades to animation-frame names, leaves code constants alone unless asked, regenerates the doc, and runs the tests.
---

# Rename a tile

Tile names live in `u4py/ultima4/tiles.py` as the `TILE_NAMES` dict (tile id → snake_case
name). That dict is the **single source of truth**: `docs/TILES.md`, `tile_name()`, and any
data/tutor/editor layer all derive from it. A trailing normalization pass forces every value
to snake_case, so spaces/caps in the literal are fine but prefer writing them clean.

## Input
The user gives one or more renames as `<id-or-current-name> -> <new name>`, e.g.
`0x4A -> stone_altar`, `ship_rail -> ship_railing`, `0x30,0x31 -> energy_wall`.

## Steps
Work from `/home/ein/projects/ultimate_rewrite` (the repo root; `./run` lives here, the venv
is `u4py/.venv`).

1. **Resolve each tile id.** If given `0xNN`, use it. If given a current name, look it up:
   `u4py/.venv/bin/python -c "import sys;sys.path.insert(0,'u4py');from ultima4.tiles import TILE_NAMES;print([hex(k) for k,v in TILE_NAMES.items() if v=='<name>'])"`

2. **Read `u4py/ultima4/tiles.py`** and find how that id gets its name:
   - **Explicit key** in the `TILE_NAMES` dict literal → Edit that value in place.
   - **Generated** name (animation frames like 0x21/0x23…, the A–Z letters 0x60–0x79, the
     sign glyphs, monster frames 0x9N…): it is derived from a base tile by the
     `_FRAME_GROUPS` / letter loops near the bottom of the dict.
       - To rename **just one frame**, add an explicit `0xNN: "new_name"` entry to the dict
         literal — an explicit key wins over the generated one (`setdefault`).
       - To rename **the whole creature/object**, rename the **base** tile's literal value;
         its frames update automatically (e.g. renaming `0x20: "mage"` also yields
         `mage2`/etc.). Prefer this when the user means the creature, not a single frame.

3. **Keep it snake_case** — `[a-z0-9_]` only. (The normalization pass slugifies anyway, but
   write it clean so the literal reads well.)

4. **Code constants are separate — do not touch them unless asked.** Some tiles also have an
   UPPER_SNAKE constant lower in `tiles.py` (e.g. `LORD_BRITISH = 0x5E`, `MERCHANT`, `DOOR`)
   that `game.py`/`dialogue.py` import and compare against. Those are **code identifiers**, not
   display names; renaming a tile's display name must NOT change them. If a renamed tile has a
   matching constant, mention it in the report but leave it. Only rename a constant if the user
   explicitly asks for a code refactor — and then update every `from .tiles import …` and use
   site, and run the tests.

5. **Fix the inline comment** if the entry (or the `0x30-0x36` block) has a justification
   comment that the new name contradicts.

6. **Regenerate the doc:** `./run tiles` (rewrites `docs/TILES.md` and the sprite PNGs).

7. **Verify:** `./run test` must stay green (22+ checks). If a check that asserts a specific
   name breaks, that's a real consumer of the name — update it too.

8. **Report**: each id, old → new, any frames that cascaded, and any related code constant you
   deliberately left untouched.

## Don't
- Don't edit the `_FRAME_GROUPS` / letter-generation loops unless the *pattern itself* changed
  (e.g. a creature turns out to have 4 frames instead of 2).
- Don't rename in `docs/TILES.md` directly — it's generated; always go through `tiles.py`.
