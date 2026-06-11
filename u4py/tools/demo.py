"""`./run demo` — the live-demo runner. Plays the real game through a named scenario and
prints a transcript (narration + actual game messages + ASCII minimaps + checked outcomes).

    ./run demo                 list the scenarios
    ./run demo <name>          play one scenario, print its transcript
    ./run demo all             play them all, print a summary
    ./run demo <name> --json   machine-readable transcript (for the agent / tooling)
    ./run demo <name> --no-frames   hide the minimaps
    ./run demo <name> --seed N      set the RNG seed (default 7)

  Watch the agent actually play it (opens the game window, characters move/talk/fight):
    ./run demo <name> --watch         live on screen
    ./run demo <name> --gif out.gif   render the playthrough to an animated GIF (no display needed)
    ./run demo <name> --shots DIR     save every frame as PNG
    ./run demo <name> --watch --speed 1.5   slower/faster pacing; --cga for CGA colors

Exit code is nonzero if any expectation failed, so demos double as smoke tests.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ultima4 import demo_scenarios as DS


def _list() -> int:
    print("Available live demos (./run demo <name>):\n")
    for name in sorted(DS.SCENARIOS):
        s = DS.SCENARIOS[name]
        print(f"  {name:20} {s['desc']}")
        print(f"  {'':20} tags: {', '.join(s['tags'])}")
    print("\n  ./run demo all        play them all")
    print("  ./run demo <name>     play one and watch the transcript")
    return 0


def _to_json(name, d) -> dict:
    return {"scenario": name, "passed": d.passed, "failures": d.failures,
            "steps": [{"kind": s.kind, "label": s.label, "lines": s.lines, "ok": s.ok}
                      for s in d.steps]}


def _opt(argv, name, default=None):
    """Read --name VALUE or --name=VALUE from argv; returns default if absent."""
    for i, a in enumerate(argv):
        if a == name and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return default


def _make_stage(argv):
    """Build a live/capturing PygameStage if --watch/--gif/--shots is set, else None."""
    watch = "--watch" in argv
    gif = _opt(argv, "--gif")
    shots = _opt(argv, "--shots")
    if not (watch or gif or shots):
        return None, None, None
    import os
    if not watch:                       # capture-only: no display needed
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    from ultima4.stage import PygameStage
    stage = PygameStage(which="cga" if "--cga" in argv else "ega",
                        speed=float(_opt(argv, "--speed", "1.0")),
                        realtime=watch,             # live window paces to wall-clock; capture is fast
                        capture=bool(gif or shots))
    return stage, gif, shots


def main(argv) -> int:
    # value-bearing options consume their next token, so strip those before reading positionals
    _VALUE_OPTS = {"--gif", "--shots", "--speed", "--seed"}
    args, skip = [], False
    for i, a in enumerate(argv):
        if skip:
            skip = False
            continue
        if a in _VALUE_OPTS:
            skip = True
            continue
        if a.startswith("--"):
            continue
        args.append(a)
    as_json = "--json" in argv
    show_frames = "--no-frames" not in argv
    seed = int(_opt(argv, "--seed", "7"))

    target = args[0] if args else "list"

    if target in ("list", "ls", "help"):
        return _list()

    if target == "all":
        results = DS.run_all(seed=seed)
        if as_json:
            print(json.dumps({n: _to_json(n, d) for n, d in results.items()}, indent=2))
        else:
            print("Live-demo suite:\n")
            for n, d in results.items():
                mark = "PASS" if d.passed else f"FAIL {d.failures}"
                print(f"  [{mark:>4}] {n}")
        ok = all(d.passed for d in results.values())
        print("" if as_json else f"\n{sum(d.passed for d in results.values())}/{len(results)} demos passed")
        return 0 if ok else 1

    if target not in DS.SCENARIOS:
        print(f"unknown scenario {target!r}\n", file=sys.stderr)
        _list()
        return 2

    stage, gif, shots = _make_stage(argv)
    try:
        d = DS.run(target, seed=seed, stage=stage)
    finally:
        if stage is not None:
            if gif:
                p = stage.save_gif(gif)
                print(f"[demo] saved GIF -> {p} ({len(stage.frames)} frames)" if p
                      else "[demo] no frames captured")
            if shots:
                n = stage.save_shots(shots)
                print(f"[demo] saved {n} PNG frames -> {shots}")
            stage.close()
    if as_json:
        print(json.dumps(_to_json(target, d), indent=2))
    else:
        print(f"\n=== live demo: {target} ===")
        print(f"    {DS.SCENARIOS[target]['desc']}")
        print(d.transcript(show_frames=show_frames))
    return 0 if d.passed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
