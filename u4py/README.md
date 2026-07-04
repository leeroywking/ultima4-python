# Ultima IV — Python rewrite

A faithful, then refactored-for-editability, Python port of *Ultima IV: Quest of the Avatar*
(1987, Origin Systems), based on the community decompilation of the DOS executables (by
ergonomy_joe). It runs self-contained — clone and play, no original game files needed.

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
`data/dialogue/*.json`, maps from `data/maps/*.txt`, the party seed from `data/party_start.json`.
These are committed, so no original game files are needed; editing a PNG or JSON changes the game
live, with no code change.

## Play it with your agent

The fun way to run this is to let an AI agent play while you **watch each turn**. In Claude Code:

1. **Build once:** `./run test` (creates the venv, expects `81/81`).
2. **Restart / reload Claude Code and approve the `ultima4` MCP server** when prompted (the repo
   ships a `.mcp.json`). If no prompt appears, run `./run install-mcp` and restart.
3. **Ask your agent to play** — e.g. *"play Ultima IV and take me through meeting Lord British."*
   It drives the game through the MCP tools and each move renders in the conversation, so you
   follow along.

Prefer a live game window (a real display, not SSH)? `./run watch` animates an agent playing on
screen; `./run` plays it yourself with the keyboard; `./run demo` lists scripted set-pieces.

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

## Running (`./run`)

The `./run` launcher lives at the **repo root** — the parent of this `u4py/` directory (so from
here, `../run`). It bootstraps the venv on first use and dispatches everything below. The only
prereq is `python3` with `venv` (`sudo apt install python3-venv`; the script errors helpfully if
it's missing).

Windowed (needs a display):
- `./run` — play it yourself (title → intro → game); `./run town <name>` — debug-boot into a town.
- `./run watch` — watch an agent play live in the window (`--scenario <name>` replays a demo live).

Headless (no display — CI, SSH, agents):
- `./run test` — the self-test suite (keep it green).
- `./run smoke [out.png]` — render one frame to a PNG under `SDL_VIDEODRIVER=dummy` and exit.
- `./run demo` — scripted live-demo playthroughs (`./run demo` lists them); `./run talk` — Talk demo.
- `./run agent-play --do "move N" …` — drive the game as an agent (stateless observe/act replay).

Agent server + tooling:
- `./run mcp` — the MCP server so an external agent can play (headless); **`./run mcp --window`**
  also opens a visible window mirroring the session, so a human watches the agent play live.
- `./run install-mcp` — register the MCP server with Claude Code; `./run agent` — editor/tutor console.
- `./run tiles` — regenerate the tile reference (`docs/TILES.md`) from `assets/shapes.png`.

The runtime assets are **pre-generated and committed** (`data/maps/*.txt`, `data/dialogue/*.json`,
`data/intro/*.json`, `data/party_start.json`, `assets/*.png`) — the game needs no original files.

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
