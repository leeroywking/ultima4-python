"""ascii-tilemap — the editable, self-describing text format that REPLACES the original
binary maps (WORLD.MAP / .ULT / .DNG) as the single source of truth.

Once the original DOS data files are deleted, these text files are the *only* copy — there
is no binary to regenerate from. So this codec is built to two hard rules:

1. **Lossless.** `parse(serialize(tiles)) == tiles` exactly, for every byte. Nothing the
   original held may be dropped — including bytes the game doesn't consume yet (a town's
   inactive-NPC slots, a dungeon's room-data block). Those ride along verbatim.
2. **Loud, never silent, on corruption.** A Windows editor that strips trailing whitespace,
   reflows, or re-encodes a file must produce a *rejected-on-load* error, not a
   silently-wrong map. Three guards enforce that:
     - every grid row is bracketed by `|` … `|` sentinels (whitespace-stripping can't
       shorten a row undetected),
     - the row is asserted to be exactly `width` tiles,
     - a `crc32` footer over the tile bytes is recomputed on load and must match.

The file embeds its own legend (char -> tile id), so it depends on nothing external: the
loader reads the mapping straight out of the file. Tiles with a natural mnemonic get one
(`~` water, `.` grass, `^` mountains); the rest are assigned deterministically from a pool.
"""
from __future__ import annotations

import re
import zlib
from typing import Dict, List, Tuple

from .tiles import tile_name

FORMAT_TAG = "ascii-tilemap v1"

# Chars never used as a legend glyph: the row sentinel, the comment marker, whitespace, and
# a couple that editors / shells like to mangle. Everything else printable is fair game.
_RESERVED = set(' \t#|"\\')
_POOL = [chr(c) for c in range(0x21, 0x7F) if chr(c) not in _RESERVED]

# Preferred mnemonic glyph per tile id, so a hand-read map looks like terrain. Anything not
# listed draws from _POOL. (Purely cosmetic — the embedded legend is what the loader trusts.)
_PREFERRED: Dict[int, str] = {
    0x00: "~",  # deep water
    0x01: ":",  # medium water
    0x02: ",",  # shallow water
    0x03: "&",  # swamp
    0x04: ".",  # grass
    0x05: "'",  # scrub
    0x06: "%",  # forest
    0x07: "n",  # hills
    0x08: "^",  # mountains
    0x09: "O",  # dungeon entrance
    0x0A: "T",  # town
    0x0B: "C",  # castle
    0x0C: "V",  # village
    0x17: "=",  # bridge
    0x1B: "<",  # ladder up
    0x1C: ">",  # ladder down
    0x1E: "$",  # shrine
    0x3A: "+",  # locked door
    0x3B: "/",  # door
    0x3E: "*",  # brick floor
    0x7F: "B",  # brick
    0xF0: "F",  # dungeon: wall kind (0xF nibble) reads as 'F' nicely too
}


def choose_legend(tile_ids) -> Dict[int, str]:
    """Deterministic id->char for exactly the tile ids present. Mnemonic where possible."""
    legend: Dict[int, str] = {}
    used = set()
    ids = sorted(set(tile_ids))
    # First pass: honor preferred glyphs that are free.
    for tid in ids:
        ch = _PREFERRED.get(tid)
        if ch and ch not in used:
            legend[tid] = ch
            used.add(ch)
    # Second pass: fill the rest from the pool, lowest free char first (stable).
    pool = [c for c in _POOL if c not in used]
    pi = 0
    for tid in ids:
        if tid in legend:
            continue
        if pi >= len(pool):
            raise ValueError(f"legend overflow: {len(ids)} distinct tiles > {len(_POOL)} glyphs")
        legend[tid] = pool[pi]
        pi += 1
    return legend


def _crc(data: bytes) -> str:
    return f"{zlib.crc32(bytes(data)) & 0xFFFFFFFF:08x}"


