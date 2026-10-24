#!/usr/bin/env python3
"""M1 glue loop: watch telemetry.jsonl, ask rules.decide(prev, cur), act via actuator.py, log decisions.jsonl.

Run inside the lab: python3 /root/workloadpilot/teacher_loop.py
Stops on SIGTERM/SIGINT (default handlers kill the process; the decision log is line-buffered).
"""
import argparse
import json
import subprocess
import sys
import time

import rules

DEFAULT_TELEMETRY = "/root/workloadpilot/out/telemetry.jsonl"
DEFAULT_DECISIONS = "/root/workloadpilot/out/decisions.jsonl"
ACTUATOR = "/root/workloadpilot/actuator.py"
COOLDOWN_SECONDS = 60.0
POLL_SECONDS = 2.0
ACTUATOR_TIMEOUT = 30


def read_new_rows(path, consumed):
    """Return (new_rows, new_consumed_count) for lines after `consumed`."""
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


def apply_action(decision):
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


def main():
    parser = argparse.ArgumentParser(description="WorkloadPilot M1 teacher glue loop")
    parser.add_argument("--telemetry", default=DEFAULT_TELEMETRY)
    parser.add_argument("--decisions", default=DEFAULT_DECISIONS)
    parser.add_argument("--cooldown", type=float, default=COOLDOWN_SECONDS)
    args = parser.parse_args()

    consumed = 0
    prev = None
    last_applied = {}  # (action, target) -> monotonic time of last actual application
    decision_log = open(args.decisions, "a", buffering=1)
    print("teacher loop running", flush=True)

    while True:
        rows, consumed = read_new_rows(args.telemetry, consumed)
        for cur in rows:
            if prev is None:
                prev = cur
                continue
            try:
                decision = rules.decide(prev, cur)
            except Exception as exc:  # noqa: BLE001 - never die on a rules bug
                decision = {
                    "action": "do_nothing",
                    "target": None,
                    "reason": "rules error: {}".format(exc),
                    "confidence": 0.5,
                }

            applied = False
            detail = ""
            action = decision["action"]
            key = (action, decision.get("target"))
            if action == "do_nothing":
                detail = "no-op"
            elif action == "alert_operator":
                detail = "alert logged"
            else:
                now = time.monotonic()
                if now - last_applied.get(key, 0.0) < args.cooldown:
                    detail = "cooldown: same action applied recently"
                else:
                    result = apply_action(decision)
                    applied = bool(result.get("applied"))
                    detail = result.get("detail", "") or result.get("reason", "")
                    if applied:
                        last_applied[key] = now

            record = {
                "ts": cur.get("ts"),
                "state": cur,
                "action": action,
                "target": decision.get("target"),
                "reason": decision.get("reason"),
                "applied": applied,
                "detail": detail,
            }
            decision_log.write(json.dumps(record) + "\n")
            prev = cur

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
