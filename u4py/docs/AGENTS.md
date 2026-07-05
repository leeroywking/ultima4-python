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
| `attack <dir>` / `talk <dir>` / `open <dir>` / `key A E` | **One-shot directional** command (key + direction in a single call). Bare `attack` (in combat) hits the nearest in-range foe. |
| `say <text>` | Free text into an **active** Talk/shop interaction (e.g. `say health`, `say bye`). |
| `pass` | Consume one turn (SPACE). |
| `wait <seconds>` | Let real game-time pass on the **moon clock** without moving (e.g. `wait 20`). See "Time & the moons". |
| `wait until <cond>` | Advance the moon clock until a condition holds: `moongate`, `moons_dark`, `trammel N`, `felucca N`. |
| `go <x> <y>` (or `travel <x> <y>`) | **Walk a whole path in one call** to tile (x, y); stops on arrival or the first interesting event. See "Moving efficiently". |

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
| `moons` | dict | `{trammel, felucca, gate}` — the two moon phases (0–7) and, when a gate is open, `gate:{x, y, destination:{x,y}\|"abyss", adjacent}`. See "Time & the moons". |
| `combat` | dict/absent | Only in combat, and the **single authoritative frame**: `active:{member, pos, reach, can_attack:[dirs], nearest:{dir, step, dist, in_range, tile}}` + `monsters:[{tile, pos, dx, dy, dist, direction, in_range}]`, all from the active member. If `can_attack` is non-empty, `attack` (nearest) / `attack <dir>`; else `move` `active.nearest.step`. (In combat, `visible` is empty and — in `min` — `view_ascii`/`moons` are dropped.) |
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

### Moving efficiently — don't spend a round-trip per step

Crossing open terrain one `move` at a time is slow (a full observe round-trip per tile). Prefer the
batch primitives:

- **`go <x> <y>`** / tool `travel_to(x, y)` — pathfinds to (x, y) (BFS, honouring your transport:
  foot/horse/ship/balloon) and walks the **whole path in one call**, taking real turns. It **stops
  early** the moment anything interesting happens and returns the observation with `travel_reason`
  (`arrived`, `interrupted: now combat`, `interaction opened`, `took damage`, `blocked`, `no_path`,
  `max_steps`) and `steps_taken`. So you never miss a fight or a conversation — you just skip the
  boring straight-line walking. If the target tile isn't walkable it stops adjacent. Overworld and
  towns only (dungeons use their own advance/turn movement).
- Use single `move N/S/E/W` for fine positioning (lining up on a door, a gate tile, an NPC).

### Time & the moons (moongates)

The two moons, **Trammel** and **Felucca**, cycle through 8 phases on a **real-time clock** (the
DOS int-`0x1C` timer, ~18.2 Hz) — **independent of your moves**, exactly as in the original. Moving
never advances them; time does. This drives two mechanics:

- **Moongates.** An open gate sits at the Trammel-phase location (one of 8 fixed spots); stepping
  onto it teleports you to the Felucca-phase location (or toward the Abyss when both moons are full).
  `observe()["moons"]["gate"]` gives the open gate's `{x, y, destination, adjacent}`.
- **Mandrake & nightshade.** The two rarest reagents can only be gathered by `key S` (Search) at
  their spots when **both moons are new** (`moons_dark`).

Because you play turn-by-turn, use the **time primitives** to let the real-time clock advance
without moving:

- `wait <seconds>` (tool `wait(seconds)`) — let N seconds of game-time pass; the moons advance at
  the authentic rate (~20 s per Trammel phase). Deterministic and replayable.
- `wait until <cond>` (tool `wait_until(condition)`) — advance until `moongate` (an open gate is
  on/adjacent to you), `moons_dark`, `trammel N`, or `felucca N`; returns `wait_reason` +
  `waited_seconds`. Typical moongate trip: walk to a gate spot → `wait until trammel <that spot>`
  (or `wait until moongate`) → step onto the gate.

In a **windowed** session the moons also advance with real wall-time as you watch; headless advances
the identical clock lazily on each observe/act plus your explicit `wait`s — same mechanic either way.

<!-- BEGIN generated reference tables (regenerate: ./run reference) -->

## Agent reference tables (generated — cite these, do not re-derive)

_Generated by `./run reference` from `data_tables.py`; don't hand-edit._

### Moongate schedule

The open gate's **location** follows the current **Trammel** phase; stepping through it teleports you to the current **Felucca** phase's location (same `MOONGATE_X/Y` table). Felucca cycles ~3x faster, and the two are phase-locked, so **from a fresh game each gate location only reaches a fixed 3-destination window**:

| Trammel phase | gate location (x,y) | reachable destinations `felucca:(x,y)` |
|:-:|:-:|:--|
| 0 | (224,133) | 0:(224,133), 1:(96,102), 2:(38,224) |
| 1 | (96,102) | 3:(50,37), 4:(166,19), 5:(104,194) |
| 2 | (38,224) | 0:(224,133), 6:(23,126), 7:(187,167) |
| 3 | (50,37) | 1:(96,102), 2:(38,224), 3:(50,37) |
| 4 | (166,19) | 4:(166,19), 5:(104,194), 6:(23,126) |
| 5 | (104,194) | 0:(224,133), 1:(96,102), 7:(187,167) |
| 6 | (23,126) | 2:(38,224), 3:(50,37), 4:(166,19) |
| 7 | (187,167) | 5:(104,194), 6:(23,126), 7:(187,167) |

To use one: `travel_to` a gate location → `wait until moongate` (gate becomes adjacent) → `wait 1` until `observe()['moons']['gate']['destination']` is the one you want → step onto the gate. `observe()['moons']` always carries the live phases + open gate.

### Companions, home towns, and the join rule

Class index = virtue = home town. **Lord British's Castle (level-ups + healing): (86,107).**

| class | companion | home town | town (x,y) |
|:--|:--|:--|:-:|
| 0 Mage | Mariah | Moonglow | (232,135) |
| 1 Bard | Iolo | Britain | (82,106) |
| 2 Fighter | Geoffrey | Jhelom | (36,222) |
| 3 Druid | Jaana | Yew | (58,43) |
| 4 Tinker | Julia | Minoc | (159,20) |
| 5 Paladin | Dupre | Trinsic | (106,184) |
| 6 Ranger | Shamino | Skara Brae | (22,128) |
| 7 Shepherd | Katrina | Magincia | (187,169) |

**Join rule** (C: `U4_TALK.C`; `dialogue.py _join`): a companion joins only if **their class ≠ the Avatar's own class** (a Fighter Avatar can never recruit Geoffrey the Fighter), **and** that virtue's karma ≥ 40 (or exactly 0), **and** `100·(party size) + 100 ≤ Avatar hp_max` — so level up at Lord British (he raises hp_max) to unlock party slots.

<!-- END generated reference tables -->

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
   `travel_to`, `wait`, `wait_until`, `viewer_status`, `list_demos`, `run_demo`.

If the agent runs from a **different folder** (not this repo as its project), register the server at
user scope so it's visible everywhere — one command:

```
./run install-mcp           # registers 'ultima4' at user scope; restart Claude Code
```

`claude mcp list` shows it; `claude mcp remove ultima4` undoes it. The checked-in `.mcp.json` is
**portable** — it uses `${CLAUDE_PROJECT_DIR:-.}`, so a clone works without editing paths. Both the
committed `.mcp.json` command and `./run mcp` keep **stdout clean** for the JSON-RPC stream (bootstrap
chatter and the pygame banner go to stderr / are suppressed), so either is safe to launch.

**Visible vs headless — where the human watches.** The shipped `.mcp.json` launches the server with
`--window`, so **a visible game window opens by default whenever the machine has a display** (and
silently falls back to headless when it doesn't). The human then watches both inline (each
`observe`/`act` is a tool result) and on screen. To launch a windowed server by hand:

```
./run mcp --window          # MCP server + a live window; the agent's moves render on screen
```

The window runs a `LiveWindow` and every `act`/`new_game`/`play` is applied on its render thread, so
what the agent does and what the screen shows are the *same* game. With no display it logs to stderr
and falls back to headless — and the `viewer_status` tool reports whether a window is attached (so a
headless session can tell the human why there's no window: switching it on needs a `--window`
relaunch + a Claude Code restart, not a mid-session toggle). (Contrast `./run watch`, which shows a
window but can only be driven by a
built-in wander policy or a pre-recorded demo — not an external agent.)

---

## Wiring the reference agent into `./run`

Add this case to the `run` launcher's `case "$cmd"` block (next to `agent-play`):

```bash
agent-demo) exec "$PY" examples/random_agent.py "$@" ;;
```

Then `./run agent-demo --seed 7 --max-turns 40` runs the reference agent in the project venv.

---

## Attribution

**The engine code in this repository is the project's own work** — an original Python
implementation ported from the decompiled DOS source — and is offered under the project's license.

The game content (`data/maps/*.txt`, `data/dialogue/*.json`, `data/intro/*.json`,
`data/party_start.json`, `assets/*.png`) derives from **Ultima IV: Quest of the Avatar**, created
by Lord British (Richard Garriott) and Origin Systems, which Origin/EA released as **freeware**.
This project is a free, non-commercial fan port and toy — a small world for people (and their
agents) to explore and edit — with no affiliation to or endorsement by Origin Systems or Electronic
Arts. All Ultima IV trademarks and copyrights remain with their owners.

If you are a rights holder and would like something changed, please open an issue.
