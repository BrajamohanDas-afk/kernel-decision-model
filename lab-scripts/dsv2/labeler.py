#!/usr/bin/env python3
"""LABELER (dataset-v2, agent G3): label featurized decisions with action + outcome.

Usage:
  python3 labeler.py --run-dir DIR

Reads DIR/rows.jsonl, DIR/decisions.jsonl, DIR/telemetry.jsonl, DIR/scenario.json and
writes DIR/labeled.jsonl: each row plus label/exploration/outcome/harmful/weight.

Outcome window: telemetry rows in (ts, ts+90s]; the baseline for counter comparisons
is the telemetry row nearest at/before ts. Victim metric over the outcome window:
  latency victim    -> v_metric_delta_or_ratio = p95_after / p95_before, where
                       p95_before is the p95 over [ts-10s, ts] via latency_metrics.
                       (The within-window p95/median tail ratio of featurize's
                       v_p95_ratio_10s is NOT used as the harm test: on the real M1
                       latency data it sits at ~1.8-2.2 even at baseline, so a 1.25
                       threshold would fire on almost every row. "Victim worsened"
                       is after-vs-before.)
  throughput victim -> v_metric_delta_or_ratio = mean(achieved_per_s/target_per_s)
                       over the outcome window (featurize's v_rate_ratio definition).

harmful is the training harm label (not an action): a decision is harmful when
  oom_kill_delta > 0 for wlp-neighbor, OR the victim measurably worsened
  (latency victim: p95_before >= 1.0 ms AND p95_ratio_after > 1.25;
   throughput victim: rate_ratio_after < 0.8).
  Neighbor CPU-throttling growth is deliberately NOT part of the harm test:
  being throttled under its own quota is the stressor working as designed
  (batch-1 finding: it falsely marked ~15 do_nothing rows per run as harmful).
weight = 0.2 if harmful else 1.0. Rows whose 90s window is truncated by the end of
the run get outcome=null, harmful=false, weight=1.0.
"""

import argparse
import collections
import json
import os
from typing import Any

from featurize import (
    QUIET_CAP,
    dig,
    is_quiet,
    latency_metrics,
    nearest_before,
    parse_ts,
    read_json,
    read_jsonl,
    throughput_metrics,
    time_index,
    window_pairs,
)

OUTCOME_WINDOW_S = 90.0
HARM_P95_RATIO = 1.25
HARM_RATE_RATIO = 0.8
HARM_THROTTLE_FACTOR = 1.5
HARM_P95_FLOOR_MS = 1.0              # ignore latency "worsening" below 1 ms p95 (noise, batch-1 finding)
HARM_THROTTLE_FLOOR_US_PER_S = 300000  # ignore throttling growth below 0.3 s/s (noise, batch-1 finding)
THROTTLE_EXEMPT_ACTIONS = ("increase_cpu", "protect_service")

NB_THROTTLED_USEC = ("cgroups", "wlp-neighbor", "cpu_stat", "throttled_usec")
NB_OOM_KILL = ("cgroups", "wlp-neighbor", "memory_events", "oom_kill")


def outcome_for(
    ts_text: str,
    label: str,
    row: dict[str, Any],
    telemetry: list[tuple[float, dict[str, Any]]],
    victim: list[tuple[float, dict[str, Any]]],
    victim_type: str,
) -> tuple[dict[str, Any] | None, bool]:
    """Compute (outcome, harmful) for one decision; (None, False) when the run ends early.

    Args:
        ts_text: decision ISO8601 timestamp (same value stored in the row).
        label: the decision action, used for the throttle-harm exemption.
        row: the featurized row (n_cpu_throttled_us_per_s_10s is the at-decision rate).
        telemetry: (epoch_seconds, telemetry row) pairs sorted by time.
        victim: (epoch_seconds, victim row) pairs sorted by time.
        victim_type: "latency" or "throughput".

    Returns:
        (outcome dict in the dataset-v2 schema, harmful flag); (None, False) when the
        telemetry ends before ts + 90s or the window has no samples.
    """
    ts = parse_ts(ts_text)
    end_limit = ts + OUTCOME_WINDOW_S
    if not telemetry or telemetry[-1][0] < end_limit:
        return None, False
    window = window_pairs(telemetry, ts, end_limit, True)
    if not window:
        return None, False
    end_t, end_row = window[-1]
    base = nearest_before(telemetry, ts)
    base_t, base_row = base if base else (ts, None)

    throttled_at_base = dig(base_row, *NB_THROTTLED_USEC)
    throttled_at_end = dig(end_row, *NB_THROTTLED_USEC)
    throttled_after = None
    if throttled_at_base is not None and throttled_at_end is not None and end_t > base_t:
        throttled_after = (throttled_at_end - throttled_at_base) / (end_t - base_t)

    oom_at_base = dig(base_row, *NB_OOM_KILL)
    oom_at_end = dig(end_row, *NB_OOM_KILL)
    oom_delta = (oom_at_end - oom_at_base) if (oom_at_base is not None and oom_at_end is not None) else None

    sys_psi_cpu_after = dig(end_row, "system", "psi_cpu_some", "avg10")

    before = window_pairs(victim, ts - 10.0, ts, False)
    after = window_pairs(victim, ts, end_limit, True)
    if victim_type == "latency":
        p95_before, _, _ = latency_metrics(before)
        p95_after, _, _ = latency_metrics(after)
        v_metric = (p95_after / p95_before) if (p95_after is not None and p95_before) else None
        # Absolute floor: sub-millisecond jitter is noise, not harm (batch 1: 15 false "harmful" do_nothing rows).
        victim_harm = (
            v_metric is not None
            and v_metric > HARM_P95_RATIO
            and p95_before is not None
            and p95_before >= HARM_P95_FLOOR_MS
        )
    else:
        _, _, rate_ratio_after = throughput_metrics(after)
        v_metric = rate_ratio_after
        victim_harm = rate_ratio_after is not None and rate_ratio_after < HARM_RATE_RATIO

    # Neighbor throttling under its own quota is expected behavior, not harm (batch-1 finding);
    # harm = OOM killed something, or the victim measurably worsened (absolute floors above).
    harmful = bool((oom_delta is not None and oom_delta > 0) or victim_harm)

    outcome = {
        "window_s": round(end_t - base_t, 3),
        "v_metric_delta_or_ratio": v_metric,
        "n_throttled_us_per_s_after": throttled_after,
        "sys_psi_cpu_avg10_after": sys_psi_cpu_after,
        "oom_kill_delta": oom_delta,
    }
    return outcome, harmful


