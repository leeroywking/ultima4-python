"""`./run agent-play` — drive the game as an agent through UltimaEnv, from the command line.

Because the env is deterministic (seeded), this driver is STATELESS: it rebuilds the game from
the seed and replays the whole action list each call, so an agent (human or LLM) can play
turn-by-turn across separate invocations just by appending one more --do each time.

    ./run agent-play                                  # the opening observation (seed 7)
    ./run agent-play --do "move N" --do "key E"       # replay these, show the result
    ./run agent-play --seed 3 --do "key T" --do "move N" --full   # full per-step trace
    ./run agent-play ... --json                        # raw JSON observation (for tooling)

`--do` takes an action string: 'move N|S|E|W', 'key <LETTER>', 'say <text>', 'pass'.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ultima4.env import UltimaEnv


def _fmt(obs: dict) -> str:
    out = []
    head = f"[{obs['mode']}] moves={obs['moves']} pos=({obs['position']['x']},{obs['position']['y']})"
    if obs.get("location"):
        head += f" @ {obs['location']}"
    if obs.get("standing_on"):
        head += f" on {obs['standing_on']}"
    out.append(head)
    out.append(f"gold={obs['gold']} food={obs['food']}  party=" + ", ".join(
        f"{m['name'] or '-'} {m['hp']}/{m['hp_max']}hp {m['mp']}mp [{m['status']}]"
        for m in obs["party"]) or "")
    out.append("view:")
    out.extend("   " + r for r in obs["view_ascii"])
    if obs["visible"]:
        out.append("visible: " + ", ".join(f"{v['tile']}@({v['dx']:+d},{v['dy']:+d})"
                                            for v in obs["visible"]))
    if obs["interaction"]["active"]:
        out.append(f"interaction: {obs['interaction']['prompt']}")
    if obs["messages"]:
        out.append("messages:")
        out.extend("   " + m for m in obs["messages"])
    if obs.get("error"):
        out.append(f"!! {obs['error']}")
    out.append("legal: " + " | ".join(obs["legal_actions"]))
    return "\n".join(out)


def main(argv) -> int:
    seed = 7
    actions, i, as_json, full = [], 0, False, False
    while i < len(argv):
        a = argv[i]
        if a == "--seed":
            seed = int(argv[i + 1]); i += 2
        elif a == "--do":
            actions.append(argv[i + 1]); i += 2
        elif a == "--json":
            as_json = True; i += 1
        elif a == "--full":
            full = True; i += 1
        else:
            i += 1

    env = UltimaEnv(seed=seed)
    obs0 = env.observe()
    trace = env.play(actions)
    final = trace[-1] if trace else obs0

    if as_json:
        print(json.dumps(trace if full else final, indent=2))
        return 0
    if full:
        print("=== opening ===")
        print(_fmt(obs0))
        for act, obs in zip(actions, trace):
            print(f"\n=== after: {act} ===")
            print(_fmt(obs))
    else:
        print(_fmt(final))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
