#!/usr/bin/env python3
"""Bad-neighbor stressor: run ONE resource-conflicting phase for a fixed duration, then release it."""
import argparse
import os
import signal
import subprocess
import sys
import time

OUT_DIR = "/root/workloadpilot/out"
IOFILE_PATH = os.path.join(OUT_DIR, "iofile")
CPU_WORKERS = 3
BUSY_LOOP_CODE = "while True: pass"
MEM_BYTES = 200 * 1024 * 1024
PAGE_BYTES = 4096
IO_CHUNK_BYTES = 1024 * 1024
IO_CAP_BYTES = 250 * 1024 * 1024
POLL_SECONDS = 0.1

_stop = False


def _on_stop(signum, frame):
    # Flag-only handler: raising here would fire during interpreter shutdown and print a traceback.
    global _stop
    _stop = True


def _sleep_until(deadline):
    while not _stop:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(POLL_SECONDS, remaining))


def _run_cpu(duration_seconds):
    workers = []
    try:
        for _ in range(CPU_WORKERS):
            workers.append(subprocess.Popen([sys.executable, "-c", BUSY_LOOP_CODE]))
        _sleep_until(time.monotonic() + duration_seconds)
    finally:
        for worker in workers:
            worker.terminate()
        for worker in workers:
            try:
                worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait()
    return "workers=%d" % (len(workers),)


def _run_mem(duration_seconds):
    buffer = bytearray(MEM_BYTES)
    try:
        for offset in range(0, MEM_BYTES, PAGE_BYTES):
            buffer[offset] = 1
        _sleep_until(time.monotonic() + duration_seconds)
    finally:
        del buffer
    return "resident_mb=%d" % (MEM_BYTES // (1024 * 1024),)


def _run_io(duration_seconds):
    # Writes are paced so the ~250MB cap is spread over the whole phase instead of
    # burning through it in the first seconds of a 90s phase.
    start = time.monotonic()
    deadline = start + duration_seconds
    bytes_per_second = IO_CAP_BYTES / duration_seconds
    chunk = b"x" * IO_CHUNK_BYTES
    written = 0
    try:
        while not _stop and time.monotonic() < deadline and written < IO_CAP_BYTES:
            with open(IOFILE_PATH, "wb") as handle:
                handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            written += IO_CHUNK_BYTES
            _sleep_until(start + (written / bytes_per_second))
    finally:
        if os.path.exists(IOFILE_PATH):
            os.remove(IOFILE_PATH)
    return "written_mb=%d" % (written // (1024 * 1024),)


def main():
    parser = argparse.ArgumentParser(description="WorkloadPilot bad-neighbor stressor")
    parser.add_argument("--phase", choices=("cpu", "mem", "io"), required=True)
    parser.add_argument("--duration", type=float, required=True)
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, _on_stop)
    signal.signal(signal.SIGINT, _on_stop)

    print("NEIGHBOR START phase=%s duration=%gs pid=%d" % (args.phase, args.duration, os.getpid()), flush=True)
    started = time.monotonic()
    if args.phase == "cpu":
        detail = _run_cpu(args.duration)
    elif args.phase == "mem":
        detail = _run_mem(args.duration)
    else:
        detail = _run_io(args.duration)
    print("NEIGHBOR END phase=%s elapsed=%.1fs %s" % (args.phase, time.monotonic() - started, detail), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
