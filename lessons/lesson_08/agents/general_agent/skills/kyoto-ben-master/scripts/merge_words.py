"""Merge new Kyoto-ben entries into output/kyoto_words.jsonl.

Usage: python3 skills/kyoto-ben-master/scripts/merge_words.py work/new_words.jsonl
"""

import json
import sys
from pathlib import Path

OUTPUT = Path("output/kyoto_words.jsonl")


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


words = {entry["word"]: entry for entry in load(OUTPUT)}

for entry in load(Path(sys.argv[1])):
    words[entry["word"]] = entry

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(
    "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in words.values()),
    encoding="utf-8",
)

print(f"{len(words)} words -> {OUTPUT}")