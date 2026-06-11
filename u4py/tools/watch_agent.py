"""`./run watch` — watch an AGENT play Ultima IV LIVE in a continuously-animating window.

Unlike `./run demo` (which renders synchronously, one scripted beat at a time), this opens a
free-running window at the DOS animation rate and lets an agent push moves onto a queue from a
background thread, so a human watches the character act in real time.

    ./run watch                         # a wandering agent roams the overworld
    ./run watch --scenario buy_a_weapon # replay a known demo scenario's moves, live
    ./run watch --which cga --speed 2 --seed 3 --max-turns 80

Flags:
    --scenario NAME   replay a demo scenario's input verbs live (see `./run demo` for names)
    --which ega|cga   palette (default ega)
    --speed FLOAT     >1 slower (longer hold per move), <1 faster; scales action_every
    --seed INT        RNG seed (default 7)
    --max-turns INT   budget for the wander policy (default 200)
    --ticks INT       stop after N render ticks (headless/test bound; default unbounded)

Headless self-check (no display):
    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy ./run watch --selftest
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ultima4.env import UltimaEnv
from ultima4.live_window import LiveWindow, wander_policy


# --- scenario replay ---------------------------------------------------------
def _scenario_actions(name: str, seed: int):
    """Capture a scenario as (prepared_game, input_actions).

    A scenario interleaves *setup* verbs (enter/goto/setup — direct scene-building) and *input*
    verbs (do/move/say/talk — the real player path). For a live, decoupled replay we want the
    game already in the scene (setup applied) and only the input verbs streamed through the
    queue. So we do two passes over the same scenario function:

      pass 1 (`_prepare_game`): run ONLY the setup verbs → a game sitting at the scene start.
      pass 2 (here): run the scenario on a throwaway Director with input verbs wrapped to record
                     each real Game.handle/feed call as an env action string, setup verbs no-op'd.
    """
    from ultima4 import demo_scenarios
    from ultima4.demo import Director

    recorded: list[str] = []
    d = Director(seed=seed)
    real_handle, real_feed = d.game.handle, d.game.feed

    def rec_handle(key, *a, **k):
        if key in ("UP", "DOWN", "LEFT", "RIGHT"):
            recorded.append({"UP": "move N", "DOWN": "move S",
                             "RIGHT": "move E", "LEFT": "move W"}[key])
        elif len(str(key)) == 1:
            recorded.append(f"key {key}")
        return real_handle(key, *a, **k)

    def rec_feed(text, *a, **k):
        recorded.append(f"say {text}")
        return real_feed(text, *a, **k)

    d.game.handle = rec_handle
    d.game.feed = rec_feed
    # Neutralise setup + narration verbs so only the player-input verbs (which call handle/feed)
    # contribute recorded actions; the scene state of this throwaway game is irrelevant.
    for verb in ("enter", "goto", "setup", "narrate", "expect",
                 "expect_message", "minimap"):
        setattr(d, verb, (lambda *a, **k: d).__get__(d, Director))

    demo_scenarios.SCENARIOS[name]["fn"](d)

    prepared = _prepare_game(name, seed)
    return prepared, recorded


def _prepare_game(name: str, seed: int):
    """Re-run the scenario applying ONLY its setup verbs (enter/goto/setup), so we get a game in
    the scene's starting position, ready for the captured inputs to be fed live."""
    from ultima4 import demo_scenarios
    from ultima4.demo import Director

    d = Director(seed=seed)
    # Neutralise the input verbs so only setup mutates the game.
    for verb in ("do", "say", "move", "talk", "narrate", "expect",
                 "expect_message", "minimap"):
        setattr(d, verb, (lambda *a, **k: d).__get__(d, Director))
    fn = demo_scenarios.SCENARIOS[name]["fn"]
    fn(d)
    return d.game


def run_scenario_live(name: str, which: str, action_every: int, seed: int,
                      max_ticks=None) -> int:
    from ultima4 import demo_scenarios
    if name not in demo_scenarios.SCENARIOS:
        known = ", ".join(sorted(demo_scenarios.SCENARIOS))
        raise SystemExit(f"unknown scenario {name!r}; known: {known}")
    prepared, actions = _scenario_actions(name, seed)
    env = UltimaEnv(seed=seed, game=prepared)
    win = LiveWindow(env, which=which, action_every=action_every)
    try:
        return win.play_actions(actions, max_ticks=max_ticks)
    finally:
        win.close()


def run_wander_live(which: str, action_every: int, seed: int, max_turns: int,
                    max_ticks=None) -> int:
    env = UltimaEnv(seed=seed)
    win = LiveWindow(env, which=which, action_every=action_every)
    try:
        return win.run_with_agent(wander_policy(seed), max_turns=max_turns,
                                  max_ticks=max_ticks)
    finally:
        win.close()


# --- headless self-check -----------------------------------------------------
def selftest() -> int:
    """Bounded headless run proving the loop applies actions and exits clean. Returns applied."""
    import os
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    env = UltimaEnv(seed=7)
    win = LiveWindow(env, which="ega", action_every=3)
    actions = ["move N", "move E", "move S", "move W", "pass"] * 4   # 20 actions
    applied = win.play_actions(actions, max_ticks=200)
    win.close()
    assert applied > 0, "no actions applied"
    print(f"[watch selftest] applied {applied} actions, exited clean")
    return applied


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="watch", description="Watch an agent play Ultima IV live.")
    ap.add_argument("--scenario", help="replay a demo scenario's inputs live")
    ap.add_argument("--which", choices=("ega", "cga"), default="ega")
    ap.add_argument("--speed", type=float, default=1.0,
                    help=">1 slower, <1 faster (scales ticks-per-action)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--max-turns", type=int, default=200)
    ap.add_argument("--ticks", type=int, default=None,
                    help="stop after N render ticks (test/headless bound)")
    ap.add_argument("--selftest", action="store_true", help="run the bounded headless self-check")
    args = ap.parse_args(argv)

    if args.selftest:
        selftest()
        return

    action_every = max(1, round(8 * args.speed))    # 8 ticks/action @1.0 ≈ 0.44 s
    if args.scenario:
        run_scenario_live(args.scenario, args.which, action_every, args.seed, args.ticks)
    else:
        run_wander_live(args.which, action_every, args.seed, args.max_turns, args.ticks)


if __name__ == "__main__":
    main()
