#!/usr/bin/env python3
"""WorkloadPilot M1 dataset builder: teacher decisions + telemetry -> the platform training rows.

Usage:
  python3 build_dataset.py --dir /root/workloadpilot/out [--holdout-frac 0.2]

Reads from --dir:
  decisions.jsonl  teacher loop output, one JSON object per line (may be absent
                   while the loop is still warming up)
  telemetry.jsonl  sampler snapshots, one JSON object per line, 2 s cadence
  phases.log       optional "ISO8601Z name" phase markers

Writes back into --dir:
  decision_train.jsonl / decision_heldout.jsonl  the platform decision rows (chronological
      split: the last round(n * holdout_frac) decisions go to heldout)
  outcomes.jsonl   one 90 s outcome window per decision

Bad JSON lines, unknown actions and malformed states are skipped with a warning
on stderr instead of crashing the glue loop.
"""

import argparse
import json
import sys
from bisect import bisect_right
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

OUTCOME_WINDOW_S = 90
MB_DIVISOR = 1024.0 * 1024.0

# Verbatim M1 action taxonomy for the platform choice question.
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

QUESTION: dict[str, dict[str, Any]] = {
    "action": {
        "type": "choice",
        "instructions": "Which resource action should the controller take for the workloads right now?",
        "criteria": ACTION_CRITERIA,
    }
}


def dig(obj: Any, *keys: str) -> Any:
    """Read obj[key1][key2]... returning None as soon as the path is missing."""
    for key in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def parse_ts(text: Any) -> datetime:
    """Parse an ISO8601 UTC timestamp ("...Z", ms precision); raises ValueError otherwise."""
    if not isinstance(text, str):
        raise ValueError(f"timestamp is not a string: {text!r}")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def load_jsonl(path: Path) -> tuple[list[dict[str, Any]], int]:
    """Load JSONL rows; malformed/non-object lines are skipped with a warning.

    Returns (rows, skipped_line_count). A missing file warns and yields ([], 0).
    """
    if not path.exists():
        print(f"WARNING: {path} not found", file=sys.stderr)
        return [], 0
    rows: list[dict[str, Any]] = []
    skipped = 0
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"WARNING: {path.name}:{lineno}: invalid JSON, skipped ({exc})", file=sys.stderr)
            skipped += 1
            continue
        if not isinstance(row, dict):
            print(f"WARNING: {path.name}:{lineno}: not a JSON object, skipped", file=sys.stderr)
            skipped += 1
            continue
        rows.append(row)
    return rows, skipped


def load_telemetry(path: Path) -> tuple[list[datetime], list[dict[str, Any]]]:
    """Load sampler rows sorted by timestamp as parallel (timestamps, rows) lists."""
    raw, skipped = load_jsonl(path)
    pairs: list[tuple[datetime, dict[str, Any]]] = []
    for row in raw:
        try:
            pairs.append((parse_ts(row.get("ts")), row))
        except ValueError as exc:
            print(f"WARNING: {path.name}: bad telemetry ts, row skipped ({exc})", file=sys.stderr)
            skipped += 1
    pairs.sort(key=lambda pair: pair[0])
    return [pair[0] for pair in pairs], [pair[1] for pair in pairs]


def load_decisions(path: Path) -> tuple[list[tuple[datetime, dict[str, Any]]], int]:
    """Load and validate teacher decisions, sorted chronologically (stable).

    A row is dropped (with a warning) when ts is unparseable, action is not one
    of the 12 taxonomy names, or state is not a sampler-row object.
    """
    raw, skipped = load_jsonl(path)
    valid: list[tuple[datetime, dict[str, Any]]] = []
    for row in raw:
        issues: list[str] = []
        decision_dt: datetime | None = None
        try:
            decision_dt = parse_ts(row.get("ts"))
        except ValueError as exc:
            issues.append(f"bad ts ({exc})")
        action = row.get("action")
        if action not in ACTION_CRITERIA:
            issues.append(f"unknown action {action!r}")
        state = row.get("state")
        if not isinstance(state, dict) or ("cgroups" not in state and "system" not in state):
            issues.append("state is not a sampler row")
        if issues:
            print(f"WARNING: {path.name}: decision skipped: {'; '.join(issues)}", file=sys.stderr)
            skipped += 1
            continue
        assert decision_dt is not None
        valid.append((decision_dt, row))
    valid.sort(key=lambda pair: pair[0])
    return valid, skipped


