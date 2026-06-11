"""`./run maps` — import the original binary maps into editable ascii-tilemap text files.

This is the one-time bridge: it reads the original DOS binaries (WORLD.MAP / .ULT / .DNG)
and writes their lossless, self-describing text equivalents under data/maps/. After this
runs (and the parity selftest is green), the binaries can be deleted — the text files are
the single source of truth. The originals are an IMPORT source only, like .EGA->PNG and
.TLK->JSON before them.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ultima4 import asciimap as am
from ultima4.savefile import DATA_DIR, load_bytes

MAPS_DIR = DATA_DIR / "maps"


def convert_world() -> Path:
    """WORLD.MAP (chunked 256x256) -> data/maps/world.txt (spatial ascii grid)."""
    spatial = am.world_chunks_to_spatial(load_bytes("WORLD.MAP", am._WSIZE * am._WSIZE))
    doc = am.serialize(spatial, am._WSIZE, am._WSIZE, name="world",
                       kind="overworld", wrap="torus")
    # Verify the round-trip reconstructs the exact original before we ever rely on the text.
    assert am.world_spatial_to_chunks(am.parse(doc)["tiles"]) == \
        load_bytes("WORLD.MAP"), "world.txt does not reconstruct WORLD.MAP byte-exact"
    out = MAPS_DIR / "world.txt"
    out.write_text(doc, encoding="utf-8")
    return out


def convert_towns() -> list[Path]:
    """Every .ULT (32x32 grid + 256-byte NPC block) -> data/maps/<base>.txt, lossless."""
    out = []
    for ult in sorted(DATA_DIR.glob("*.ULT")):
        raw = ult.read_bytes()
        tiles, npc = raw[:1024], raw[1024:]
        doc = am.serialize_town(tiles, npc, name=ult.stem.lower())
        gtiles, gnpc = am.parse_town(doc)
        assert gtiles + gnpc == raw, f"{ult.name}: town text does not reconstruct the .ULT byte-exact"
        dest = MAPS_DIR / f"{ult.stem.lower()}.txt"
        dest.write_text(doc, encoding="utf-8")
        out.append(dest)
    return out


def convert_dungeons() -> list[Path]:
    """Each .DNG (8 level grids + room-data block) -> data/maps/<base>.dng.txt, lossless.

    CAMP.DNG (192 B) is a special camp arena, not an 8-level dungeon — skipped here and
    tracked in the deletion-readiness audit, not silently dropped.
    """
    out = []
    for dng in sorted(DATA_DIR.glob("*.DNG")):
        raw = dng.read_bytes()
        if len(raw) < am.DNG_TILE_BYTES:
            print(f"[maps] SKIP {dng.name} ({len(raw)} B — not an 8-level dungeon; see audit)")
            continue
        doc = am.serialize_dungeon(raw, name=dng.stem.lower())
        assert am.parse_dungeon(doc) == raw, f"{dng.name}: dungeon text does not reconstruct byte-exact"
        dest = MAPS_DIR / f"{dng.stem.lower()}.dng.txt"
        dest.write_text(doc, encoding="utf-8")
        out.append(dest)
    return out


def main(argv=None):
    MAPS_DIR.mkdir(parents=True, exist_ok=True)
    written = [convert_world(), *convert_towns(), *convert_dungeons()]
    for p in written:
        print(f"[maps] wrote {p.relative_to(DATA_DIR.parent)}  ({p.stat().st_size} bytes)")


if __name__ == "__main__":
    main(sys.argv[1:])
