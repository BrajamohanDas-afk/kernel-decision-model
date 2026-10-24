"""Merge the M1 v1+v2 the platform rows into the pilot dataset (train + heldout)."""
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent  # "kernel decision model"
OUT = HERE / "data"
OUT.mkdir(exist_ok=True)


def load(path):
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


train = load(ROOT / "results" / "m1-v1" / "decision_train.jsonl") + load(ROOT / "results" / "m1-v2" / "decision_train.jsonl")
held = load(ROOT / "results" / "m1-v1" / "decision_heldout.jsonl") + load(ROOT / "results" / "m1-v2" / "decision_heldout.jsonl")

seen = set()
dups = 0
for row in train + held:
    if row["id"] in seen:
        dups += 1
    seen.add(row["id"])

(OUT / "merged_train.jsonl").write_text(
    "\n".join(json.dumps(r) for r in train) + "\n", encoding="utf-8")
(OUT / "merged_heldout.jsonl").write_text(
    "\n".join(json.dumps(r) for r in held) + "\n", encoding="utf-8")

print("train rows:", len(train), "| heldout rows:", len(held), "| duplicate ids:", dups)
print("train classes:", dict(Counter(r["labels"]["action"] for r in train)))
print("heldout classes:", dict(Counter(r["labels"]["action"] for r in held)))
