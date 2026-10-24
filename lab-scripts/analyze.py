#!/usr/bin/env python3
"""WorkloadPilot Milestone 0 analyzer.

Reads telemetry.jsonl, phases.log and critical_latency.log from --dir and prints
a readable per-phase report with PASS/WEAK/FAIL signal judgments.

Stdlib only. Missing files, missing fields and null cgroup blocks are reported
as N/A instead of crashing.
"""

import argparse
import bisect
import json
import math
import os
from datetime import datetime, timezone

PHASE_ORDER = ("baseline", "cpu_load", "mem_load", "io_load", "recovery")
NEIGHBOR = "wlp-neighbor"
BYTES_PER_MB = 1048576.0


def parse_ts(text):
    """Parse an ISO8601 timestamp; tolerate trailing Z and ms fractions."""
    if not isinstance(text, str):
        return None
    value = text.strip()
    if value.endswith("Z") or value.endswith("z"):
        value = value[:-1]
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    # Normalize to naive UTC so mixed inputs never make comparisons raise.
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def dig(obj, *keys):
    """Walk nested dicts, returning None as soon as a level is missing or null."""
    cur = obj
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def fmt(value, digits=2):
    if value is None:
        return "N/A"
    return format(value, "." + str(digits) + "f")


def read_jsonl(path):
    rows = []
    bad = 0
    present = os.path.isfile(path)
    if not present:
        return rows, bad, present
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                bad += 1
                continue
            if isinstance(obj, dict):
                rows.append(obj)
            else:
                bad += 1
    return rows, bad, present


def read_phases(path):
    phases = []
    if not os.path.isfile(path):
        return phases
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            parts = line.split()
            if len(parts) < 2:
                continue
            start = parse_ts(parts[0])
            if start is not None:
                phases.append({"name": parts[1], "start": start})
    phases.sort(key=lambda phase: phase["start"])
    return phases


def read_latency(path):
    """Return (ts, latency_ms) points from '<ISO8601> <latency_us>' lines."""
    points = []
    if not os.path.isfile(path):
        return points
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            parts = line.split()
            if len(parts) < 2:
                continue
            ts = parse_ts(parts[0])
            try:
                micros = float(parts[1])
            except ValueError:
                continue
            if ts is not None:
                points.append((ts, micros / 1000.0))
    points.sort(key=lambda point: point[0])
    return points


def bucket_items(items, phases):
    """Bucket (ts, payload) items by phase window; keeps the items intact."""
    starts = [phase["start"] for phase in phases]
    buckets = [[] for _ in phases]
    early = 0
    for item in items:
        index = bisect.bisect_right(starts, item[0]) - 1
        if index < 0:
            early += 1
        else:
            buckets[index].append(item)
    return buckets, early


def numeric_values(raws, extract):
    """Collect numeric (non-bool) values, skipping None and wrong types."""
    out = []
    for row in raws:
        value = extract(row)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        out.append(float(value))
    return out


def first_loadavg(row):
    load = dig(row, "system", "loadavg")
    if isinstance(load, list) and load:
        first = load[0]
        if isinstance(first, bool) or not isinstance(first, (int, float)):
            return None
        return float(first)
    return None


def mean(vals):
    if not vals:
        return None
    return sum(vals) / float(len(vals))


def percentile(vals, pct):
    """Nearest-rank percentile; good enough for a lab report."""
    if not vals:
        return None
    ordered = sorted(vals)
    rank = max(1, int(math.ceil(pct / 100.0 * len(ordered))))
    return ordered[min(rank, len(ordered)) - 1]


def counter_delta(vals):
    """Last minus first of a monotonic counter series; None when unavailable."""
    if not vals:
        return None
    return vals[-1] - vals[0]