def serialize(tiles: bytes, width: int, height: int, *, name: str, kind: str,
              wrap: str = "none", extra_lines: List[str] | None = None) -> str:
    """Render `tiles` (row-major, length width*height) as an ascii-tilemap document.

    `extra_lines` are appended verbatim after the grid (e.g. a town's `# npcs:` table or a
    pointer to a room-data sidecar); they are comments to this codec and round-trip untouched.
    """
    if len(tiles) != width * height:
        raise ValueError(f"tiles is {len(tiles)} bytes, expected {width*height}")
    legend = choose_legend(tiles)
    out: List[str] = []
    out.append(f"# Ultima IV map: {name}  ({kind})")
    out.append("# This file is the SINGLE SOURCE OF TRUTH for this map — edit freely.")
    out.append("# Do NOT let an editor reflow it or strip trailing spaces; rows are fixed-width")
    out.append("# and bracketed by | … |, and the crc32 footer is verified on load.")
    out.append(f"# format: {FORMAT_TAG}  width={width} height={height} wrap={wrap}")
    out.append("# legend (char  hex  name):")
    for tid in sorted(legend):
        out.append(f"#   {legend[tid]}  {tid:02x}  {tile_name(tid)}")
    out.append("#")
    for row in range(height):
        chars = "".join(legend[tiles[row * width + col]] for col in range(width))
        out.append(f"|{chars}|")
    out.append(f"# crc32: {_crc(tiles)}")
    if extra_lines:
        out.extend(extra_lines)
    return "\n".join(out) + "\n"


_META_RE = re.compile(r"format:\s*ascii-tilemap v1\s+width=(\d+)\s+height=(\d+)\s+wrap=(\S+)")
_LEGEND_RE = re.compile(r"^#\s+(\S)\s+([0-9A-Fa-f]{2})\s+\S+\s*$")
_ROW_RE = re.compile(r"^\|(.*)\|$")
_CRC_RE = re.compile(r"crc32:\s*([0-9A-Fa-f]{8})")


def parse(text: str) -> dict:
    """Parse an ascii-tilemap document back to its tile bytes, validating every guard.

    Returns {tiles: bytes, width, height, wrap, extra_lines}. Raises ValueError (loudly) on
    any structural damage — wrong row width, missing sentinel, unknown glyph, crc mismatch.
    """
    lines = text.splitlines()
    meta = None
    legend: Dict[str, int] = {}
    rows: List[str] = []
    crc_want = None
    extra: List[str] = []
    in_grid = False
    for ln in lines:
        m = _ROW_RE.match(ln)
        if m:
            in_grid = True
            rows.append(m.group(1))
            continue
        if ln.startswith("#"):
            if meta is None:
                mm = _META_RE.search(ln)
                if mm:
                    meta = (int(mm.group(1)), int(mm.group(2)), mm.group(3))
                    continue
            lm = _LEGEND_RE.match(ln)
            if lm:
                legend[lm.group(1)] = int(lm.group(2), 16)
                continue
            cm = _CRC_RE.search(ln)
            if cm:
                crc_want = cm.group(1)
                continue
            if in_grid:                 # comments after the grid = caller's extra_lines
                extra.append(ln)
            continue
        if in_grid and ln.strip():      # a non-comment, non-row line after the grid
            extra.append(ln)
    if meta is None:
        raise ValueError("not an ascii-tilemap: missing 'format: ascii-tilemap v1' header")
    width, height, wrap = meta
    if len(rows) != height:
        raise ValueError(f"expected {height} rows, found {len(rows)} (file truncated or reflowed?)")
    tiles = bytearray()
    for y, r in enumerate(rows):
        if len(r) != width:
            raise ValueError(f"row {y} is {len(r)} tiles, expected {width} "
                             f"(an editor may have stripped/added chars)")
        for x, ch in enumerate(r):
            if ch not in legend:
                raise ValueError(f"row {y} col {x}: glyph {ch!r} not in legend")
            tiles.append(legend[ch])
    if crc_want is None:
        raise ValueError("missing crc32 footer")
    got = _crc(tiles)
    if got != crc_want:
        raise ValueError(f"crc32 mismatch: file says {crc_want}, tiles hash {got} — file is damaged")
    return {"tiles": bytes(tiles), "width": width, "height": height, "wrap": wrap,
            "extra_lines": extra}


# --- town NPC block <-> readable table ---------------------------------------
# The .ULT trailer is a 256-byte tNPC block: 8 parallel arrays of 32 entries each
# (gtile@0x00, x@0x20, y@0x40, tile@0x60, old_x@0x80, old_y@0xA0, var@0xC0, tlk@0xE0).
# We render it as one hex row per non-empty slot and rebuild the full 256 bytes on load —
# slots whose 8 bytes are all zero are omitted and reconstructed as zero (lossless).
_NPC_COLS = ("gtile", "x", "y", "tile", "oldx", "oldy", "move", "talk")
_NPC_OFF = (0x00, 0x20, 0x40, 0x60, 0x80, 0xA0, 0xC0, 0xE0)
NPC_BLOCK_BYTES = 0x100
_NPC_ROW_RE = re.compile(r"^#\s+" + r"\s+".join([r"([0-9a-fA-F]{2})"] * 9))


