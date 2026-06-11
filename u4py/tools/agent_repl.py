"""Interactive console for the editor + tutor agents — `./run agent`.

A text REPL (no pygame) for poking at the agent layer against a live game. Edit the game
with natural language, ask the tutor for guidance, and watch the state change. Great for
testing how the tutor's advice shifts as you (via the editor) complete objectives.

    agent> ask what should I do next?        # tutor (gentle nudge)
    agent> ask how do I raise honesty? !      # tutor, pointed hint  (!! = direct answer)
    agent> next                               # the single best next objective
    agent> edit max my stats                  # editor mutates the live game
    agent> edit give me the bell
    agent> state                              # dump the GameRPC snapshot the agents see
    agent> help / quit
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ultima4.game import Game
from ultima4.agent.editor import EditorAgent
from ultima4.agent.tutor import TutorAgent

HELP = """commands:
  ask <question>     tutor answers (append ! for a pointed hint, !! for the direct answer)
  next               tutor's single best next objective
  edit <request>     editor changes the live game (e.g. "max my stats", "add a moongate")
  state              print the JSON snapshot both agents read
  help / quit"""


def main() -> None:
    game = Game()
    ed, tut = EditorAgent(game), TutorAgent(game)
    print("=== Ultima IV agent console ===  (fresh game; type 'help')")
    print(HELP)
    while True:
        try:
            line = input("\nagent> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        cmd, _, arg = line.partition(" ")
        cmd = cmd.lower()
        if cmd in ("quit", "exit", "q"):
            break
        elif cmd == "help":
            print(HELP)
        elif cmd in ("ask", "tutor"):
            level = 2 if arg.rstrip().endswith("!!") else 1 if arg.rstrip().endswith("!") else 0
            print("  " + tut.ask(arg.rstrip("! "), hint_level=level))
        elif cmd == "next":
            print("  " + tut.next_step())
        elif cmd in ("edit", "editor"):
            print("  " + ed.apply(arg))
        elif cmd in ("state", "snapshot"):
            print(json.dumps(ed.rpc.snapshot(), indent=2, ensure_ascii=False))
        else:
            print("  " + tut.ask(line))          # bare text -> a tutor question


if __name__ == "__main__":
    main()