def compute_stats(tele_items, lat_values):
    stats = {"n": len(tele_items)}
    timestamps = [ts for ts, _ in tele_items]
    stats["t_first"] = min(timestamps) if timestamps else None
    stats["t_last"] = max(timestamps) if timestamps else None
    if len(timestamps) > 1:
        stats["covered_s"] = (max(timestamps) - min(timestamps)).total_seconds()
    elif timestamps:
        stats["covered_s"] = 0.0
    else:
        stats["covered_s"] = None

    raws = [row for _, row in tele_items]
    stats["nb_rows"] = sum(1 for row in raws if dig(row, "cgroups", NEIGHBOR) is not None)
    stats["nb_null_rows"] = stats["n"] - stats["nb_rows"]

    stats["nb_throttled_d"] = counter_delta(numeric_values(
        raws, lambda row: dig(row, "cgroups", NEIGHBOR, "cpu_stat", "throttled_usec")))
    stats["nb_nr_throttled_d"] = counter_delta(numeric_values(
        raws, lambda row: dig(row, "cgroups", NEIGHBOR, "cpu_stat", "nr_throttled")))
    stats["nb_usage_d"] = counter_delta(numeric_values(
        raws, lambda row: dig(row, "cgroups", NEIGHBOR, "cpu_stat", "usage_usec")))
    stats["nb_mem_current_max"] = max(numeric_values(
        raws, lambda row: dig(row, "cgroups", NEIGHBOR, "memory_current_mb")), default=None)
    stats["nb_mem_high_d"] = counter_delta(numeric_values(
        raws, lambda row: dig(row, "cgroups", NEIGHBOR, "memory_events", "high")))
    stats["nb_oom_kill_d"] = counter_delta(numeric_values(
        raws, lambda row: dig(row, "cgroups", NEIGHBOR, "memory_events", "oom_kill")))

    wbytes_delta = counter_delta(numeric_values(
        raws, lambda row: dig(row, "cgroups", NEIGHBOR, "io_stat", "wbytes")))
    stats["nb_wbytes_d_mb"] = wbytes_delta / BYTES_PER_MB if wbytes_delta is not None else None

    mem_vals = numeric_values(raws, lambda row: dig(row, "system", "psi_memory_some", "avg10"))
    io_vals = numeric_values(raws, lambda row: dig(row, "system", "psi_io_some", "avg10"))
    cpu_vals = numeric_values(raws, lambda row: dig(row, "system", "psi_cpu_some", "avg10"))
    load_vals = numeric_values(raws, first_loadavg)
    avail_vals = numeric_values(raws, lambda row: dig(row, "system", "mem_available_mb"))

    stats["psi_mem_mean"] = mean(mem_vals)
    stats["psi_mem_max"] = max(mem_vals, default=None)
    stats["psi_mem_last"] = mem_vals[-1] if mem_vals else None
    stats["psi_io_mean"] = mean(io_vals)
    stats["psi_io_max"] = max(io_vals, default=None)
    stats["psi_io_last"] = io_vals[-1] if io_vals else None
    stats["psi_cpu_mean"] = mean(cpu_vals)
    stats["load1_mean"] = mean(load_vals)
    stats["mem_avail_min"] = min(avail_vals) if avail_vals else None

    stats["lat_n"] = len(lat_values)
    stats["lat_p50"] = percentile(lat_values, 50)
    stats["lat_p95"] = percentile(lat_values, 95)
    stats["lat_max"] = max(lat_values, default=None)
    return stats