def npc_block_to_lines(block: bytes) -> List[str]:
    if len(block) != NPC_BLOCK_BYTES:
        raise ValueError(f"npc block must be {NPC_BLOCK_BYTES} bytes, got {len(block)}")
    lines = ["# npcs — one hex row per slot from the .ULT trailer (edit to move/retalk NPCs):",
             "# slot " + " ".join(c.rjust(4) for c in _NPC_COLS) + "    ; tile"]
    for slot in range(32):
        vals = [block[off + slot] for off in _NPC_OFF]
        if not any(vals):
            continue                                  # empty slot -> reconstructed as zero
        cells = " ".join(f"{v:02x}".rjust(4) for v in vals)
        lines.append(f"#  {slot:02x}  {cells}    ; {tile_name(vals[3])}")
    return lines


def npc_lines_to_block(extra_lines: List[str]) -> bytes:
    block = bytearray(NPC_BLOCK_BYTES)
    seen = False
    for ln in extra_lines:
        m = _NPC_ROW_RE.match(ln)
        if not m:
            continue
        seen = True
        nums = [int(g, 16) for g in m.groups()]
        slot, vals = nums[0], nums[1:]
        if not 0 <= slot < 32:
            raise ValueError(f"npc slot {slot:#x} out of range 0..31")
        for off, v in zip(_NPC_OFF, vals):
            block[off + slot] = v
    if not seen:
        raise ValueError("town map has no '# npcs' table — file truncated?")
    return bytes(block)


def serialize_town(tiles: bytes, npc_block: bytes, *, name: str, kind: str = "town") -> str:
    """A 32x32 .ULT: ascii grid + the NPC table as trailing extra_lines."""
    return serialize(tiles, 32, 32, name=name, kind=kind, wrap="none",
                     extra_lines=npc_block_to_lines(npc_block))


def parse_town(text: str) -> Tuple[bytes, bytes]:
    """Inverse of serialize_town -> (1024-byte tile grid, 256-byte NPC block)."""
    g = parse(text)
    if g["width"] != 32 or g["height"] != 32:
        raise ValueError(f"town map must be 32x32, got {g['width']}x{g['height']}")
    return g["tiles"], npc_lines_to_block(g["extra_lines"])


# --- dungeons: 8 level grids + the (currently opaque) room-data block ---------
# A .DNG is 8 stacked 8x8 levels (first 512 bytes, nibble-encoded: high nibble = kind) plus
# a room-data block the engine doesn't parse yet (4096 B; 16384 for the Abyss). We render the
# levels as ascii grids and carry the room block verbatim as hex so deleting the .DNG loses
# nothing — when the altar/stone rooms get implemented, the bytes are already here. C: U4_DNG.C.
DNG_TILE_BYTES = 512
_DNG_SIZE = 8
_DNG_LEVELS = 8
_DNG_KINDS = {0x0: "corridor", 0x1: "ladder_up", 0x2: "ladder_down", 0x3: "ladder_both",
              0x4: "chest", 0x5: "ceiling_hole", 0x6: "floor_hole", 0x7: "fountain",
              0x8: "field", 0x9: "room", 0xA: "altar", 0xB: "door_special", 0xD: "door",
              0xE: "room_marker", 0xF: "wall"}
_DNG_HEAD_RE = re.compile(r"format:\s*ascii-dungeon v1\s+size=(\d+)\s+levels=(\d+)")
_DNG_LVL_RE = re.compile(r"^==\s*level\s+(\d+)\s*==")
_DNG_HEX_RE = re.compile(r"^#\s*([0-9a-fA-F]{2}(?:\s+[0-9a-fA-F]{2})*)\s*$")


def _dng_name(b: int) -> str:
    base = _DNG_KINDS.get(b >> 4, f"kind_{b >> 4:x}")
    return base if (b & 0xF) == 0 else f"{base}_{b & 0xF:x}"