def kept_decisions(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply featurize's quiet cap so labeled rows line up with rows.jsonl exactly."""
    kept: list[dict[str, Any]] = []
    quiet_kept = 0
    for decision in decisions:
        quiet = is_quiet(decision)
        if quiet and quiet_kept >= QUIET_CAP:
            continue
        if quiet:
            quiet_kept += 1
        kept.append(decision)
    return kept


def main() -> None:
    parser = argparse.ArgumentParser(description="label featurized decisions (dataset-v2)")
    parser.add_argument("--run-dir", required=True, help="run directory with rows/decisions/telemetry files")
    args = parser.parse_args()
    run_dir: str = args.run_dir

    scenario = read_json(os.path.join(run_dir, "scenario.json"))
    rows = read_jsonl(os.path.join(run_dir, "rows.jsonl"))
    decisions = kept_decisions(read_jsonl(os.path.join(run_dir, "decisions.jsonl")))
    telemetry = time_index(read_jsonl(os.path.join(run_dir, "telemetry.jsonl")))
    victim = time_index(read_jsonl(os.path.join(run_dir, "victim.log")))
    victim_type: str = scenario["victim_type"]

    if len(rows) != len(decisions):
        raise SystemExit(f"labeler: {len(decisions)} kept decisions but {len(rows)} feature rows in {run_dir}")

    labeled: list[dict[str, Any]] = []
    for row, decision in zip(rows, decisions):
        if row["ts"] != decision["ts"]:
            raise SystemExit(f"labeler: row ts {row['ts']!r} does not match decision ts {decision['ts']!r}")
        label: str = decision["action"]
        outcome, harmful = outcome_for(row["ts"], label, row, telemetry, victim, victim_type)
        entry = dict(row)
        entry["label"] = label
        entry["exploration"] = bool(decision.get("exploration"))
        entry["outcome"] = outcome
        entry["harmful"] = harmful
        entry["weight"] = 0.2 if harmful else 1.0
        labeled.append(entry)

    out_path = os.path.join(run_dir, "labeled.jsonl")
    with open(out_path, "w", encoding="utf-8") as handle:
        for entry in labeled:
            handle.write(json.dumps(entry) + "\n")

    total = len(labeled)
    harmful_by_action = collections.Counter(entry["label"] for entry in labeled if entry["harmful"])
    class_counts = collections.Counter(entry["label"] for entry in labeled)
    exploration_count = sum(1 for entry in labeled if entry["exploration"])

    print(f"labeler: {out_path}")
    print(f"rows={total} harmful={sum(harmful_by_action.values())}")
    print("harmful by action:")
    for action in sorted(harmful_by_action):
        print(f"  {action}: {harmful_by_action[action]}")
    print("class counts:")
    for action in sorted(class_counts):
        print(f"  {action}: {class_counts[action]}")
    exploration_share = (100.0 * exploration_count / total) if total else 0.0
    rules_count = total - exploration_count
    rules_share = (100.0 * rules_count / total) if total else 0.0
    print(f"exploration vs rules: exploration={exploration_count} ({exploration_share:.1f}%) rules={rules_count} ({rules_share:.1f}%)")


if __name__ == "__main__":
    main()