def load_phases(path: Path) -> list[tuple[str, str]]:
    """Read optional phases.log markers as (ts, name); malformed lines are ignored."""
    if not path.exists():
        return []
    phases: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2:
            phases.append((parts[0], parts[1]))
    return phases


def _bytes_to_mb(value: Any) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return round(value / MB_DIVISOR, 2)


def _cpu_max_cores(text: Any) -> float | None:
    """cpu.max "quota period" -> cores; "max" (no quota) and junk -> None."""
    if not isinstance(text, str):
        return None
    parts = text.split()
    if len(parts) != 2 or parts[0] == "max":
        return None
    try:
        return round(int(parts[0]) / int(parts[1]), 2)
    except ValueError:
        return None


def compact_state(row: dict[str, Any]) -> dict[str, Any]:
    """Compact, low-noise snapshot of one sampler row for the platform state.

    Computable from a single sampler snapshot - exactly what an online policy
    sees at decision time, so no lookahead. 15 numeric fields, missing sources
    stay null. Prefixes: n_ = noisy neighbor cgroup, c_ = critical service
    cgroup, sys_ = system-wide. kernel counters (throttled_usec, wbytes, events
    high) are cumulative; *_psi_avg10 fields are the 10 s recent-stall rates
    that capture "what is hurting right now".
    shortcut: cumulative counters embed run age, so cross-run comparability is
    weak; upgrade to windowed rates if offenders appear in the platform error analysis.
    """
    neighbor = dig(row, "cgroups", "wlp-neighbor") or {}
    critical = dig(row, "cgroups", "wlp-critical") or {}
    system = dig(row, "system") or {}
    loadavg = dig(system, "loadavg")
    return {
        "n_cpu_max_cores": _cpu_max_cores(dig(neighbor, "cpu_max")),
        "n_cpu_throttled_usec": dig(neighbor, "cpu_stat", "throttled_usec"),
        "n_cpu_psi_avg10": dig(neighbor, "psi_cpu_some", "avg10"),
        "n_mem_current_mb": dig(neighbor, "memory_current_mb"),
        "n_mem_high_mb": dig(neighbor, "memory_high_mb"),
        "n_mem_events_high": dig(neighbor, "memory_events", "high"),
        "n_io_wbytes_mb": _bytes_to_mb(dig(neighbor, "io_stat", "wbytes")),
        "n_pids": dig(neighbor, "pids_current"),
        "c_cpu_throttled_usec": dig(critical, "cpu_stat", "throttled_usec"),
        "c_mem_current_mb": dig(critical, "memory_current_mb"),
        "c_psi_cpu_avg10": dig(critical, "psi_cpu_some", "avg10"),
        "sys_psi_cpu_avg10": dig(system, "psi_cpu_some", "avg10"),
        "sys_psi_mem_avg10": dig(system, "psi_memory_some", "avg10"),
        "sys_psi_io_avg10": dig(system, "psi_io_some", "avg10"),
        "sys_load1": loadavg[0] if isinstance(loadavg, list) and loadavg else None,
    }


def _num_delta(end_row: dict[str, Any], base_row: dict[str, Any] | None, keys: tuple[str, ...]) -> float | None:
    """end[keys] - base[keys], or None when either side is missing/not numeric."""
    if base_row is None:
        return None
    end_value = dig(end_row, *keys)
    base_value = dig(base_row, *keys)
    if not isinstance(end_value, (int, float)) or isinstance(end_value, bool):
        return None
    if not isinstance(base_value, (int, float)) or isinstance(base_value, bool):
        return None
    return end_value - base_value


