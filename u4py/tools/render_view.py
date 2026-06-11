"""Headless render check: decode tiles + WORLD.MAP and draw the avatar's view to PNGs.

Usage:
    python -m tools.render_view [cga|ega]

Outputs (in u4py/):
    view_11x11.png   -- the 11x11 overworld viewport the player sees, avatar centred.
    world_overview.png -- whole 256x256 map, one representative colour per tile.

This verifies the full graphics pipeline (shape decode + map chunk indexing) end-to-end
against the real game data, before we add the interactive pygame window.
"""
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ultima4.graphics import decode_shapes  # noqa: E402
from ultima4.savefile import load_bytes, load_party  # noqa: E402
from ultima4.world import World  # noqa: E402

AVATAR_TILE = 0x1F  # TIL_1F: on-foot party


def tile_images(which: str):
    fname = "SHAPES.CGA" if which == "cga" else "SHAPES.EGA"
    tiles = decode_shapes(load_bytes(fname))
    return [Image.frombytes("RGB", (16, 16), t) for t in tiles], fname


def main(which: str = "cga") -> None:
    imgs, fname = tile_images(which)
    world = World.load()
    party = load_party()

    # Avatar overworld position (C: C_26B6 uses Party._x/_y when loc < 0x11).
    cx, cy = party.x, party.y
    print(f"tiles: {fname}  avatar@({cx},{cy}) tile={world.tile_at(cx, cy):#04x}")

    # --- 11x11 viewport, scaled 3x, avatar drawn at centre ---
    R, SCALE = 5, 3
    n = 2 * R + 1
    view = Image.new("RGB", (n * 16, n * 16))
    for j, dy in enumerate(range(-R, R + 1)):
        for i, dx in enumerate(range(-R, R + 1)):
            tid = world.tile_at(cx + dx, cy + dy)
            view.paste(imgs[tid], (i * 16, j * 16))
    view.paste(imgs[AVATAR_TILE], (R * 16, R * 16))  # avatar centre
    view = view.resize((n * 16 * SCALE, n * 16 * SCALE), Image.NEAREST)
    view.save("view_11x11.png")
    print("wrote view_11x11.png")

    # --- whole-map overview: average colour of each tile's sprite, 1px per world tile ---
    avg = []
    for t in imgs:
        px = t.getdata()
        k = len(px)
        avg.append(tuple(sum(c[ch] for c in px) // k for ch in range(3)))
    overview = Image.new("RGB", (256, 256))
    ov = overview.load()
    for y in range(256):
        for x in range(256):
            ov[x, y] = avg[world.tile_at(x, y)]
    ov[cx, cy] = (255, 0, 0)  # mark the avatar
    overview = overview.resize((512, 512), Image.NEAREST)
    overview.save("world_overview.png")
    print("wrote world_overview.png")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "cga")
