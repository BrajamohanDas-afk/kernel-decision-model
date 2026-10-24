#!/usr/bin/env python3
"""WorkloadPilot dataset-v2 throughput victim: processes ~8ms items at a target rate.

Once per second it appends one JSONL row
{"ts": ISO8601Z, "achieved_per_s": actual, "target_per_s": target}.
SIGTERM/SIGINT exit cleanly.
"""

import argparse
import json
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Any

ITEM_WORK_S = 0.008
REPORT_S = 1.0

_stop = False


def _on_stop(signum: int, frame: Any) -> None:
    global _stop
    _stop = True


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def burn_cpu(seconds: float) -> None:
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        pass


def sleep_until(deadline: float) -> None:
    while not _stop:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.05))


def main() -> int:
    parser = argparse.ArgumentParser(description="Paced throughput victim.")
    parser.add_argument("--out", required=True, help="JSONL output path")
    parser.add_argument("--target-per-s", type=float, default=50.0)
    args = parser.parse_args()
    if args.target_per_s <= 0:
        parser.error("--target-per-s must be > 0")

    signal.signal(signal.SIGTERM, _on_stop)
    signal.signal(signal.SIGINT, _on_stop)

    period_s = 1.0 / args.target_per_s
    next_item = time.perf_counter()
    window_start = time.perf_counter()
    completed = 0
    with open(args.out, "w", encoding="utf-8") as out:
        while not _stop:
            burn_cpu(ITEM_WORK_S)
            completed += 1
            now = time.perf_counter()
            if now < next_item:
                sleep_until(next_item)
            # Never chase a schedule we already missed: re-anchor to now.
            next_item = max(next_item + period_s, time.perf_counter())
            now = time.perf_counter()
            if now - window_start >= REPORT_S:
                out.write(
                    json.dumps(
                        {
                            "ts": now_iso(),
                            "achieved_per_s": completed,
                            "target_per_s": args.target_per_s,
                        }
                    )
                    + "\n"
                )
                out.flush()
                completed = 0
                window_start = now
    return 0


if __name__ == "__main__":
    sys.exit(main())