def _empty_outcome() -> dict[str, Any]:
    return {
        "window_s": None,
        "neighbor_throttled_usec_delta": None,
        "neighbor_memory_current_mb_end": None,
        "neighbor_events_high_delta": None,
        "neighbor_wbytes_mb_delta": None,
        "system_psi_cpu_end": None,
        "system_psi_mem_end": None,
        "system_psi_io_end": None,
    }


def compute_outcome(
    decision_dt: datetime,
    telemetry_ts: list[datetime],
    telemetry_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """What happened in the 90 s after a decision (uses only later telemetry).

    Window = rows with ts in (decision_dt, decision_dt + 90 s]. Deltas compare
    the last window row with the closest row at or before the decision
    (the decision's own base snapshot). window_s is the observed span between
    base and window end, so the deltas are stated per real seconds observed.
    shortcut: counter deltas assume the cgroup survived the window; if a
    restart/kill recreated it the counters reset and a delta can go negative.
    """
    end_index = bisect_right(telemetry_ts, decision_dt + timedelta(seconds=OUTCOME_WINDOW_S)) - 1
    start_index = bisect_right(telemetry_ts, decision_dt)
    base_index = start_index - 1
    if end_index < start_index or end_index < 0:
        return _empty_outcome()
    end_row = telemetry_rows[end_index]
    base_row = telemetry_rows[base_index] if base_index >= 0 else None
    window_s = (
        round((telemetry_ts[end_index] - telemetry_ts[base_index]).total_seconds())
        if base_row is not None
        else None
    )
    wbytes_delta = _num_delta(end_row, base_row, ("cgroups", "wlp-neighbor", "io_stat", "wbytes"))
    return {
        "window_s": window_s,
        "neighbor_throttled_usec_delta": _num_delta(
            end_row, base_row, ("cgroups", "wlp-neighbor", "cpu_stat", "throttled_usec")
        ),
        "neighbor_memory_current_mb_end": dig(end_row, "cgroups", "wlp-neighbor", "memory_current_mb"),
        "neighbor_events_high_delta": _num_delta(
            end_row, base_row, ("cgroups", "wlp-neighbor", "memory_events", "high")
        ),
        "neighbor_wbytes_mb_delta": None if wbytes_delta is None else round(wbytes_delta / MB_DIVISOR, 2),
        "system_psi_cpu_end": dig(end_row, "system", "psi_cpu_some", "avg10"),
        "system_psi_mem_end": dig(end_row, "system", "psi_memory_some", "avg10"),
        "system_psi_io_end": dig(end_row, "system", "psi_io_some", "avg10"),
    }


def decision_row(decision: dict[str, Any], ordinal: int) -> dict[str, Any]:
    """One the platform training row: compact state + 12-way action question + teacher label."""
    return {
        "id": f"{decision['ts']}-{ordinal}",
        "state": compact_state(decision["state"]),
        "questions": QUESTION,
        "labels": {"action": decision["action"]},
        "weight": 1.0,
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write rows compactly, one JSON object per line."""
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")


def _mean_text(values: list[float]) -> str:
    if not values:
        return "n/a"
    return f"n={len(values)} mean={sum(values) / len(values):.3f}"


def print_summary(
    dir_path: Path,
    decisions: list[tuple[datetime, dict[str, Any]]],
    outcome_rows: list[dict[str, Any]],
    n_skipped: int,
    n_train: int,
    n_holdout: int,
    holdout_frac: float,
    phases: list[tuple[str, str]],
) -> None:
    """Print decision counts, the split and a tiny per-action outcome digest."""
    action_counts: dict[str, int] = {}
    for _, decision in decisions:
        action_counts[decision["action"]] = action_counts.get(decision["action"], 0) + 1
    applied = sum(1 for row in outcome_rows if row["applied"])
    windows = sum(1 for row in outcome_rows if row["outcome"]["window_s"] is not None)

    by_action: dict[str, list[dict[str, Any]]] = {}
    for row in outcome_rows:
        by_action.setdefault(row["action"], []).append(row["outcome"])

    def collect(actions: tuple[str, ...], key: str) -> list[float]:
        return [
            outcome[key]
            for action in actions
            for outcome in by_action.get(action, [])
            if outcome[key] is not None
        ]

    print("=== WorkloadPilot dataset build ===")
    print(f"dir: {dir_path}")
    print(f"decisions: {len(decisions)} valid, {n_skipped} lines skipped")
    counts = " | ".join(f"{name} {count}" for name, count in action_counts.items() if count > 0)
    print(f"actions: {counts}")
    print(f"applied: {applied}  refused: {len(decisions) - applied}")
    print(f"split: train {n_train}, heldout {n_holdout} (holdout-frac {holdout_frac})")
    print(f"outcomes: {len(outcome_rows)} written, windows observed {windows}/{len(outcome_rows)}")
    print("digest:")
    print(f"  neighbor_throttled_usec_delta  increase_cpu+protect_service: {_mean_text(collect(('increase_cpu', 'protect_service'), 'neighbor_throttled_usec_delta'))}")
    print(f"  system_psi_io_end              throttle_io:                  {_mean_text(collect(('throttle_io',), 'system_psi_io_end'))}")
    print(f"  neighbor_memory_current_mb_end increase_memory+decrease_memory: {_mean_text(collect(('increase_memory', 'decrease_memory'), 'neighbor_memory_current_mb_end'))}")
    if phases:
        names = ", ".join(name for _, name in phases)
        print(f"phases.log: {len(phases)} phases ({names})")
    else:
        print("phases.log: not found")


def build(dir_path: Path, holdout_frac: float) -> None:
    """Run one dataset build over dir_path, write the three outputs, print the summary."""
    if not dir_path.is_dir():
        raise FileNotFoundError(f"--dir is not a directory: {dir_path}")
    telemetry_ts, telemetry_rows = load_telemetry(dir_path / "telemetry.jsonl")
    decisions, n_skipped = load_decisions(dir_path / "decisions.jsonl")

    n_total = len(decisions)
    n_holdout = min(n_total, int(n_total * holdout_frac + 0.5))
    n_train = n_total - n_holdout

    train_rows: list[dict[str, Any]] = []
    heldout_rows: list[dict[str, Any]] = []
    outcome_rows: list[dict[str, Any]] = []
    for ordinal, (decision_dt, decision) in enumerate(decisions):
        outcome_rows.append(
            {
                "ts": decision["ts"],
                "action": decision["action"],
                "applied": bool(decision.get("applied")),
                "outcome": compute_outcome(decision_dt, telemetry_ts, telemetry_rows),
            }
        )
        row = decision_row(decision, ordinal + 1)
        (heldout_rows if ordinal >= n_train else train_rows).append(row)

    write_jsonl(dir_path / "decision_train.jsonl", train_rows)
    write_jsonl(dir_path / "decision_heldout.jsonl", heldout_rows)
    write_jsonl(dir_path / "outcomes.jsonl", outcome_rows)

    print_summary(
        dir_path,
        decisions,
        outcome_rows,
        n_skipped,
        n_train,
        n_holdout,
        holdout_frac,
        load_phases(dir_path / "phases.log"),
    )
    print(f"wrote: {dir_path / 'decision_train.jsonl'} ({len(train_rows)}), "
          f"{dir_path / 'decision_heldout.jsonl'} ({len(heldout_rows)}), "
          f"{dir_path / 'outcomes.jsonl'} ({len(outcome_rows)})")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the platform training rows from teacher decisions + telemetry.")
    parser.add_argument("--dir", required=True, help="directory holding decisions.jsonl / telemetry.jsonl / phases.log")
    parser.add_argument("--holdout-frac", type=float, default=0.2, help="fraction of (chronologically last) decisions to hold out")
    args = parser.parse_args()
    if not 0.0 <= args.holdout_frac <= 1.0:
        raise SystemExit(f"--holdout-frac must be within [0, 1], got {args.holdout_frac}")
    try:
        build(Path(args.dir), args.holdout_frac)
    except FileNotFoundError as exc:
        # clean one-line error: a traceback here makes Ubuntu's apport hook import
        # /root/workloadpilot/inspect.py (stdlib shadow) and spew noise.
        raise SystemExit(str(exc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
