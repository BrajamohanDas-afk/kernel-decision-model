#!/usr/bin/env python3
"""WorkloadPilot dataset-v2 latency victim: fixed-cadence 5ms-work / 20ms-loop app.

Per iteration it burns --work-ms of CPU, sleeps out the remaining cadence and
appends one JSONL row {"ts": ISO8601Z, "latency_us": wake-up overshoot in us}.
SIGTERM/SIGINT exit cleanly.
"""

import argparse
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Any

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
    parser = argparse.ArgumentParser(description="Fixed-cadence latency victim.")
    parser.add_argument("--out", required=True, help="JSONL output path")
    parser.add_argument("--cadence-ms", type=float, default=20.0)
    parser.add_argument("--work-ms", type=float, default=5.0)
    args = parser.parse_args()
    if args.cadence_ms <= 0 or args.work_ms <= 0:
        parser.error("--cadence-ms and --work-ms must be > 0")

    signal.signal(signal.SIGTERM, _on_stop)
    signal.signal(signal.SIGINT, _on_stop)

    cadence_s = args.cadence_ms / 1000.0
    work_s = args.work_ms / 1000.0
    with open(args.out, "w", encoding="utf-8") as out:
        while not _stop:
            started = time.perf_counter()
            burn_cpu(work_s)
            deadline = started + cadence_s
            sleep_until(deadline)
            overshoot_us = max(0, int((time.perf_counter() - deadline) * 1e6))
            out.write(json.dumps({"ts": now_iso(), "latency_us": overshoot_us}) + "\n")
            out.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
