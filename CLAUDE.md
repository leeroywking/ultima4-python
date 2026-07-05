# Ultima IV → Python rewrite — working rules

This repo is a **faithful port** of Ultima IV from the decompiled DOS source. The Python game
is in `u4py/`; the original is in `u4/` (`SRC/*.C`, `*.H`, `*.ASM`), with a portable-C
reference in `forVS/`. Game data files are in `u4py/data/`.

## Rule #1 — reference the original FIRST (non-negotiable)

When (re)building any behavior from the original game, **derive it from the original source,
not from modern convention, a round number, or memory (yours or the user's).**

Before writing code for a ported feature:
1. Locate it in `u4/SRC/*.C` / `*.H` / `*.ASM` (or `forVS/`, or the data files) and **cite the
   function/constant in a comment** (e.g. `# C: U4_ANIM.C C_3A80`).
2. Take positions, sizes, **timings/rates**, colors, tables, formulas, and text **from the
   source**. A modern/round value (e.g. `60` fps, "top-right corner") is a smell that you're
   guessing — go find the real value.
3. If the source genuinely doesn't pin a value down, **say so** and state the smallest
   defensible inference; don't silently invent.
4. Deviate only deliberately, and record the deviation as a known simplification in
   `u4py/ROADMAP.md`.

Examples of getting this wrong (don't repeat): the animation tick is the DOS **int 0x1C timer
= 18.2 Hz** (`LOW.ASM`), not 60 fps; the moon-phase HUD is **top-center, text col 11–12 row 0**
(`U4_ANIM.C C_3A80`), drawn as charset glyphs `0x14+((phase-1)&7)`, not a hand-picked corner.

## Other standing rules
- Faithful port first (verify against original), then refactor toward legible, data-driven code.
- Every feature ships with a headless check in `tools/selftest.py`; keep `./run test` green.
- `u4py/ROADMAP.md` is the live plan; the project memory holds context across sessions.

## Playing the game as an agent (if the human asks you to play / demo it)

This game is built to be **played by you, with the human watching**. The entire point is that the
person sees the world and your moves **turn by turn**. So the rule is:

> **Play in the mode the human can watch. NEVER silently drop into a headless run that shows them
> nothing.** If the watchable mode isn't ready yet, set it up and hand off for a restart — do not
> "play" headlessly as a substitute.

### Preferred — MCP tools (the human watches each turn inline)
This repo ships a portable `.mcp.json`, so opening the repo in Claude Code offers an `ultima4` MCP
server (tools `mcp__ultima4__*`). Every `observe()` / `act()` renders **in the conversation**, so
the human follows every turn. Loop: `new_game(seed)` → `observe()` → pick from `legal_actions` →
`act(...)` → repeat, reading `view_ascii` / `visible` / `standing_on` / `messages` to decide.
**Prefer the batch tools over spamming single steps:** `travel_to(x,y)` walks a whole path in one
call and stops on anything interesting (combat, dialog, arrival); `wait(seconds)` / `wait_until(...)`
advance the real-time moons (for a moongate) instead of repeating `pass`. `observe()["moons"]` shows
the phases + open gate for planning.

The shipped `.mcp.json` launches the server with `--window`, so **a real game window also opens
automatically whenever the machine has a display** (it silently stays headless if not) — the human
then watches both inline and on screen. If the human asks to *see* a window, or wonders why there
isn't one, call **`viewer_status()`**: if it reports `headless`, relay its note (getting a window
needs a `--window` relaunch + a Claude Code restart; it can't be toggled mid-session).

**If the `mcp__ultima4__*` tools are NOT available yet** (fresh clone / not approved / not
restarted) — this is the common first-run case — **set them up, then STOP and hand off. Do not
headless-play instead:**
1. Build + confirm once (also creates the venv the server runs on): `./run test` (all checks green).
2. Say to the human, roughly:
   > "The game's ready. Please **restart Claude Code** (or reload this window) and **approve the
   > `ultima4` server** when prompted — then tell me to go and I'll play it so you can watch each
   > turn." *(If no approval prompt appears, run `./run install-mcp` and restart.)*
3. **Wait for them.** After the restart the tools appear; then play via MCP.

### Human watches a live game window (needs a display)
- **MCP with a window is the default** — the shipped `.mcp.json` launches `--window`, so playing
  over MCP already opens a visible window mirroring YOUR play (every `act()`/`new_game()` renders on
  screen) whenever a display exists. Nothing extra to do; `viewer_status()` tells you if it's on.
- **`./run mcp --window`** is the same thing launched by hand (for a standalone/kiosk session).
- `./run watch` plays live in the window but is driven by a built-in wander policy or a pre-recorded
  demo (`--scenario NAME`), not by you; `./run demo` lists scripted set-piece playthroughs.

The window needs a display (a local machine, not plain SSH / headless); without one it falls back
to headless automatically.

### Headless CLI — for YOUR own testing, not a user-facing playthrough
`./run agent-play --do "move N" --do "key T" ...` replays the action list statelessly and prints the
observation + `legal_actions`; `./run agent-demo` runs the reference policy. Use these to reason,
script, or self-test — **not** as the way you play *for a human who wanted to watch* (they see almost
nothing). Only play a real session this way if the human explicitly asks for an unattended/automated run.

### Play efficiently — DON'T deliberate on forced moves (this is the speed lever)
Most turns have no real choice; treating each like a puzzle is what makes play crawl. So:

- **Act instantly on the obvious. No reasoning, no narration on a forced move** — just emit the
  action. Spend thought ONLY at real branches: an enemy in range, low HP, a fork in the route, a
  dialog/menu, something unexpected in `messages`. A whole traversal or a chase across the arena is
  *one decision* ("head to X" / "close on the enemy"), then a run of reflex moves.
- **Combat is almost always mechanical** — read one field and go:
  - `observe()['combat']['active']['can_attack']` non-empty? → `act("attack")` (hits the nearest
    in-range foe; or `attack <dir>`). Don't recompute geometry.
  - Otherwise → step toward the foe: `act("move " + combat.active.nearest.step)`.
  - Only stop to actually *think* if HP is low (flee/heal), a spell clearly wins it, or the setup is
    unusual. Everything in `combat` is from the active member's frame — trust it, ignore `view_ascii`.
- **One-shot directional commands:** `act("attack E")`, `act("talk N")`, `act("open W")` — one call,
  not `key A` then `move E`.
- **Read the delta, not the dump.** `set_verbosity('min')` once at the start; then each turn only
  `position` / `mode` / `messages` / `combat` / `travel_reason` matter — the rest is omitted while
  unchanged (and `view_ascii`/`moons` are dropped entirely during combat).
- **Decide once; cite, don't recompute.** Route / moon timing / recruit order: work out once, jot it
  down. The moongate schedule + companion/town/**join rule** are precomputed in
  `u4py/docs/AGENTS.md` ("Agent reference tables") — cite them (e.g. a companion whose class == the
  Avatar's own class can never join). **Narrate one line per beat, not per tile.**

**Action grammar** (same everywhere): `"move N|S|E|W"`, `"key <LETTER>"` (T=Talk, E=Enter, C=Cast,
Z=Ztats, K=Klimb, D=Descend, X=eXit…), `"say <text>"` (into an active Talk/shop), `"pass"`, and the
time primitives `"wait <seconds>"` / `"wait until moongate|moons_dark|trammel N|felucca N"` (the moons
run on a real-time clock independent of moves; `wait` lets it advance — e.g. to catch a moongate), and
`"go <x> <y>"` (travel a whole path in one call, stopping on combat/dialog/arrival). The
full observe/act contract is in `u4py/docs/AGENTS.md`. Goal of a playthrough is up to the human;
the win condition is the Abyss/Codex (`observation["won"]`).
