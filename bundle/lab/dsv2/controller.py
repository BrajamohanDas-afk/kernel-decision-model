#!/usr/bin/env python3
"""WorkloadPilot dataset-v2 controller: watch telemetry.jsonl, decide, act, log decisions.

Feeds consecutive telemetry rows to rules.decide, optionally explores on non-quiet states
(explore mode), applies the chosen action via actuator.py, and appends one decisions.jsonl
record per new telemetry row. The very first row is dropped: it has no previous state.

Usage:
  python3 controller.py --run-dir DIR --mode rules|explore [--explore-prob 0.3]
                        [--cooldown 45] [--seed 1234] [--dry-run] [--source FILE] [--poll 2]

Stops cleanly on SIGTERM/SIGINT; decisions.jsonl is line-buffered. Stdlib only.
"""
import argparse
import json
import os
import random
import signal
import subprocess
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import rules  # noqa: E402 - PROJECT_ROOT added above so sibling rules.py imports

ACTUATOR = os.path.join(PROJECT_ROOT, "actuator.py")
ACTUATOR_TIMEOUT = 30
UNIT_NEIGHBOR = "wlp-neighbor"
EXPLORE_WEIGHTS = {
    "increase_cpu": 1,
    "decrease_cpu": 1,
    "increase_memory": 3,
    "decrease_memory": 1,
    "throttle_io": 1,
    "restrict_process_count": 2,
    "protect_service": 2,
}


def read_new_rows(path, consumed):
    """Return (new_rows, new_consumed_count) for lines after `consumed`.

    shortcut: `consumed` counts lines, not bytes; a telemetry file truncated mid-run
    stalls until it regrows past that count, fine for run-scoped files.
    """
    try:
        with open(path) as handle:
            lines = handle.readlines()
    except FileNotFoundError:
        return [], consumed
    rows = []
    for line in lines[consumed:]:
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows, len(lines)


def rules_decision(prev, cur):
    """rules.decide with a tolerant fallback; never raises."""
    try:
        return rules.decide(prev, cur)
    except Exception as exc:  # noqa: BLE001 - never die on a rules bug
        return {
            "action": "do_nothing",
            "target": None,
            "reason": "rules error: {}".format(exc),
            "confidence": 0.5,
        }


def in_cooldown(key, last_applied, now, cooldown):
    """True when key=(action, target) was actually applied within the cooldown window."""
    return now - last_applied.get(key, 0.0) < cooldown


def explore_pick(rng):
    """Weighted draw from the explore action table; returns (action, target)."""
    action = rng.choices(tuple(EXPLORE_WEIGHTS), weights=tuple(EXPLORE_WEIGHTS.values()), k=1)[0]
    target = "both" if action == "protect_service" else UNIT_NEIGHBOR
    return action, target


def choose_decision(prev, cur, mode, explore_prob, cooldown, last_applied, rng):
    """Return (decision, exploration). Explore only on non-quiet states; else rules."""
    if mode == "explore":
        cgroups = cur.get("cgroups")
        quiet = not isinstance(cgroups, dict) or cgroups.get(UNIT_NEIGHBOR) is None
        if not quiet and rng.random() < explore_prob:
            action, target = explore_pick(rng)
            if not in_cooldown((action, target), last_applied, time.monotonic(), cooldown):
                return {"action": action, "target": target, "reason": "explore: " + action}, True
    return rules_decision(prev, cur), False


def call_actuator(decision):
    """Call actuator.py in stdin-JSON mode; return its result dict (never raises)."""
    payload = json.dumps({"action": decision["action"], "target": decision.get("target")})
    try:
        out = subprocess.run(
            [sys.executable, ACTUATOR],
            input=payload,
            capture_output=True,
            text=True,
            timeout=ACTUATOR_TIMEOUT,
        )
        last = out.stdout.strip().splitlines()[-1]
        return json.loads(last)
    except Exception as exc:  # noqa: BLE001 - glue must survive actuator failures
        return {"applied": False, "detail": "actuator error: {}".format(exc)}


def apply_decision(decision, last_applied, cooldown, dry_run):
    """Apply one chosen decision; return (applied, detail). Never raises."""
    action = decision.get("action")
    key = (action, decision.get("target"))
    if action == "do_nothing":
        return False, "no-op"
    if action == "alert_operator":
        return False, "alert logged"
    if dry_run:
        return False, "dry-run"
    now = time.monotonic()
    if in_cooldown(key, last_applied, now, cooldown):
        return False, "cooldown: same action applied recently"
    result = call_actuator(decision)
    applied = bool(result.get("applied"))
    detail = result.get("detail") or result.get("reason") or ""
    if applied:
        last_applied[key] = now
    return applied, detail


def main():
    parser = argparse.ArgumentParser(description="WorkloadPilot dataset-v2 controller")
    parser.add_argument("--run-dir", required=True, help="run directory (telemetry + decisions)")
    parser.add_argument("--mode", choices=("rules", "explore"), required=True)
    parser.add_argument("--explore-prob", type=float, default=0.3)
    parser.add_argument("--cooldown", type=float, default=45.0)
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--dry-run", action="store_true", help="never call the actuator")
    parser.add_argument("--source", default=None, help="telemetry file (default: run-dir/telemetry.jsonl)")
    parser.add_argument("--poll", type=float, default=2.0)
    args = parser.parse_args()

    source = args.source or os.path.join(args.run_dir, "telemetry.jsonl")
    decisions_path = os.path.join(args.run_dir, "decisions.jsonl")
    rng = random.Random(args.seed)
    stop = False

    def _on_stop(signum, frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _on_stop)
    signal.signal(signal.SIGTERM, _on_stop)

    consumed = 0
    prev = None
    last_applied = {}  # (action, target) -> monotonic time of last actual application
    decision_log = open(decisions_path, "a", buffering=1)
    print(
        "controller running mode={} dry_run={} source={} decisions={}".format(
            args.mode, args.dry_run, source, decisions_path
        ),
        flush=True,
    )
    try:
        while not stop:
            rows, consumed = read_new_rows(source, consumed)
            for cur in rows:
                if prev is None:
                    prev = cur
                    continue
                try:
                    decision, exploration = choose_decision(
                        prev, cur, args.mode, args.explore_prob, args.cooldown, last_applied, rng
                    )
                    applied, detail = apply_decision(
                        decision, last_applied, args.cooldown, args.dry_run
                    )
                except Exception as exc:  # noqa: BLE001 - one bad row must not kill the loop
                    decision = {
                        "action": "do_nothing",
                        "target": None,
                        "reason": "controller error: {}".format(exc),
                    }
                    exploration, applied, detail = False, False, "controller error"
                record = {
                    "ts": cur.get("ts"),
                    "state": cur,
                    "action": decision.get("action"),
                    "target": decision.get("target"),
                    "reason": decision.get("reason"),
                    "applied": applied,
                    "detail": detail,
                    "mode": args.mode,
                    "exploration": exploration,
                }
                decision_log.write(json.dumps(record) + "\n")
                prev = cur
            if not stop:
                time.sleep(args.poll)
    finally:
        decision_log.close()
        print("controller stopped", flush=True)


if __name__ == "__main__":
    main()
