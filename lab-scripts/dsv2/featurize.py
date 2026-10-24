#!/usr/bin/env python3
"""FEATURIZE (dataset-v2, agent G3): one feature row per controller decision.

Usage:
  python3 featurize.py --run-dir DIR

Reads DIR/scenario.json, DIR/telemetry.jsonl, DIR/decisions.jsonl, DIR/victim.log
and writes DIR/rows.jsonl, one row per decision ts (quiet rows capped).

Conventions:
  - "current" values come from the telemetry row nearest at/before the decision ts.
  - rate features use the cumulative-counter delta over [ts-10s, ts] (30s for
    memory_events.high) divided by the seconds between the first and last telemetry
    row of that window that carries the counter. throttled_usec and memory_events
    rates are per second; io_stat.wbytes is converted to MB (MiB, /1024^2).
  - quiet: the decision's own state.cgroups["wlp-neighbor"] is null. Feature values
    still come from telemetry (single source of state truth). Only the first
    QUIET_CAP quiet rows per run are kept, so quiet do-nothing rows cannot dominate.
  - victim features over [ts-10s, ts]: latency victim -> p95 (ms) and p95/median;
    throughput victim -> mean(achieved_per_s/target_per_s).
  - prev_action / seconds_since_prev_action come from the previous decision record.
  - timestamps are ISO8601 UTC strings ("...Z"); the output keeps the decision ts
    verbatim.

The delivered v2 key list contains both n_cpu_psi_avg10 and n_psi_cpu_avg10; both
map to the same neighbor cgroup psi_cpu_some.avg10 sample.
"""

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any

QUIET_CAP = 10
MB_DIVISOR = 1024.0 * 1024.0

FEATURE_KEYS: list[str] = [
    "n_cpu_max_cores",
    "n_cpu_throttled_us_per_s_10s",
    "n_cpu_psi_avg10",
    "n_cpu_psi_slope",
    "n_mem_current_mb",
    "n_mem_high_mb",
    "n_mem_headroom_mb",
    "n_mem_events_high_per_s_30s",
    "n_io_wbytes_mb_per_s_10s",
    "n_pids",
    "n_pids_delta_10s",
    "n_psi_cpu_avg10",
    "n_psi_mem_some_avg10",
    "n_psi_mem_full_avg10",
    "n_psi_io_some_avg10",
    "c_cpu_throttled_us_per_s_10s",
    "c_mem_current_mb",
    "c_psi_cpu_avg10",
    "c_psi_mem_full_avg10",
    "v_p95_ms_10s",
    "v_p95_ratio_10s",
    "v_rate_ratio_10s",
    "sys_psi_cpu_avg10",
    "sys_psi_cpu_slope",
    "sys_psi_mem_some_avg10",
    "sys_psi_io_some_avg10",
    "sys_load1",
    "prev_action",
    "seconds_since_prev_action",
]


def parse_ts(text: Any) -> float:
    """Parse an ISO8601 UTC timestamp ("...Z", ms precision) into epoch seconds."""
    if not isinstance(text, str):
        raise ValueError(f"timestamp is not a string: {text!r}")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def read_json(path: str) -> dict[str, Any]:
    """Load one JSON object from path."""
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def read_jsonl(path: str) -> list[dict[str, Any]]:
    """Load JSONL rows from path; empty lines are skipped, bad JSON raises with context."""
    rows: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"bad JSON in {path} line {line_number}: {exc}") from exc
    return rows


def dig(obj: Any, *keys: str) -> Any:
    """Read obj[key1][key2]... returning None as soon as the path is missing."""
    for key in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def time_index(rows: list[dict[str, Any]]) -> list[tuple[float, dict[str, Any]]]:
    """Sort rows by parsed ts and return (epoch_seconds, row) pairs."""
    return sorted(((parse_ts(row["ts"]), row) for row in rows), key=lambda pair: pair[0])


def window_pairs(
    pairs: list[tuple[float, dict[str, Any]]], lo: float, hi: float, lo_strict: bool
) -> list[tuple[float, dict[str, Any]]]:
    """Filter (epoch_seconds, row) pairs to (lo, hi], [lo, hi] when lo is not strict."""
    if lo_strict:
        return [(ts, row) for ts, row in pairs if lo < ts <= hi]
    return [(ts, row) for ts, row in pairs if lo <= ts <= hi]


def nearest_before(pairs: list[tuple[float, dict[str, Any]]], ts: float) -> tuple[float, dict[str, Any]] | None:
    """Return the (epoch_seconds, row) pair nearest at/before ts, or None."""
    found: tuple[float, dict[str, Any]] | None = None
    for pair in pairs:
        if pair[0] <= ts:
            found = pair
        else:
            break
    return found


