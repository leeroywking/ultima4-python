"""Headless Talk demo — drive a conversation with no pygame window.

    python -m tools.talk_demo

Boots the game, walks into Britain, finds the first talkable NPC, and scripts a
conversation through the Game/Conversation engine exactly as the UI would. Proves the
Talk port end-to-end (TLK decode -> keyword loop -> yes/no question) on CI/headless.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ultima4.game import Game
from ultima4.constants import MOD_BUILDING


def main() -> None:
    g = Game()
    g.rng.seed(1)                       # deterministic: skip the random name/temperament

    # Enter Britain (location id 6) directly and place the avatar by an NPC.
    g._enter_location(6, entry=(1, 15), kind="towne")
    assert g.mode == MOD_BUILDING, g.mode
    # Iolo is the joinable companion (tlkidx 1) — has the PLAY/COMP keywords.
    npc = next(n for n in g.location.npcs if n.tlkidx == 1)
    print(f"Britain has {len(g.location.npcs)} NPCs; "
          f"talking to the one at ({npc.x},{npc.y}) tlkidx={npc.tlkidx}\n")

    # Stand next to the NPC and Talk in its direction.
    g.party.x, g.party.y = npc.x - 1, npc.y
    g.handle("T")                        # cmd_talk -> "Talk- Dir?"
    g.handle("E")                        # direction East -> starts the conversation

    script = ["name", "job", "health", "look", "PLAY", "Y", "bye"]
    for line in g.messages:
        print("  " + line)
    for word in script:
        print(f"\n> {word}")
        g.messages.clear()
        g.talk_input(word)
        for line in g.messages:
            print("  " + line)

    print(f"\nconversation ended: {g.active is None}")
    print(f"moves after talk: {g.party.moves}")


if __name__ == "__main__":
    main()
