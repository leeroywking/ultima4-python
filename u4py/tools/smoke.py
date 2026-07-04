"""`./run smoke [out.png]` — headless one-frame render check (no window, no display needed).

Boots the game under `SDL_VIDEODRIVER=dummy`, draws a single overworld frame with the shared
`play.draw_game`, saves it to a PNG, and exits 0. This is the display-less / CI entrypoint: it
verifies the whole graphics pipeline (assets + map + draw) end-to-end without opening a window.

    ./run smoke                 # writes smoke.png in u4py/
    ./run smoke /tmp/frame.png  # writes to a chosen path
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Force the headless SDL backends BEFORE pygame initialises a video mode.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import play                                     # noqa: E402
from ultima4.game import Game                   # noqa: E402


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    out = argv[0] if argv else "smoke.png"
    which = "ega"

    play.pygame.init()
    W, H = play.VIEW * play.SCALE, play.VIEW * play.SCALE + play.PANEL_H
    screen = play.pygame.display.set_mode((W, H))
    assets = play.Assets(which)
    game = Game()                                # fresh overworld boot (from data/party_start.json)
    play.draw_game(screen, assets, game, 0)
    play.pygame.image.save(screen, out)
    play.pygame.quit()

    print(f"[smoke] rendered one {W}x{H} frame -> {out}  "
          f"(avatar at {game.party.x},{game.party.y})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
