"""Tile/charset graphics decoding, ported from forVS/common.c (CMN_puttile/CMN_putchar).

The reference VS build renders in CGA: shapes are 64 bytes/tile (16x16 @ 2bpp), charset
16 bytes/char (8x8 @ 2bpp), palette = CGA cyan/magenta/white. The CGA scanline
de-interleave is reproduced exactly:  visual_row = (i & 7)*2 + (i >> 3)  for shapes.
(common.c also applies a Windows bottom-up flip that cancels this; here we target a
top-down framebuffer, so we map file-row -> visual_row directly.)

EGA decoding (16-color, 128 bytes/tile) is also provided for the prettier tileset.

Output: each decoded glyph is a flat `bytes` of RGB triples (width*height*3), ready for
pygame.image.frombuffer(buf, (w, h), "RGB").
"""
from __future__ import annotations

from typing import List

# CGA palette 1, high-intensity (C: common.c U4_PALETTE). 0=black 1=cyan 2=magenta 3=white.
CGA_PALETTE = [(0x1F, 0x1F, 0x1F), (0x1F, 0xE0, 0xE0), (0xE0, 0x1F, 0xE0), (0xE0, 0xE0, 0xE0)]

# Standard 16-color EGA palette, for the SHAPES.EGA tileset.
EGA_PALETTE = [
    (0x00, 0x00, 0x00), (0x00, 0x00, 0xAA), (0x00, 0xAA, 0x00), (0x00, 0xAA, 0xAA),
    (0xAA, 0x00, 0x00), (0xAA, 0x00, 0xAA), (0xAA, 0x55, 0x00), (0xAA, 0xAA, 0xAA),
    (0x55, 0x55, 0x55), (0x55, 0x55, 0xFF), (0x55, 0xFF, 0x55), (0x55, 0xFF, 0xFF),
    (0xFF, 0x55, 0x55), (0xFF, 0x55, 0xFF), (0xFF, 0xFF, 0x55), (0xFF, 0xFF, 0xFF),
]

TILE_W = TILE_H = 16
CHAR_W = CHAR_H = 8

# File sizes (C: U4_INIT.C C_C51C) that disambiguate CGA vs EGA shape sets.
SHAPES_CGA_SIZE = 0x4000   # 256 * 64
SHAPES_EGA_SIZE = 0x8000   # 256 * 128
CHARSET_CGA_SIZE = 0x0800  # 128 * 16
CHARSET_EGA_SIZE = 0x1000  # 128 * 32


def _cga_rows(i_count: int):
    """Yield (file_row, visual_row) pairs for the CGA even/odd-bank de-interleave."""
    half = i_count >> 1  # 8 for tiles, 4 for chars
    for i in range(i_count):
        yield i, (i % half) * 2 + (i // half)


def _decode_cga(data: bytes, n: int, w: int, h: int, palette) -> List[bytes]:
    """Decode `n` glyphs of w*h @ 2bpp with CGA scanline interleave."""
    bytes_per_row = w // 4           # 4 px per byte
    glyph_bytes = bytes_per_row * h  # 64 (tile) / 16 (char)
    out: List[bytes] = []
    for g in range(n):
        base = g * glyph_bytes
        buf = bytearray(w * h * 3)
        for file_row, vis_row in _cga_rows(h):
            row_off = base + file_row * bytes_per_row
            for bx in range(bytes_per_row):
                byt = data[row_off + bx]
                for k in range(4):
                    col = (byt >> (6 - k * 2)) & 0x03
                    x = bx * 4 + k
                    p = (vis_row * w + x) * 3
                    buf[p:p + 3] = bytes(palette[col])
        out.append(bytes(buf))
    return out


def _decode_ega(data: bytes, n: int, w: int, h: int, palette) -> List[bytes]:
    """Decode `n` glyphs of w*h @ 4bpp, linear rows, 2 px/byte (high nibble = left)."""
    bytes_per_row = w // 2
    glyph_bytes = bytes_per_row * h
    out: List[bytes] = []
    for g in range(n):
        base = g * glyph_bytes
        buf = bytearray(w * h * 3)
        for row in range(h):
            row_off = base + row * bytes_per_row
            for bx in range(bytes_per_row):
                byt = data[row_off + bx]
                for k, shift in ((0, 4), (1, 0)):
                    col = (byt >> shift) & 0x0F
                    x = bx * 2 + k
                    p = (row * w + x) * 3
                    buf[p:p + 3] = bytes(palette[col])
        out.append(bytes(buf))
    return out


def decode_shapes(data: bytes) -> List[bytes]:
    """256 map tiles -> list of 16x16 RGB buffers. Auto-detects CGA vs EGA by size."""
    if len(data) == SHAPES_CGA_SIZE:
        return _decode_cga(data, 256, TILE_W, TILE_H, CGA_PALETTE)
    if len(data) == SHAPES_EGA_SIZE:
        return _decode_ega(data, 256, TILE_W, TILE_H, EGA_PALETTE)
    raise ValueError(f"SHAPES file size {len(data)} is neither CGA ({SHAPES_CGA_SIZE}) "
                     f"nor EGA ({SHAPES_EGA_SIZE})")


def decode_charset(data: bytes) -> List[bytes]:
    """Font glyphs -> list of 8x8 RGB buffers. Auto-detects CGA vs EGA and glyph count by
    size (the EGA CHARSET.EGA ships 256 glyphs x 32 bytes = 8192)."""
    if len(data) == CHARSET_CGA_SIZE:
        return _decode_cga(data, 128, CHAR_W, CHAR_H, CGA_PALETTE)
    if len(data) % 32 == 0:                       # EGA: 32 bytes/glyph (8x8 @ 4bpp)
        return _decode_ega(data, len(data) // 32, CHAR_W, CHAR_H, EGA_PALETTE)
    raise ValueError(f"CHARSET file size {len(data)} is neither CGA nor EGA")
