#!/usr/bin/env python3
"""SPLIT-BY-RUN (dataset-v2, agent G3): train/heldout split by run seed, PLATFORM export.

Usage:
  python3 split_by_run.py --runs-dir DIR --out-dir DIR [--holdout-every 4]

Run dirs (each with scenario.json + labeled.jsonl) are sorted by scenario seed and
assigned deterministically: the run at 0-based index i goes to heldout when
i % holdout_every == holdout_every - 1, everything else to train. Dirs without
labeled.jsonl are skipped with a warning.

Writes into --out-dir:
  train.jsonl, heldout.jsonl  decision rows: id "<seed>-<row_index>", state = the
                              featurize feature keys, questions.action (12-option
                              choice), labels.action, weight
  analysis.jsonl              seed/ts/quiet/label/exploration/harmful/outcome per row
  manifest.json               runs/rows/class counts per split + generated_at
  class_counts.json           per-class counts per split
"""

import argparse
import collections
import datetime
import json
import os
import sys
from typing import Any

from featurize import FEATURE_KEYS

HOLDOUT_EVERY_DEFAULT = 4

ACTION_INSTRUCTIONS = "Which resource action should the controller take for the workloads right now?"

# Verbatim dataset-v2 action taxonomy for the platform choice question.
ACTION_CRITERIA: dict[str, str] = {
    "do_nothing": "No change needed",
    "increase_cpu": "Give more CPU (raise cpu.max/weight)",
    "decrease_cpu": "Reduce CPU allocation",
    "increase_memory": "Raise memory limits",
    "decrease_memory": "Lower memory limits",
    "throttle_io": "Reduce disk I/O priority",
    "restrict_process_count": "Tighten the process-count limit",
    "protect_service": "Favor the critical service over the noisy neighbor",
    "isolate_workload": "Move the workload to a restricted cgroup (needs approval)",
    "restart_service": "Restart the workload (needs approval)",
    "kill_process": "Kill the process (needs approval)",
    "alert_operator": "Notify a human; take no automated action",
}


def read_json(path: str) -> dict[str, Any]:
    """Load one JSON object from path."""
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def read_jsonl(path: str) -> list[dict[str, Any]]:
    """Load JSONL rows from path; empty lines are skipped."""
    rows: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def decision_row(seed: Any, row_index: int, row: dict[str, Any]) -> dict[str, Any]:
    """Build one PLATFORM training row from a labeled feature row."""
    return {
        "id": f"{seed}-{row_index}",
        "state": {key: row.get(key) for key in FEATURE_KEYS},
        "questions": {
            "action": {
                "type": "choice",
                "instructions": ACTION_INSTRUCTIONS,
                "criteria": ACTION_CRITERIA,
            }
        },
        "labels": {"action": row["label"]},
        "weight": row["weight"],
    }


def analysis_row(seed: Any, row: dict[str, Any]) -> dict[str, Any]:
    """Build one human-analysis record from a labeled feature row."""
    return {
        "seed": seed,
        "ts": row["ts"],
        "quiet": row["quiet"],
        "label": row["label"],
        "exploration": row["exploration"],
        "harmful": row["harmful"],
        "outcome": row["outcome"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="split labeled runs into train/heldout (dataset-v2)")
    parser.add_argument("--runs-dir", required=True, help="directory containing run-* subdirectories")
    parser.add_argument("--out-dir", required=True, help="output directory for split files")
    parser.add_argument("--holdout-every", type=int, default=HOLDOUT_EVERY_DEFAULT, help="every Nth run goes to heldout")
    args = parser.parse_args()

    runs: list[tuple[Any, str]] = []
    for name in sorted(os.listdir(args.runs_dir)):
        run_dir = os.path.join(args.runs_dir, name)
        scenario_path = os.path.join(run_dir, "scenario.json")
        if not os.path.isfile(scenario_path):
            continue
        if not os.path.isfile(os.path.join(run_dir, "labeled.jsonl")):
            print(f"warning: skipping {run_dir}: no labeled.jsonl", file=sys.stderr)
            continue
        runs.append((read_json(scenario_path)["seed"], run_dir))
    runs.sort(key=lambda item: item[0])

    os.makedirs(args.out_dir, exist_ok=True)
    per_split = {
        "train": {"seeds": [], "rows": 0, "classes": collections.Counter()},
        "heldout": {"seeds": [], "rows": 0, "classes": collections.Counter()},
    }
    with open(os.path.join(args.out_dir, "train.jsonl"), "w", encoding="utf-8") as train_handle, open(
        os.path.join(args.out_dir, "heldout.jsonl"), "w", encoding="utf-8"
    ) as heldout_handle, open(os.path.join(args.out_dir, "analysis.jsonl"), "w", encoding="utf-8") as analysis_handle:
        handles = {"train": train_handle, "heldout": heldout_handle}
        for index, (seed, run_dir) in enumerate(runs):
            split = "heldout" if index % args.holdout_every == args.holdout_every - 1 else "train"
            per_split[split]["seeds"].append(seed)
            for row_index, row in enumerate(read_jsonl(os.path.join(run_dir, "labeled.jsonl"))):
                handles[split].write(json.dumps(decision_row(seed, row_index, row)) + "\n")
                analysis_handle.write(json.dumps(analysis_row(seed, row)) + "\n")
                per_split[split]["rows"] += 1
                per_split[split]["classes"][row["label"]] += 1

    class_counts = {
        split: dict(sorted(per_split[split]["classes"].items())) for split in ("train", "heldout")
    }
    generated_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = {
        "generated_at": generated_at,
        "holdout_every": args.holdout_every,
        "runs_dir": args.runs_dir,
        "train": {
            "n_runs": len(per_split["train"]["seeds"]),
            "seeds": per_split["train"]["seeds"],
            "n_rows": per_split["train"]["rows"],
            "class_counts": class_counts["train"],
        },
        "heldout": {
            "n_runs": len(per_split["heldout"]["seeds"]),
            "seeds": per_split["heldout"]["seeds"],
            "n_rows": per_split["heldout"]["rows"],
            "class_counts": class_counts["heldout"],
        },
    }
    with open(os.path.join(args.out_dir, "manifest.json"), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=1)
        handle.write("\n")
    with open(os.path.join(args.out_dir, "class_counts.json"), "w", encoding="utf-8") as handle:
        json.dump(class_counts, handle, indent=1)
        handle.write("\n")

    classes = sorted(set(class_counts["train"]) | set(class_counts["heldout"]))
    print(f"split_by_run: {args.out_dir} (holdout_every={args.holdout_every}, runs sorted by seed)")
    print(f"split     runs  rows")
    for split in ("train", "heldout"):
        print(f"{split:<9} {len(per_split[split]['seeds']):>4}  {per_split[split]['rows']:>4}")
    print(f"{'class':<24} {'train':>7} {'heldout':>7}")
    for action in classes:
        print(f"{action:<24} {class_counts['train'].get(action, 0):>7} {class_counts['heldout'].get(action, 0):>7}")


if __name__ == "__main__":
    main()