def serialize_dungeon(data: bytes, *, name: str) -> str:
    if len(data) < DNG_TILE_BYTES:
        raise ValueError(f"{name}: {len(data)} bytes < {DNG_TILE_BYTES} (not 8 dungeon levels)")
    levels, rooms = data[:DNG_TILE_BYTES], data[DNG_TILE_BYTES:]
    legend = choose_legend(levels)
    out = [f"# Ultima IV dungeon: {name}",
           "# SINGLE SOURCE OF TRUTH — 8 levels of 8x8 (nibble-coded), then the room-data block.",
           f"# format: ascii-dungeon v1  size={_DNG_SIZE} levels={_DNG_LEVELS}",
           "# legend (char  hex  kind):"]
    for tid in sorted(legend):
        out.append(f"#   {legend[tid]}  {tid:02x}  {_dng_name(tid)}")
    out.append("#")
    for L in range(_DNG_LEVELS):
        out.append(f"== level {L} ==")
        for row in range(_DNG_SIZE):
            base = L * 64 + row * _DNG_SIZE
            out.append("|" + "".join(legend[levels[base + c]] for c in range(_DNG_SIZE)) + "|")
    out.append(f"# crc32: {_crc(data)}")
    out.append(f"# room-data block ({len(rooms)} bytes) — verbatim hex, edit only when you know "
               "the room format:")
    for i in range(0, len(rooms), 32):
        out.append("# " + " ".join(f"{b:02x}" for b in rooms[i:i + 32]))
    return "\n".join(out) + "\n"


def parse_dungeon(text: str) -> bytes:
    legend: Dict[str, int] = {}
    head = None
    levels = bytearray()
    rooms = bytearray()
    crc_want = None
    in_rooms = False
    for ln in text.splitlines():
        if head is None:
            hm = _DNG_HEAD_RE.search(ln)
            if hm:
                head = (int(hm.group(1)), int(hm.group(2)))
                continue
        m = _ROW_RE.match(ln)
        if m:
            r = m.group(1)
            for ch in r:
                if ch not in legend:
                    raise ValueError(f"dungeon glyph {ch!r} not in legend")
                levels.append(legend[ch])
            continue
        cm = _CRC_RE.search(ln)
        if cm:
            crc_want = cm.group(1)
            in_rooms = True                  # room hex follows the crc line
            continue
        if in_rooms:
            hx = _DNG_HEX_RE.match(ln)
            if hx:
                rooms += bytes(int(b, 16) for b in hx.group(1).split())
            continue
        lm = _LEGEND_RE.match(ln)
        if lm:
            legend[lm.group(1)] = int(lm.group(2), 16)
    if head is None:
        raise ValueError("not an ascii-dungeon file (missing format header)")
    if len(levels) != DNG_TILE_BYTES:
        raise ValueError(f"expected {DNG_TILE_BYTES} level tiles, got {len(levels)} "
                         "(a level grid was truncated or reflowed?)")
    data = bytes(levels) + bytes(rooms)
    if crc_want is None:
        raise ValueError("missing crc32 footer")
    if _crc(data) != crc_want:
        raise ValueError(f"crc32 mismatch: file says {crc_want}, data hashes {_crc(data)} — damaged")
    return data


# --- overworld chunk <-> spatial reordering ----------------------------------
# WORLD.MAP stores 256x256 as an 8x8 grid of 32x32 chunks (chunk r,c at offset (r*8+c)*1024).
# Humans want to read it as a plain top-to-bottom map, so the text file holds spatial
# (row-major) order; these convert between the two. (C: U4_MAP.C C_2399 chunk dlseek.)
_WCHUNK = 32
_WPERROW = 8
_WSIZE = 256


def world_chunks_to_spatial(data: bytes) -> bytes:
    out = bytearray(_WSIZE * _WSIZE)
    for y in range(_WSIZE):
        for x in range(_WSIZE):
            chunk = (y // _WCHUNK) * _WPERROW + (x // _WCHUNK)
            src = chunk * (_WCHUNK * _WCHUNK) + (y % _WCHUNK) * _WCHUNK + (x % _WCHUNK)
            out[y * _WSIZE + x] = data[src]
    return bytes(out)


def world_spatial_to_chunks(spatial: bytes) -> bytes:
    out = bytearray(_WSIZE * _WSIZE)
    for y in range(_WSIZE):
        for x in range(_WSIZE):
            chunk = (y // _WCHUNK) * _WPERROW + (x // _WCHUNK)
            dst = chunk * (_WCHUNK * _WCHUNK) + (y % _WCHUNK) * _WCHUNK + (x % _WCHUNK)
            out[dst] = spatial[y * _WSIZE + x]
    return bytes(out)
