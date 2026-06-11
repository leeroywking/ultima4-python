"""Overworld map (WORLD.MAP) loader + viewport, ported from U4_MAP.C.

WORLD.MAP is 256x256 tiles (one byte each) stored as an 8x8 grid of 32x32-tile chunks.
Chunk (row, col) lives at file offset (row*8 + col) * 1024; within a chunk the byte at
[ty][tx] is at chunk_base + ty*32 + tx. (C: U4_MAP.C C_2399 dlseek formula.)

The original streams one chunk at a time into a cache; we just hold all 64 KiB and index
into it. The *visible tiles* are identical — the cache was only a 1987 memory optimization.
The world wraps as a torus (movement masks coordinates with & 0xff).
"""
from __future__ import annotations

from typing import List

WORLD_SIZE = 256          # tiles per side
CHUNK = 32                # tiles per chunk side
CHUNKS_PER_ROW = 8        # 256 / 32
WORLD_BYTES = WORLD_SIZE * WORLD_SIZE  # 65536


class World:
    def __init__(self, data: bytes):
        if len(data) != WORLD_BYTES:
            raise ValueError(f"WORLD.MAP must be {WORLD_BYTES} bytes, got {len(data)}")
        self.data = bytearray(data)      # mutable: lets transport/editor place tiles

    @classmethod
    def load(cls, name: str = "world.txt") -> "World":
        """Load the overworld from its editable ascii-tilemap (the single source of truth).

        data/maps/world.txt holds the map in human-readable spatial order; we fold it back
        into the original chunked WORLD.MAP byte layout the rest of the engine indexes into.
        The binary WORLD.MAP is an import source only (tools/convert_maps.py) — never read
        here. C: U4_MAP.C chunk layout.
        """
        from . import asciimap as am
        from .savefile import DATA_DIR
        path = DATA_DIR / "maps" / name
        spatial = am.parse(path.read_text(encoding="utf-8"))["tiles"]
        return cls(am.world_spatial_to_chunks(spatial))

    def _index(self, x: int, y: int) -> int:
        x &= 0xFF
        y &= 0xFF
        chunk = (y // CHUNK) * CHUNKS_PER_ROW + (x // CHUNK)
        return chunk * (CHUNK * CHUNK) + (y % CHUNK) * CHUNK + (x % CHUNK)

    def tile_at(self, x: int, y: int) -> int:
        """Tile id at world (x, y), wrapping as a torus (C: chunked WORLD.MAP layout)."""
        return self.data[self._index(x, y)]

    def set_tile(self, x: int, y: int, tile: int) -> None:
        self.data[self._index(x, y)] = tile & 0xFF

    def viewport(self, cx: int, cy: int, radius: int = 5) -> List[List[int]]:
        """A (2*radius+1) square of tile ids centred on (cx, cy). Default 11x11."""
        span = range(-radius, radius + 1)
        return [[self.tile_at(cx + dx, cy + dy) for dx in span] for dy in span]