def judge_phases(stats_by_name):
    """Per-phase PASS/WEAK/FAIL verdicts per the milestone signal contract."""
    signals = {}
    base = stats_by_name.get("baseline")

    if base is None:
        signals["baseline"] = ("SKIP", "no baseline phase data")
    else:
        quiet = base["n"] > 0 and base["nb_null_rows"] == base["n"]
        mem_ok = base["psi_mem_max"] is None or base["psi_mem_max"] < 0.5
        io_ok = base["psi_io_max"] is None or base["psi_io_max"] < 0.5
        if quiet and mem_ok and io_ok:
            verdict = "PASS"
        elif quiet:
            verdict = "WEAK"
        else:
            verdict = "FAIL"
        detail = (f"expected QUIET: neighbor null in {base['nb_null_rows']}/{base['n']} rows, "
                  f"psi_mem_some avg10 max {fmt(base['psi_mem_max'])} (<0.5 ok), "
                  f"psi_io_some avg10 max {fmt(base['psi_io_max'])} (<0.5 ok)")
        signals["baseline"] = (verdict, detail)

    st = stats_by_name.get("cpu_load")
    if st is None:
        signals["cpu_load"] = ("SKIP", "no cpu_load phase data")
    else:
        throttle_delta = st["nb_throttled_d"]
        cond_throttle = throttle_delta is not None and throttle_delta > 0
        p95 = st["lat_p95"]
        base_p95 = base["lat_p95"] if base is not None else None
        ratio = p95 / base_p95 if (p95 is not None and base_p95) else None
        cond_latency = ratio is not None and ratio >= 1.5
        if cond_throttle and cond_latency:
            verdict = "PASS"
        elif cond_throttle or cond_latency:
            verdict = "WEAK"
        else:
            verdict = "FAIL"
        ratio_text = f"{fmt(ratio)}x baseline p95" if ratio is not None else "N/A"
        detail = (f"neighbor throttled_usec d {fmt(throttle_delta, 0)} us (>0 needed); "
                  f"critical p95 {fmt(p95)} ms = {ratio_text} (>=1.5x needed)")
        signals["cpu_load"] = (verdict, detail)

    st = stats_by_name.get("mem_load")
    if st is None:
        signals["mem_load"] = ("SKIP", "no mem_load phase data")
    else:
        mem_current = st["nb_mem_current_max"]
        cond_mem = mem_current is not None and mem_current >= 150.0
        psi_mem = st["psi_mem_max"]
        cond_psi = psi_mem is not None and psi_mem >= 1.0
        if cond_mem and cond_psi:
            verdict = "PASS"
        elif cond_mem or cond_psi:
            verdict = "WEAK"
        else:
            verdict = "FAIL"
        detail = (f"neighbor mem_current max {fmt(mem_current, 1)} MB (>=150 needed); "
                  f"system psi_mem_some avg10 max {fmt(psi_mem)} (>=1.0 needed)")
        signals["mem_load"] = (verdict, detail)

    st = stats_by_name.get("io_load")
    if st is None:
        signals["io_load"] = ("SKIP", "no io_load phase data")
    else:
        wbytes = st["nb_wbytes_d_mb"]
        cond_w = wbytes is not None and wbytes >= 50.0
        psi_io = st["psi_io_max"]
        cond_io = psi_io is not None and psi_io >= 2.0
        verdict = "PASS" if (cond_w or cond_io) else "FAIL"
        detail = (f"neighbor wbytes d {fmt(wbytes)} MB (>=50 needed); "
                  f"system psi_io_some avg10 max {fmt(psi_io)} (>=2.0 needed)")
        signals["io_load"] = (verdict, detail)

    st = stats_by_name.get("recovery")
    if st is None:
        signals["recovery"] = ("SKIP", "no recovery phase data")
    else:
        base_mem = base["psi_mem_mean"] if base is not None else None
        base_io = base["psi_io_mean"] if base is not None else None
        limit_mem = max(2.0 * base_mem, 0.5) if base_mem is not None else 1.0
        limit_io = max(2.0 * base_io, 0.5) if base_io is not None else 1.0
        mem_ok = st["psi_mem_last"] is None or st["psi_mem_last"] <= limit_mem
        io_ok = st["psi_io_last"] is None or st["psi_io_last"] <= limit_io
        if mem_ok and io_ok:
            verdict = "PASS"
        elif mem_ok or io_ok:
            verdict = "WEAK"
        else:
            verdict = "FAIL"
        detail = (f"returned toward baseline (lenient): psi_mem_some avg10 last {fmt(st['psi_mem_last'])} "
                  f"vs baseline mean {fmt(base_mem)} (limit {fmt(limit_mem)}); "
                  f"psi_io_some avg10 last {fmt(st['psi_io_last'])} vs baseline mean {fmt(base_io)} "
                  f"(limit {fmt(limit_io)})")
        signals["recovery"] = (verdict, detail)

    for name in PHASE_ORDER:
        if name not in signals:
            signals[name] = ("SKIP", "phase missing")
    return signals