def counter_rate(points: list[tuple[float, dict[str, Any]]], path: tuple[str, ...], scale: float) -> float | None:
    """(last - first) / seconds over the non-null counter samples in points, times scale."""
    samples = [(ts, dig(row, *path)) for ts, row in points]
    samples = [(ts, value) for ts, value in samples if value is not None]
    if len(samples) < 2:
        return None
    (t0, v0), (t1, v1) = samples[0], samples[-1]
    if t1 <= t0:
        return None
    return (v1 - v0) / (t1 - t0) * scale


def counter_delta(points: list[tuple[float, dict[str, Any]]], path: tuple[str, ...]) -> float | None:
    """last - first over the non-null counter samples in points."""
    samples = [(ts, dig(row, *path)) for ts, row in points]
    samples = [(ts, value) for ts, value in samples if value is not None]
    if len(samples) < 2:
        return None
    return samples[-1][1] - samples[0][1]


def percentile(values: list[float], quantile: float) -> float | None:
    """Linear-interpolation percentile (numpy-style) of values, or None when empty."""
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    fraction = position - low
    return ordered[low] * (1.0 - fraction) + ordered[high] * fraction


def psi_avg10_slope(block: Any, stream: str) -> tuple[float | None, float | None]:
    """(psi_cpu_some.avg10, avg10 - avg60) for a cgroup-like block; None when missing."""
    sub = dig(block, stream)
    if not isinstance(sub, dict):
        return None, None
    avg10, avg60 = sub.get("avg10"), sub.get("avg60")
    slope = (avg10 - avg60) if (avg10 is not None and avg60 is not None) else None
    return avg10, slope


def cpu_max_cores(cpu_max: Any) -> float | None:
    """Parse cpu.max ("<max> <period>" usec, "max" = unlimited) into core count."""
    if not isinstance(cpu_max, str):
        return None
    parts = cpu_max.split()
    if len(parts) != 2 or parts[0] == "max":
        return None
    try:
        return int(parts[0]) / float(int(parts[1]))
    except ValueError:
        return None


def latency_metrics(pairs: list[tuple[float, dict[str, Any]]]) -> tuple[float | None, float | None, float | None]:
    """Latency window: (p95_ms, p95/median, None)."""
    latencies = [row["latency_us"] / 1000.0 for _, row in pairs if row.get("latency_us") is not None]
    if not latencies:
        return None, None, None
    p95 = percentile(latencies, 0.95)
    median = percentile(latencies, 0.5)
    ratio = (p95 / median) if (p95 is not None and median) else None
    return p95, ratio, None


def throughput_metrics(pairs: list[tuple[float, dict[str, Any]]]) -> tuple[float | None, float | None, float | None]:
    """Throughput window: (None, None, mean(achieved/target))."""
    ratios = [
        row["achieved_per_s"] / row["target_per_s"]
        for _, row in pairs
        if row.get("achieved_per_s") is not None and row.get("target_per_s")
    ]
    if not ratios:
        return None, None, None
    return None, None, sum(ratios) / len(ratios)


def is_quiet(decision: dict[str, Any]) -> bool:
    """QUIET: the decision row's own state has no wlp-neighbor cgroup block."""
    return dig(decision, "state", "cgroups", "wlp-neighbor") is None


