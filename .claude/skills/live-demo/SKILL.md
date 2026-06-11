---
name: live-demo
description: Launch the Ultima IV port and play it through a moment of gameplay, producing a watchable transcript. Use when the user says things like "launch the game and take me through a conversation with Lord British where he heals you", "play through the first dungeon", "show me buying a weapon", "demo combat", or any "launch/play/show me the game doing X". Maps the request to a named scenario (./run demo <name>) or composes a new one with the Director, runs it, and relays the transcript.
---

# Live demo: play the game through a scenario

The game is fully drivable headlessly. A **Director** (`u4py/ultima4/demo.py`) plays a real
`Game` through the *same* input path a person uses — `game.handle(key)` for commands/movement,
`game.feed(line)` for Talk/shop dialogue — and records a transcript: narration, the actual game
messages, ASCII minimaps of the viewport, and checked outcomes. Scenarios live in
`u4py/ultima4/demo_scenarios.py` (the `SCENARIOS` registry) and run in milliseconds.

## How to handle a request

1. **List what exists:** `./run demo` (prints every scenario + tags + description).
2. **If a scenario already fits the ask, run it and relay the transcript:**
   `./run demo <name>` (human-readable) or `./run demo <name> --json` (structured).
   Example: "conversation with Lord British where he heals you" → `./run demo lord_british_heal`.
3. **If nothing fits, compose a new scenario** (see below), then run it. Prefer *adding it to
   `demo_scenarios.py`* so it's reusable and gets test coverage; for a one-off, drive a Director
   inline via `./run shell`.
4. **Relay the result to the user.** Show the transcript (or a tightened summary for long ones)
   and state whether every expectation was met. The transcript is the deliverable — it's the
   "live" the user asked for, reproducible and reviewable.

Current scenarios: `lord_british_heal`, `talk_to_townsfolk`, `buy_a_weapon`, `heal_at_the_inn`,
`mix_and_cast_heal`, `first_dungeon`, `win_a_fight`. (Run `./run demo` for the authoritative list.)

## Composing a new scenario

Write a function `fn(d: Director)` and register it in `SCENARIOS`. Director verbs:

- `d.narrate(text)` — a scene-setting line in the transcript.
- `d.enter(name_or_loc, kind=None)` — enter a town/castle by name ("britain", "lcb", …); kind
  auto-detects castle vs towne.
- `d.goto(x, y)` — place the party (narrated as walking there).
- `d.setup(fn, note)` — arbitrary game tweak (party HP/class/reagents, or call a module like
  `dungeon.enter_dungeon` / `combat.start_encounter`). `fn` receives the Director.
- `d.move(dir, n)` / `d.do(*keys, label=)` — player keystrokes (`"UP"`, `"T"`, `"A"`, …).
- `d.talk(dir, *lines)` — Talk toward `dir`, then feed conversation lines.
- `d.say(*lines)` — feed lines into the active Talk/shop interaction.
- `d.minimap(label=)` — snapshot an ASCII minimap of the viewport (`@` = party).
- `d.expect(cond, desc)` / `d.expect_message(substr, desc)` — record a checked outcome.

Ground every scenario in real game behavior — the existing flows in `tools/selftest.py` are the
canonical reference for how each subsystem (Talk, shops, mixing/casting, dungeon, combat) is
driven. Derive sequences from there or the source, not from guesses. After adding a scenario,
run `./run demo <name>` and `./run test` (the suite runs every scenario and asserts it passes).

## Watching the agent actually play (the visual)

The point for most users is to *watch a character play*, not read a transcript. The autopilot
drives the real game window — the character moves tile by tile, Talk dialogue scrolls in the
panel, blows land in combat — using the same renderer as interactive play.

- **`./run demo <name> --watch`** — opens the live game window and plays the scenario on screen,
  paced to wall-clock (`--speed 1.5` slower, `0.6` faster; `--cga` for CGA colors). Needs a
  display. If you (the agent) are headless/over SSH, DON'T block on it — tell the user to run it,
  or launch it in the **background** (it self-terminates, lingering on a "demo complete" frame).
- **`./run demo <name> --gif out.gif`** — renders the whole playthrough to an animated GIF with
  **no display needed** (fast, deterministic). This is the artifact to produce when the user
  can't watch live or wants something shareable — and how *you* verify/show the result: generate
  it, then extract a frame to PNG and Read it (Read renders PNGs). `--shots DIR` = one PNG/frame.

Recommended flow for "launch the game and have a character do X": run `--gif` to produce the
visual (the transcript prints alongside), confirm by reading a frame, and offer the user
`--watch` to see it live on their machine. **Lead with the visual, not the transcript.**

For **open-ended "just play it"** (no fixed script), drive a Director interactively — observe the
last messages, pick the next verb, repeat — under an explicit turn budget so it terminates. Never
block on an unbounded real-time wait.

Seeds are fixed (`--seed`, default 7) so demos are reproducible. One honest caveat: scenarios set
up required state directly (a wounded party, a Mage's mana) and sometimes `goto` scene-cuts the
character to a spot rather than walking every tile — the *gameplay* actions (talk, fight, cast,
shop, dungeon steps) are real and animated. Authentic tile-by-tile navigation is a future upgrade.