def print_stats_block(title, stats, phase_start):
    print(f"--- {title} ---")
    if phase_start is not None:
        print(f"  phase start: {phase_start.isoformat()}")
    covered = f"{fmt(stats['covered_s'], 1)} s" if stats["covered_s"] is not None else "N/A"
    print(f"  rows: {stats['n']}   covered: {covered}")
    if stats["lat_n"]:
        print(f"  critical latency (ms): p50 {fmt(stats['lat_p50'])}  p95 {fmt(stats['lat_p95'])}  "
              f"max {fmt(stats['lat_max'])}   (samples: {stats['lat_n']})")
    else:
        print("  critical latency (ms): N/A (no samples)")
    print(f"  neighbor: throttled_usec d {fmt(stats['nb_throttled_d'], 0)} us | "
          f"nr_throttled d {fmt(stats['nb_nr_throttled_d'], 0)} | "
          f"mem_current max {fmt(stats['nb_mem_current_max'], 1)} MB | "
          f"mem.high d {fmt(stats['nb_mem_high_d'], 0)} | "
          f"oom_kill d {fmt(stats['nb_oom_kill_d'], 0)} | "
          f"wbytes d {fmt(stats['nb_wbytes_d_mb'])} MB   "
          f"(block present in {stats['nb_rows']}/{stats['n']} rows)")
    print(f"  system: psi_mem_some avg10 mean/max {fmt(stats['psi_mem_mean'])}/{fmt(stats['psi_mem_max'])} | "
          f"psi_io_some avg10 mean/max {fmt(stats['psi_io_mean'])}/{fmt(stats['psi_io_max'])} | "
          f"psi_cpu_some avg10 mean {fmt(stats['psi_cpu_mean'])} | "
          f"loadavg[0] mean {fmt(stats['load1_mean'])} | "
          f"mem_available min {fmt(stats['mem_avail_min'], 1)} MB")


def main():
    parser = argparse.ArgumentParser(description="WorkloadPilot Milestone 0 analyzer")
    parser.add_argument("--dir", default="/root/workloadpilot/out",
                        help="directory containing telemetry.jsonl, phases.log and critical_latency.log")
    args = parser.parse_args()

    telemetry_path = os.path.join(args.dir, "telemetry.jsonl")
    phases_path = os.path.join(args.dir, "phases.log")
    latency_path = os.path.join(args.dir, "critical_latency.log")

    raw_rows, bad_lines, tele_present = read_jsonl(telemetry_path)
    phases = read_phases(phases_path)
    latency_points = read_latency(latency_path)

    tele_items = []
    bad_ts = 0
    for row in raw_rows:
        ts = parse_ts(row.get("ts"))
        if ts is None:
            bad_ts += 1
        else:
            tele_items.append((ts, row))

    print("WorkloadPilot Milestone 0 - analyzer report")
    print(f"dir: {os.path.abspath(args.dir)}")
    if tele_present:
        tele_line = f"telemetry.jsonl: {len(tele_items)} rows parsed"
        if bad_lines:
            tele_line += f" ({bad_lines} unparsable line(s) skipped)"
        if bad_ts:
            tele_line += f" ({bad_ts} row(s) without a usable ts skipped)"
    else:
        tele_line = "telemetry.jsonl: MISSING"
    print(tele_line)
    print("phases.log: " + ("MISSING" if not os.path.isfile(phases_path) else f"{len(phases)} phases"))
    print("critical_latency.log: " + ("MISSING" if not os.path.isfile(latency_path) else f"{len(latency_points)} samples"))

    if phases:
        tele_buckets, tele_early = bucket_items(tele_items, phases)
        lat_buckets, lat_early = bucket_items(latency_points, phases)
        if tele_early:
            print(f"({tele_early} telemetry row(s) before the first phase start were ignored)")
        blocks = []
        stats_by_name = {}
        for index, phase in enumerate(phases):
            stats = compute_stats(tele_buckets[index], [ms for _, ms in lat_buckets[index]])
            stats_by_name[phase["name"]] = stats
            blocks.append((phase["name"], stats, phase["start"]))
        signals = judge_phases(stats_by_name)
    else:
        stats = compute_stats(tele_items, [ms for _, ms in latency_points])
        blocks = [("all rows (phases.log missing)", stats, None)]
        signals = {name: ("SKIP", "no phases.log") for name in PHASE_ORDER}

    for name, stats, phase_start in blocks:
        print("")
        print_stats_block(name, stats, phase_start)
        if name in signals:
            verdict, detail = signals[name]
            print(f"  SIGNAL: {verdict} - {detail}")

    print("")
    print("SIGNAL CHECK")
    for name in PHASE_ORDER:
        verdict, detail = signals[name]
        print(f"  {name.ljust(9)} {verdict.ljust(4)}  {detail}")

    passed = sum(1 for name in PHASE_ORDER if signals[name][0] == "PASS")
    print("")
    print(f"OVERALL: {passed}/5 phases PASS")


if __name__ == "__main__":
    main()
