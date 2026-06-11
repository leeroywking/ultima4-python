# Ultima IV — Python rewrite

A faithful, then refactored-for-editability, Python port of *Ultima IV: Quest of the Avatar*
(1987, Origin Systems), based on the community decompilation of the DOS executables
(`../u4`, by ergonomy_joe).

This is an experiment in agent-driven rewriting. The end goal is a game whose code and
content are legible enough that an agent can, at runtime:

- **Edit** it live from natural language ("max my stats", "add a moongate to a new town of shopkeepers").
- **Tutor** the player — answer "what should I do next?" from the live game state + a U4
  knowledge base, with *progressive hinting* (nudge first, spoil only on demand).

## Status

Playable end-to-end and winnable: title screen → intro/gypsy character creation → overworld,
towns, shops, combat, spells, dungeons, shrines, moongates, and the endgame. The full plan and
the live "start here next" snapshot are in `ROADMAP.md`; per-session context is in the project memory.

**Single source of truth:** the game reads only plain-text/PNG assets at runtime — graphics from
`assets/*.png`, intro/tarot text + menus from `data/intro/*.json`, NPC dialogue from
`data/dialogue/*.json`. The original `.EGA`/`.TLK`/`SRC-TITLE` files are *import sources only*
(converted once by the tools below); editing a PNG or JSON changes the game live, with no code change.

## Layout

- `ultima4/state.py`     — `Party` / `Character`: byte-accurate port of `tParty` / `tChara`. The single source of truth for game state.
- `ultima4/constants.py` — game modes, directions, item bit-flags, keyboard codes.
- `ultima4/data_tables.py` — moongate positions, town/dungeon file lists, place coordinates (ported from `U4_MAIN2.C`).
- `ultima4/savefile.py`  — load/save `PARTY.SAV` and the generic data-file loader.
- `tools/inspect_save.py` — dump a `PARTY.SAV` to verify binary fidelity against the original.

## Game data files

The original copyrighted data files are **not** included. Drop a U4 install's data files
(`PARTY.SAV`, `WORLD.MAP`, `SHAPES.EGA`, `CHARSET.EGA`, `MONSTERS.SAV`, `*.ULT`, `*.DNG`,
`*.TLK`) into `data/`. The free release is available via GOG.

Each ported module cites the C source it came from (e.g. `# C: U4_INIT.C C_C51C`).

## Running

From the repo root (one level up), `./run` bootstraps the venv and dispatches:

- `./run` — play (title → intro → game); `./run town <name>` — debug-boot straight into a town.
- `./run test` — the headless self-test suite (keep it green).
- **Import tools** (regenerate the runtime assets from the originals in `data/`; run once, or after
  dropping in fresh originals):
  - `./run gfx` — `.EGA` graphics → `assets/*.png` (tiles, font, intro pictures).
  - `./run intro` — `SRC-TITLE/TITLE_*.C` → `data/intro/{questions,cards,narrative,menus}.json`.
  - `./run dump` — `.TLK` dialogue → `data/dialogue/*.json`.
- `./run tiles` — regenerate the tile reference (`docs/TILES.md`); `./run agent` — the editor/tutor console.

## Tile reference — `docs/TILES.md`

`docs/TILES.md` is a **generated** visual catalogue of all 256 game tiles: each sprite
rendered from `SHAPES.EGA`, laid out as a 16×16 grid (a tile's hex id is its position —
row = high nibble, column = low nibble), with its name and walkability. The names come
from `ultima4/tiles.py` (`TILE_NAMES`), which is the **single source of truth**; they are
snake_case identifiers so they're safe to reference in code (`lord_british`, `ship_w`,
`force_field`). Regenerate the doc with `./run tiles`.

**Do not edit `docs/TILES.md` by hand** — it's overwritten on every regeneration, and the
names live in `tiles.py`. To change a tile's name, use the **`rename-tile` skill**:

> `/rename-tile 0x4A -> stone_altar`   ·   `/rename-tile force_field_1 -> poison_gas`

The skill edits `TILE_NAMES`, keeps the name snake_case, cascades to animation-frame names
(renaming a creature's base tile renames its frames too), leaves code constants alone unless
you ask for a refactor, regenerates `docs/TILES.md`, and runs the tests. See
`.claude/skills/rename-tile/SKILL.md`.
