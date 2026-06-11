#!/usr/bin/env python3
"""Reference agent for the Ultima IV port — living documentation of the observe/act loop.

This is the canonical example a *downstream* AI agent (or its author) should read to learn how
to drive the game. It is deliberately small and heavily commented; the policy is a *biased*
random walk, not a smart player — just enough logic to show how to read an observation and turn
it into a legal action.

What it demonstrates, end to end:
  1. Construct the environment:           env = UltimaEnv(seed=...)
  2. Perceive:                            obs = env.observe()      (plain JSON, no engine objects)
  3. Decide from `obs["legal_actions"]`:  read `view_ascii` / `visible` to pick a move
  4. Act:                                 obs = env.act("move N")  (returns the next observation)
  5. Stop on `obs["won"]` or a turn budget, then print a summary.

The policy: scan the ASCII viewport for a town/castle/village glyph; if one is adjacent, step
onto it and press **E** (Enter); if it's in view but not adjacent, walk toward it; otherwise
wander, preferring open ground over water/mountains. When a Talk/shop interaction is active
(`obs["interaction"]["active"]`), say a friendly keyword and then "bye".

Run it:
    u4py/.venv/bin/python examples/random_agent.py --seed 7 --max-turns 40
    ./run agent-demo --seed 7 --max-turns 40      # once the run subcommand is wired (see docs)

The env is deterministic given the seed, so the same flags reproduce the same session.
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

# Make the `ultima4` package importable when run as a loose script (mirrors tools/agent_play.py).
# After `pip install ultima4-py` this line is unnecessary, but it keeps the example runnable
# straight from a checkout without installing anything.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ultima4.env import UltimaEnv  # noqa: E402  (import after sys.path tweak, on purpose)

# Minimap glyphs (from ultima4/demo.py `_MINI`) that mean "a place you can Enter".
# O=ruin/shrine-ish marker, T=towne, C=castle, V=village. The '@' glyph is always the party,
# fixed at the center of the viewport.
ENTERABLE = set("OTCV")

# View geometry: render_ascii(radius=4) returns a (2*radius+1) square with '@' at the center.
RADIUS = 4
CENTER = RADIUS  # row/col index of the party in view_ascii

# Map a compass direction to the (dcol, drow) it moves the *party* in the viewport. North is up
# (decreasing row); the action grammar uses N/S/E/W.
DIRS = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)}

# Terrain glyphs that are cheap/safe to walk on, so the wander policy biases toward them.
# (',' scrub, '.' floor/road/brush, "'" forest-edge, '%' swamp-ish — all generally passable.)
OPEN_GLYPHS = set(",.'%")


def find_enterable(view):
    """Return (col, row) of the nearest enterable glyph in the viewport, or None.

    `view` is obs["view_ascii"]: a list of equal-length strings. We scan every cell, skip the
    party's own center, and keep the one closest (Chebyshev distance) to the center.
    """
    best = None
    best_dist = 99
    for row, line in enumerate(view):
        for col, ch in enumerate(line):
            if ch in ENTERABLE and not (col == CENTER and row == CENTER):
                dist = max(abs(col - CENTER), abs(row - CENTER))
                if dist < best_dist:
                    best, best_dist = (col, row), dist
    return best


def step_toward(col, row):
    """Pick the compass move that reduces distance to viewport cell (col, row).

    Greedy: close the larger axis gap first. Returns a direction letter N/S/E/W.
    """
    dcol, drow = col - CENTER, row - CENTER
    if abs(dcol) >= abs(drow) and dcol != 0:
        return "E" if dcol > 0 else "W"
    return "S" if drow > 0 else "N"


def choose_action(obs, rng):
    """The policy: map one observation to one action string from obs["legal_actions"].

    This is the only "brains" in the example. A real agent would replace this with an LLM call
    or a planner, but the shape is the same: look at the observation, return a legal action.
    """
    legal = obs["legal_actions"]

    # 1) If a conversation/shop is active, be polite: greet, then leave so we don't get stuck.
    if obs["interaction"]["active"]:
        # `say <keyword>` options are listed in legal_actions; "bye" ends most conversations.
        return "say bye"

    # 2) In combat, attack: `key A` then a direction (the engine prompts "Attack - dir?").
    #    A real agent would target the nearest monster from `obs["visible"]`; we keep it simple
    #    and just swing in the direction of the first visible foe (or north as a fallback).
    if obs["mode"] == "combat":
        if "key A" in legal:
            return "key A"
        foes = obs.get("visible") or []
        if foes:
            f = foes[0]
            if abs(f["dx"]) >= abs(f["dy"]) and f["dx"] != 0:
                return "move " + ("E" if f["dx"] > 0 else "W")
            return "move " + ("S" if f["dy"] > 0 else "N")
        return rng.choice([a for a in legal if a.startswith("move")] or ["pass"])

    # 3) If we are already STANDING ON an enterable tile, Enter it now. (Once the party steps
    #    onto a town the '@' glyph hides the tile in view_ascii, so we must read `standing_on`.)
    if obs.get("standing_on") in ("town", "village", "castle", "ruins") and "key E" in legal:
        return "key E"

    # 4) If the engine is asking "which direction?" (pending_dir), legal is just the 4 moves.
    #    Pick one toward an enterable place if we can see one, else north.
    movement_only = set(legal) <= {"move N", "move S", "move E", "move W"}
    target = find_enterable(obs["view_ascii"])
    if movement_only:
        if target:
            return "move " + step_toward(*target)
        return "move N"

    # 5) An enterable place is in view but we're not on it yet: walk toward it. Stepping onto
    #    the tile sets up the `standing_on` Enter handled by branch (3) next turn.
    if target:
        return "move " + step_toward(*target)

    # 6) Nothing interesting in view: wander, preferring open ground over water/mountains.
    #    Read the four neighbor glyphs straight out of the ASCII view.
    view = obs["view_ascii"]
    good, ok = [], []
    for d, (dcol, drow) in DIRS.items():
        c, r = CENTER + dcol, CENTER + drow
        if 0 <= r < len(view) and 0 <= c < len(view[r]):
            ch = view[r][c]
            if ch in OPEN_GLYPHS:
                good.append("move " + d)
            elif ch not in "~^&O":   # avoid deep water '~', mountains '^', hills '&'
                ok.append("move " + d)
    pool = good or ok or ["move N", "move S", "move E", "move W"]
    return rng.choice(pool)


def print_env_info(argv=None):
    """Console-script body for `ultima4-env-info`: a runnable cheat-sheet for the env contract.

    Prints the observe/act loop, the action grammar, and a live opening observation so a new
    agent author can see the JSON shape without reading any source. Zero-arg callable.
    """
    import json

    print(__doc__.strip())
    print("\n--- action grammar -----------------------------------------------------------")
    print('  "move N" | "move S" | "move E" | "move W"   (compass movement)')
    print('  "key <LETTER>"   one of A,B,C,D,E,F,G,H,I,J,K,L,M,O,P,Q,R,S,T,U,W,X,Z')
    print('  "say <text>"     free text into an active Talk/shop interaction')
    print('  "pass"           wait one turn')
    print("\n--- a live opening observation (seed 7) --------------------------------------")
    obs = UltimaEnv(seed=7).observe()
    print(json.dumps(obs, indent=2))
    print("\n  obs['legal_actions'] always lists exactly what is valid in the current state.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Reference random-walk agent for the Ultima IV env.")
    ap.add_argument("--seed", type=int, default=7, help="world seed (deterministic).")
    ap.add_argument("--max-turns", type=int, default=40, help="turn budget before stopping.")
    ap.add_argument("--quiet", action="store_true", help="suppress the per-turn trace.")
    args = ap.parse_args(argv)

    rng = random.Random(args.seed)        # the *policy's* RNG, separate from the world seed
    env = UltimaEnv(seed=args.seed)
    obs = env.observe()                   # the opening observation (turn 0)

    entered_locations = []                # towns/castles we managed to enter
    start_loc = obs.get("location")

    for turn in range(1, args.max_turns + 1):
        action = choose_action(obs, rng)
        obs = env.act(action)             # <-- the core call: one action in, next obs out

        # Track whether we crossed into a building (mode flips to "building").
        loc = obs.get("location")
        if loc and loc not in entered_locations:
            entered_locations.append(loc)

        if not args.quiet:
            # A compact one-line trace: turn, action, resulting mode/pos, and any new messages.
            msgs = "; ".join(obs["messages"]) if obs["messages"] else ""
            line = (f"t{turn:>3} {action:<10} -> [{obs['mode']}] "
                    f"pos=({obs['position']['x']},{obs['position']['y']})")
            if obs.get("location"):
                line += f" @ {obs['location']}"
            if msgs:
                line += f"  | {msgs}"
            if obs.get("error"):
                line += f"  !! {obs['error']}"
            print(line)

        if obs["won"]:
            print(f"\n*** The game was WON on turn {turn}! ***")
            break

    # --- summary -------------------------------------------------------------
    print("\n=== summary ===")
    print(f"seed            : {args.seed}")
    print(f"turns played    : {turn}")
    print(f"start location  : {start_loc or 'wilderness'}")
    print(f"final mode      : {obs['mode']}")
    print(f"final position  : ({obs['position']['x']},{obs['position']['y']})"
          + (f" @ {obs['location']}" if obs.get("location") else ""))
    print(f"gold / food     : {obs['gold']} / {obs['food']}")
    print(f"entered town?   : {'yes -> ' + ', '.join(entered_locations) if entered_locations else 'no'}")
    print(f"won             : {obs['won']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
