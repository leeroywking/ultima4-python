"""Convert U4 `.EGA` graphics → canonical PNGs (the single source of truth) — `./run gfx`.

Import-time tool only: the game reads PNGs, never `.EGA`. Run once to (re)generate
`u4py/assets/` from the original data files.

Formats (all verified against the original):
  - SHAPES.EGA  : 256 tiles, 16x16 @ 4bpp linear -> a 16x16 spritesheet (assets/shapes.png).
  - CHARSET.EGA : 256 glyphs, 8x8 @ 4bpp linear -> a 16x16 fontsheet (assets/charset.png).
  - pictures    : full-screen 320x200 @ 4bpp linear, LZW-compressed (tools/lzw.py). Layout
                  determined empirically (linear, 160 B/row, hi-nibble left — not planar,
                  not even/odd) -> one PNG each (assets/<name>.png).
Small symbol/rune images use a 2nd, not-yet-identified format and are skipped (see ROADMAP).
"""
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ultima4.graphics import decode_shapes, decode_charset, _decode_ega, EGA_PALETTE
from ultima4.savefile import load_bytes, DATA_DIR
from lzw import decompress

ASSETS = Path(__file__).resolve().parent.parent / "assets"
PIC_W, PIC_H = 320, 200
PIC_BYTES = PIC_W * PIC_H // 2          # 32000


def _sheet(buffers, cw, ch, cols=16) -> Image.Image:
    rows = (len(buffers) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cw, rows * ch))
    for i, b in enumerate(buffers):
        sheet.paste(Image.frombytes("RGB", (cw, ch), b), ((i % cols) * cw, (i // cols) * ch))
    return sheet


def _picture(name: str) -> Image.Image:
    raw = decompress(load_bytes(name))
    buf = _decode_ega(raw[:PIC_BYTES], 1, PIC_W, PIC_H, EGA_PALETTE)[0]
    return Image.frombytes("RGB", (PIC_W, PIC_H), buf)


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    # Tile + font sheets, EGA (canonical) and CGA (for `./run play cga`).
    _sheet(decode_shapes(load_bytes("SHAPES.EGA")), 16, 16).save(ASSETS / "shapes.png")
    _sheet(decode_charset(load_bytes("CHARSET.EGA")), 8, 8).save(ASSETS / "charset.png")
    _sheet(decode_shapes(load_bytes("SHAPES.CGA")), 16, 16).save(ASSETS / "shapes_cga.png")
    _sheet(decode_charset(load_bytes("CHARSET.CGA")), 8, 8).save(ASSETS / "charset_cga.png")
    print(f"  shapes/charset (.png + _cga.png) -> {ASSETS}")
    pics = 0
    for p in sorted(DATA_DIR.glob("*.EGA")):
        if p.name in ("SHAPES.EGA", "CHARSET.EGA"):
            continue
        try:
            raw = decompress(p.read_bytes())
        except Exception:
            raw = b""
        if len(raw) >= PIC_BYTES:                       # a full-screen LZW picture
            _picture(p.name).save(ASSETS / f"{p.stem.lower()}.png")
            pics += 1
        # else: small 2nd-format image -> skipped (logged in ROADMAP)
    print(f"  {pics} full-screen picture PNGs -> {ASSETS}")


if __name__ == "__main__":
    main()
