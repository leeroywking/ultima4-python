"""Export the binary .TLK dialogue files to plain-text JSON.

    python -m tools.dump_dialogue                 # all towns -> data/dialogue/*.json
    python -m tools.dump_dialogue BRITAIN.TLK     # one file, printed to stdout

This is the IMPORT step for dialogue (mirrors tools/convert_graphics for art): an opaque
4608-byte binary becomes the legible JSON the game actually speaks from at runtime — the
single source of truth the editor agent rewrites ("change Iolo's job to ...") and the tutor
agent reads ("who in Britain talks about the bell?"). The .TLK is never read at runtime; run
this once (or after dropping in fresh .TLK files) to (re)generate data/dialogue/*.json.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ultima4.data_tables import LOCATION_FILES, TLK_FILES
from ultima4.dialogue import TalkData


def town_name(tlk: str) -> str:
    return tlk.split(".")[0].title()


def to_json(tlk_file: str) -> list:
    return [d.to_dict() for d in TalkData.load(tlk_file).records]


def main(argv: list) -> None:
    if argv:
        print(json.dumps(to_json(argv[0]), indent=2, ensure_ascii=False))
        return
    out_dir = Path(__file__).resolve().parent.parent / "data" / "dialogue"
    out_dir.mkdir(exist_ok=True)
    total = 0
    for loc_file, tlk_file in zip(LOCATION_FILES, TLK_FILES):
        records = to_json(tlk_file)
        dest = out_dir / f"{town_name(tlk_file)}.json"
        dest.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  {tlk_file:14} -> {dest.relative_to(out_dir.parent.parent)}  ({len(records)} NPCs)")
        total += len(records)
    print(f"Exported {total} NPC dialogues from {len(TLK_FILES)} towns to {out_dir}")


if __name__ == "__main__":
    main(sys.argv[1:])
