#!/usr/bin/env python3
"""Latency-sensitive app: ~20ms cadence, ~5ms CPU burn, one latency line per iteration.

Latency = how late the iteration woke past its intended 20ms tick, in microseconds.
It is measured per iteration (no cumulative drift), so it drops back after a load phase.
"""
import signal
import sys
import time
from datetime import datetime, timezone

LOG_PATH = "/root/workloadpilot/out/critical_latency.log"
TICK_SECONDS = 0.020
BURN_SECONDS = 0.005

_running = True


def _utc_timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _on_stop(signum, frame):
    global _running
    _running = False


def _burn_for(burn_seconds):
    spin = 0
    deadline = time.perf_counter() + burn_seconds
    while time.perf_counter() < deadline:
        spin += 1
    return spin


def main():
    global _running
    signal.signal(signal.SIGTERM, _on_stop)
    signal.signal(signal.SIGINT, _on_stop)
    _running = True
    while _running:
        tick_start = time.perf_counter()
        _burn_for(BURN_SECONDS)
        tick_target = tick_start + TICK_SECONDS
        now = time.perf_counter()
        if now < tick_target:
            time.sleep(tick_target - now)
            now = time.perf_counter()
        latency_us = int((now - tick_target) * 1000000.0)
        if latency_us < 0:
            latency_us = 0
        with open(LOG_PATH, "a", buffering=1) as log:
            log.write("%s %d\n" % (_utc_timestamp(), latency_us))
            log.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
