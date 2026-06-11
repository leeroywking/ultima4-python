# Playing Ultima IV with an AI agent

This is a **faithful Python port of Ultima IV: Quest of the Avatar**, built so that an AI agent
(yours or someone else's) can perceive the game, choose from a small set of legal actions, and
play it turn by turn. The engine is a careful port of the decompiled DOS source; the world,
dialogue, shops, dungeons, combat, and the virtue/quest systems all run headlessly behind one
stable interface: `ultima4.env.UltimaEnv`.

This document is the integration guide. If you are writing an agent, start at **Quickstart**,
then read **The observe/act contract**.

---

## Quickstart

From a checkout (no install needed — the `./run` launcher bootstraps an isolated venv):

```bash
./run agent-play                                   # print the opening observation (seed 7)
./run agent-play --seed 7 --do "move S" --do "move E" --do "key E"   # walk into a town
./run agent-play --seed 7 --do "key T" --do "move N" --full          # full per-step trace
./run agent-play ... --json                         # raw JSON observation (for tooling)
```

Run the **reference agent** — a small, heavily-commented random-walk player that doubles as
living documentation of the loop:

```bash
u4py/.venv/bin/python examples/random_agent.py --seed 7 --max-turns 40
./run agent-demo --seed 7 --max-turns 40            # once the run subcommand is wired (below)
```

Its summary at the end reports the turns played, final location, gold/food, and whether it
managed to enter a town.

After `pip install ultima4-py` (see **Packaging**), two console scripts are available:

```bash
ultima4-agent --seed 7 --max-turns 40   # the reference agent
ultima4-env-info                        # prints this contract + a live opening observation
```

---

## The observe/act contract

The whole game is driven through one class, `ultima4.env.UltimaEnv`:

```python
from ultima4.env import UltimaEnv

env = UltimaEnv(seed=7)        # deterministic given the seed
obs = env.observe()            # perceive: a plain-JSON dict (no engine objects)
print(obs["legal_actions"])    # exactly the actions valid right now
obs = env.act("move N")        # act: returns the next observation
# ...loop until obs["won"] or your turn budget...
```

Methods:

| Method | Returns | Notes |
|---|---|---|
| `UltimaEnv(seed=7)` | env | Construct. Deterministic given `seed`. |
| `.reset(seed=None)` | obs | Rebuild the game; reuse current seed if `None`. |
| `.observe(radius=4)` | obs | Perceive without acting. |
| `.act(action_str)` | obs | Apply one action, return the resulting observation. |
| `.legal_actions()` | list[str] | Actions valid in the current state (also in `obs`). |
| `.play(actions)` | list[obs] | Apply a sequence; one observation per action (replay). |

### The action grammar

Every action is a short string:

| Action | Meaning |
|---|---|
| `move N` / `move S` / `move E` / `move W` | Compass movement (N = up/north). |
| `key <LETTER>` | A command key: one of `A B C D E F G H I J K L M O P Q R S T U W X Z`. Friendly names below. |
| `say <text>` | Free text into an **active** Talk/shop interaction (e.g. `say health`, `say bye`). |
| `pass` | Wait one turn (also `wait`). |

The command letters (`key X`) map to the original Ultima IV command set:

```
A attack   B board    C cast     D descend  E enter    F fire     G get
H hole-up  I ignite   J jimmy    K klimb    L locate   M mix      O open
P peer     Q quit     R ready    S search   T talk     U use      W wear
X x-it     Z ztats
```

Some commands then ask for a direction; when that happens the engine sets a pending state and
`legal_actions` narrows to just `move N/S/E/W` for the next action (e.g. `key E` to Enter a
town, then a direction, or — when you are standing on the town tile — it enters immediately).

### `legal_actions` — read this every turn

`obs["legal_actions"]` is the single most useful field: it lists **exactly** what is valid in
the current state, so your agent never has to guess. It changes with context:

- **Outdoors / in town:** the four moves, `pass`, and the full `key <LETTER>` command set.
- **A direction is pending:** only `move N/S/E/W`.
- **Combat:** `move N/S/E/W`, `key A` (attack), `pass`.
- **Dungeon:** relative moves (`move N (advance)`, `move E (turn right)`, …) plus `key K/D/X/C/Z`.
- **A Talk/shop interaction is active:** `say <keyword>` hints (`name`, `job`, `health`, `look`,
  `join`, `bye`) plus `say <text>` for free text.

### The observation fields

Every `observe()`/`act()` returns a dict with these keys:

| Field | Type | Meaning |
|---|---|---|
| `schema` | int | Observation schema version (currently `1`). |
| `mode` | str | `outdoors`, `building`, `dungeon`, or `combat`. |
| `moves` | int | Turn counter. |
| `position` | `{x, y}` | Party position (world or local map coordinates). |
| `location` | str/null | Town/castle name when in a building; `dungeon z=N` in a dungeon; `null` outdoors. |
| `standing_on` | str/null | Tile name under the party when outdoors (e.g. `grass`, `town`); `null` otherwise. |
| `view_ascii` | list[str] | A `(2·radius+1)`-square ASCII minimap; `@` is the party at the center. |
| `party` | list | Per-character `name, class, hp, hp_max, mp, str, dex, int, xp, level, status`. |
| `gold` | int | Party gold. |
| `food` | int | Party food (drains over time — see turn-tick upkeep). |
| `inventory` | dict | `torches, gems, keys, sextants, reagents{…8 reagents}`. |
| `items` | list | Quest items held (runes, stones, the three-part key, etc.). |
| `visible` | list | NPCs/monsters in view: `{tile, dx, dy}` offsets from the party. |
| `messages` | list[str] | Game text emitted **since the last observation** (deltas, not the whole log). |
| `interaction` | `{active, prompt}` | Whether a Talk/shop dialog owns input, and its prompt. |
| `won` | bool | True once the Avatar completes the quest. |
| `legal_actions` | list[str] | See above. |
| `error` | str/null | Set when the last action was malformed or rejected. |

#### `view_ascii` glyph legend

The minimap uses compact glyphs (from `ultima4/demo.py`). The load-bearing ones:

```
@ party (always center)   ~ water   ^ mountain   & hills   ' forest
. road/brush/floor   , scrub   % swamp   T towne   V village   C castle
O ruin/marker   = bridge   < up-stair   > down-stair   $ chest   + door   # wall
```

Letters that aren't special are the first letter of the tile name (e.g. `G` guard/grass-variant).
To make robust decisions, combine `view_ascii` (terrain shape) with `visible` (exact NPC/monster
offsets) and `standing_on` (the tile you're on, since `@` hides it in the view).

### A real example observation

Captured with `./run agent-play --seed 7 --do "move S" --do "move E" --do "key E" --json`
(the party has just walked onto the town tile south of the start and entered **Jhelom**),
trimmed for length:

```json
{
  "schema": 1,
  "mode": "building",
  "moves": 3,
  "position": { "x": 1, "y": 15 },
  "location": "Jhelom",
  "standing_on": null,
  "view_ascii": [
    "~~~R.#..G",
    "~~~..#...",
    "~~~..#GFG",
    "~~~......",
    "~~~.@....",
    "~~~......",
    "~~~..#GFG",
    "~~~..#...",
    "~~~R.#.G."
  ],
  "party": [
    { "name": "Avatar", "hp": 300, "hp_max": 300, "mp": 0,
      "str": 20, "dex": 15, "int": 11, "xp": 205, "level": 3, "status": "G" }
  ],
  "gold": 200,
  "food": 300,
  "inventory": { "torches": 2, "gems": 0, "keys": 0, "sextants": 0,
                 "reagents": { "Ginseng": 3, "Garlic": 4, "…": 0 } },
  "items": [],
  "visible": [],
  "messages": [],
  "interaction": { "active": false, "prompt": null },
  "won": false,
  "legal_actions": ["move N", "move S", "move E", "move W", "pass",
                    "key A", "key B", "...", "key T", "...", "key Z"],
  "error": null
}
```

To capture a full, untrimmed observation at any time, run `ultima4-env-info` or
`./run agent-play --json`.

---

## How an external agent connects

There are three ways to plug an agent into the game; they all sit on the same `UltimaEnv`.

### (a) In-process via `UltimaEnv` (recommended)

Import the class and drive it directly — the lowest-latency, most flexible path. See
[`examples/random_agent.py`](../examples/random_agent.py) for a complete, commented loop. The
shape is just: `observe()` → choose from `legal_actions()` → `act()` → repeat until `won`.

### (b) CLI via `./run agent-play` (stateless replay)

`./run agent-play` is a **stateless** command-line driver: it rebuilds the game from the seed and
**replays the entire `--do` action list** on each invocation, then prints the resulting
observation. This works because the env is deterministic given its seed.

The determinism trick: to play turn-by-turn across separate process invocations, keep appending
one more `--do` each call. The same seed + same action prefix always reproduces the same state,
so an agent (human or LLM) can play incrementally without keeping a process alive:

```bash
./run agent-play --seed 7 --do "move S"
./run agent-play --seed 7 --do "move S" --do "move E"
./run agent-play --seed 7 --do "move S" --do "move E" --do "key E"   # now in Jhelom
```

Add `--json` for machine-readable output, `--full` for a per-step trace.

### (c) MCP server — the zero-setup path for another agent

The Model Context Protocol server (`ultima4/agent/mcp_server.py`, stdio transport, FastMCP) lets
any MCP-capable agent play with no Python. The ideal flow — **a human points a fresh agent at this
repo and it starts playing**:

1. **Open the repo in Claude Code.** A checked-in **`.mcp.json`** at the repo root is auto-detected;
   approve the `ultima4` server when prompted. The agent also reads the repo `CLAUDE.md`, which
   tells it how to play.
2. The tools appear as `mcp__ultima4__*`. The agent plays the loop:
   `new_game(seed)` → `observe()` → pick from the returned `legal_actions` → `act("move N" | "key T"
   | "say health" | "pass")` → repeat. Tools: `new_game`, `observe`, `act`, `legal_actions`, `play`,
   `list_demos`, `run_demo`.

If the agent runs from a **different folder** (not this repo as its project), register the server at
user scope so it's visible everywhere — one command:

```
./run install-mcp           # registers 'ultima4' at user scope; restart Claude Code
```

`claude mcp list` shows it; `claude mcp remove ultima4` undoes it. The registered launch command is
the venv Python on `ultima4.agent.mcp_server` with `PYTHONPATH` set (the server uses package-relative
imports and a clean stdout — do NOT launch it via `./run mcp` for a real client, as the launcher's
dependency check prints to stdout and would corrupt the JSON-RPC stream). On a fresh machine the
absolute paths in `.mcp.json` won't match — regenerate with `./run install-mcp project`, or hand-edit
the two paths.

---

## Wiring the reference agent into `./run`

Add this case to the `run` launcher's `case "$cmd"` block (next to `agent-play`):

```bash
agent-demo) exec "$PY" examples/random_agent.py "$@" ;;
```

Then `./run agent-demo --seed 7 --max-turns 40` runs the reference agent in the project venv.

---

## Copyright / data licensing — read before redistributing

**The engine code in this repository is the project's own work** (ported from the decompiled
DOS source as an original Python implementation) and is offered under the project's license.

**The game DATA is a different matter.** Everything under `u4py/data/` and the assets converted
from it — `data/maps/*.txt`, `data/dialogue/*.json`, `assets/*.png`, and similar — **derives from
Ultima IV: Quest of the Avatar**, which is **copyrighted by Origin Systems / Electronic Arts**.

Ultima IV was made available as a *free download* historically, and that is wonderful — but
**"free to download" is NOT the same as "licensed to redistribute in a derived/converted
format."** Re-packaging the maps, dialogue, and graphics into new file formats and shipping them
is a redistribution of a derivative work, which the original "free download" permission may not
cover.

**Recommended distribution model — ship the engine only:**

1. Distribute the **engine** (this package) without the `data/` directory or converted assets.
   The `pyproject.toml` here deliberately does **not** bundle game data in the wheel.
2. Have each user **bring their own original Ultima IV data files** (the files they already have
   the right to use), and place them in `u4py/data/`.
3. Run the import tools to regenerate the editable assets **locally**:

   ```bash
   ./run maps    # WORLD.MAP / *.ULT / *.DNG -> data/maps/*.txt
   ./run gfx     # EGA/PIC graphics          -> assets/*.png
   ./run dump    # *.TLK dialogue            -> data/dialogue/*.json
   ```

This keeps copyrighted content out of your distribution while letting anyone who legitimately
owns Ultima IV play and edit the game.

> This is practical guidance, **not legal advice.** Before redistributing any game data — in any
> format — verify the licensing terms for your situation.