def build_row(
    decision: dict[str, Any],
    prev: dict[str, Any] | None,
    telemetry: list[tuple[float, dict[str, Any]]],
    victim: list[tuple[float, dict[str, Any]]],
    victim_type: str,
    seed: Any,
    quiet: bool,
) -> dict[str, Any]:
    """Build one feature row for a decision from telemetry and victim windows."""
    ts = parse_ts(decision["ts"])
    win10 = window_pairs(telemetry, ts - 10.0, ts, False)
    win30 = window_pairs(telemetry, ts - 30.0, ts, False)
    current_pair = nearest_before(telemetry, ts)
    current = current_pair[1] if current_pair else None
    neighbor = dig(current, "cgroups", "wlp-neighbor")
    critical = dig(current, "cgroups", "wlp-critical")
    system = dig(current, "system")

    n_cpu_psi10, n_cpu_psi_slope = psi_avg10_slope(neighbor, "psi_cpu_some")
    c_cpu_psi10, _ = psi_avg10_slope(critical, "psi_cpu_some")
    sys_psi_cpu10, sys_psi_cpu_slope = psi_avg10_slope(system, "psi_cpu_some")

    n_mem_current = dig(neighbor, "memory_current_mb")
    n_mem_high = dig(neighbor, "memory_high_mb")
    if victim_type == "latency":
        v_p95, v_p95_ratio, v_rate_ratio = latency_metrics(window_pairs(victim, ts - 10.0, ts, False))
    else:
        v_p95, v_p95_ratio, v_rate_ratio = throughput_metrics(window_pairs(victim, ts - 10.0, ts, False))

    row: dict[str, Any] = {"ts": decision["ts"], "run_seed": seed, "quiet": quiet}
    row.update(
        {
            "n_cpu_max_cores": cpu_max_cores(dig(neighbor, "cpu_max")),
            "n_cpu_throttled_us_per_s_10s": counter_rate(win10, ("cgroups", "wlp-neighbor", "cpu_stat", "throttled_usec"), 1.0),
            "n_cpu_psi_avg10": n_cpu_psi10,
            "n_cpu_psi_slope": n_cpu_psi_slope,
            "n_mem_current_mb": n_mem_current,
            "n_mem_high_mb": n_mem_high,
            "n_mem_headroom_mb": (n_mem_high - n_mem_current) if (n_mem_high is not None and n_mem_current is not None) else None,
            "n_mem_events_high_per_s_30s": counter_rate(win30, ("cgroups", "wlp-neighbor", "memory_events", "high"), 1.0),
            "n_io_wbytes_mb_per_s_10s": counter_rate(win10, ("cgroups", "wlp-neighbor", "io_stat", "wbytes"), 1.0 / MB_DIVISOR),
            "n_pids": dig(neighbor, "pids_current"),
            "n_pids_delta_10s": counter_delta(win10, ("cgroups", "wlp-neighbor", "pids_current")),
            "n_psi_cpu_avg10": n_cpu_psi10,
            "n_psi_mem_some_avg10": dig(neighbor, "psi_memory_some", "avg10"),
            "n_psi_mem_full_avg10": dig(neighbor, "psi_memory_full", "avg10"),
            "n_psi_io_some_avg10": dig(neighbor, "psi_io_some", "avg10"),
            "c_cpu_throttled_us_per_s_10s": counter_rate(win10, ("cgroups", "wlp-critical", "cpu_stat", "throttled_usec"), 1.0),
            "c_mem_current_mb": dig(critical, "memory_current_mb"),
            "c_psi_cpu_avg10": c_cpu_psi10,
            "c_psi_mem_full_avg10": dig(critical, "psi_memory_full", "avg10"),
            "v_p95_ms_10s": v_p95,
            "v_p95_ratio_10s": v_p95_ratio,
            "v_rate_ratio_10s": v_rate_ratio,
            "sys_psi_cpu_avg10": sys_psi_cpu10,
            "sys_psi_cpu_slope": sys_psi_cpu_slope,
            "sys_psi_mem_some_avg10": dig(system, "psi_memory_some", "avg10"),
            "sys_psi_io_some_avg10": dig(system, "psi_io_some", "avg10"),
            "sys_load1": (dig(system, "loadavg") or [None])[0],
            "prev_action": prev["action"] if prev else None,
            "seconds_since_prev_action": (ts - parse_ts(prev["ts"])) if prev else None,
        }
    )
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description="featurize controller decisions (dataset-v2)")
    parser.add_argument("--run-dir", required=True, help="run directory with scenario/telemetry/decisions/victim files")
    args = parser.parse_args()
    run_dir: str = args.run_dir

    scenario = read_json(os.path.join(run_dir, "scenario.json"))
    decisions = read_jsonl(os.path.join(run_dir, "decisions.jsonl"))
    telemetry = time_index(read_jsonl(os.path.join(run_dir, "telemetry.jsonl")))
    victim = time_index(read_jsonl(os.path.join(run_dir, "victim.log")))
    victim_type: str = scenario["victim_type"]
    seed = scenario["seed"]

    kept: list[dict[str, Any]] = []
    quiet_kept = 0
    dropped = 0
    prev: dict[str, Any] | None = None
    for decision in decisions:
        quiet = is_quiet(decision)
        if quiet and quiet_kept >= QUIET_CAP:
            dropped += 1
        else:
            if quiet:
                quiet_kept += 1
            kept.append(build_row(decision, prev, telemetry, victim, victim_type, seed, quiet))
        prev = decision

    out_path = os.path.join(run_dir, "rows.jsonl")
    with open(out_path, "w", encoding="utf-8") as handle:
        for row in kept:
            handle.write(json.dumps(row) + "\n")

    print(f"featurize: {out_path}")
    print(f"seed={seed} victim_type={victim_type} decisions={len(decisions)} rows_kept={len(kept)} quiet_dropped={dropped} (cap {QUIET_CAP})")
    for key in FEATURE_KEYS:
        nulls = sum(1 for row in kept if row[key] is None)
        print(f"  null {key}: {nulls}/{len(kept)}")


if __name__ == "__main__":
    main()
