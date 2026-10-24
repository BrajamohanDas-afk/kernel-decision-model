"""Fetch evaluation per-row data (rows_url) from result JSONs immediately.

Evaluation download links expire after ~1 hour — this script exists to be run
right after any evaluation, so reports can always be built later.

Usage: python fetch_eval_rows.py results/v2-2b-tuned.json [more.json ...]
"""
import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent

for arg in sys.argv[1:]:
    src = Path(arg)
    if not src.is_absolute():
        src = HERE / src
    data = json.loads(src.read_text(encoding="utf-8"))
    url = data.get("rows_url")
    if not url:
        print("no rows_url in", src)
        continue
    out = src.with_name(src.stem + "_rows.jsonl")
    with urllib.request.urlopen(url, timeout=60) as resp:
        payload = resp.read()
    out.write_bytes(payload)
    lines = payload.count(b"\n")
    print("saved {} ({} rows)".format(out, lines))
print("DONE")
