#!/usr/bin/env python3
"""WorkloadPilot dataset-v2 neighbor stressor: ONE invocation runs ONE load.

Variants: cpu_burn | mem_grow | io_write | fork_light | mixed.
SIGTERM/SIGINT set a stop flag; every pattern checks it and its finally block
releases children, memory and temp files.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from typing import Any

CPU_BURNER_CODE = "while True: pass"
SLEEP_BIN = "/usr/bin/sleep"
SLEEP_CHILD_S = "0.2"
IO_CHUNK_BYTES = 1024 * 1024
PAGE_BYTES = 4096
POLL_S = 0.05
RAMP_TICK_S = 0.02
SAWTOOTH_CYCLES = 4

_stop = False


class StopRequested(Exception):
    pass


def _on_stop(signum: int, frame: Any) -> None:
    global _stop
    _stop = True


def _sleep_until(deadline: float) -> None:
    while not _stop:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(POLL_S, remaining))


def _terminate(children: list[subprocess.Popen]) -> None:
    for child in children:
        child.terminate()
    for child in children:
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


def run_cpu_burn(procs: int, duration_s: float) -> str:
    workers: list[subprocess.Popen] = []
    try:
        for _ in range(procs):
            workers.append(subprocess.Popen([sys.executable, "-c", CPU_BURNER_CODE]))
        _sleep_until(time.monotonic() + duration_s)
    finally:
        _terminate(workers)
    return "procs=%d" % procs


def _touch(buffer: bytearray, start: int, end: int) -> None:
    touched = 0
    for offset in range(start, end, PAGE_BYTES):
        buffer[offset] = 1
        touched += 1
        if touched % 4096 == 0 and _stop:
            return


def _ramp(buffer: bytearray, target_bytes: int, duration_s: float, start: float) -> None:
    deadline = start + duration_s
    touched = 0
    while not _stop and time.monotonic() < deadline:
        fraction = min(1.0, (time.monotonic() - start) / duration_s)
        upto = int(target_bytes * fraction)
        if upto > touched:
            _touch(buffer, touched, upto)
            touched = upto
        time.sleep(RAMP_TICK_S)
    if not _stop and touched < target_bytes:
        _touch(buffer, touched, target_bytes)


def run_mem_grow(target_mb: int, pattern: str, duration_s: float) -> str:
    target_bytes = target_mb * 1024 * 1024
    start = time.monotonic()
    buffer: bytearray | None = None
    try:
        if pattern == "step":
            buffer = bytearray(target_bytes)
            _touch(buffer, 0, target_bytes)
            _sleep_until(start + duration_s)
        elif pattern == "ramp":
            buffer = bytearray(target_bytes)
            _ramp(buffer, target_bytes, duration_s, start)
        elif pattern == "spike":
            _sleep_until(start + duration_s / 3.0)
            buffer = bytearray(target_bytes)
            _touch(buffer, 0, target_bytes)
            _sleep_until(start + 2.0 * duration_s / 3.0)
            del buffer
            buffer = None
            _sleep_until(start + duration_s)
        else:  # sawtooth
            cycle_s = duration_s / SAWTOOTH_CYCLES
            for _ in range(SAWTOOTH_CYCLES):
                if _stop:
                    break
                buffer = bytearray(target_bytes)
                _touch(buffer, 0, target_bytes)
                _sleep_until(min(time.monotonic() + cycle_s / 2.0, start + duration_s))
                del buffer
                buffer = None
                _sleep_until(min(time.monotonic() + cycle_s / 2.0, start + duration_s))
            _sleep_until(start + duration_s)
    finally:
        del buffer
    return "target_mb=%d pattern=%s" % (target_mb, pattern)


def run_io_write(rate_mbps: float, duration_s: float, iofile: str) -> str:
    start = time.monotonic()
    deadline = start + duration_s
    bytes_per_s = max(1.0, rate_mbps * 1024.0 * 1024.0)
    chunk = b"x" * IO_CHUNK_BYTES
    written = 0
    try:
        while not _stop and time.monotonic() < deadline:
            with open(iofile, "wb") as handle:
                handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            written += IO_CHUNK_BYTES
            # Never sleep past the phase deadline: a chunk period smaller than the
            # remaining time would otherwise overrun the scheduled phase end.
            _sleep_until(min(start + written / bytes_per_s, deadline))
    finally:
        try:
            if os.path.exists(iofile):
                os.remove(iofile)
        except OSError:
            pass
    return "written_mb=%.1f rate_mbps=%g" % (written / (1024.0 * 1024.0), rate_mbps)


def run_fork_light(procs_per_s: float, duration_s: float) -> str:
    deadline = time.monotonic() + duration_s
    period_s = 1.0 / procs_per_s
    children: list[subprocess.Popen] = []
    spawned = 0
    failed = 0
    next_spawn = time.monotonic()
    try:
        while not _stop and time.monotonic() < deadline:
            try:
                children.append(subprocess.Popen([SLEEP_BIN, SLEEP_CHILD_S]))
                spawned += 1
            except OSError:
                failed += 1  # pids.max refused the fork
            children = [child for child in children if child.poll() is None]
            next_spawn = max(next_spawn + period_s, time.monotonic())
            _sleep_until(min(next_spawn, deadline))
    finally:
        _terminate(children)
    return "spawned=%d failed=%d rate=%g" % (spawned, failed, procs_per_s)


def mixed_child_argv(item: dict[str, Any], duration_s: float) -> list[str]:
    kind = item["type"]
    argv = [sys.executable, os.path.abspath(__file__), kind]
    if kind == "cpu_burn":
        argv += ["--procs", str(int(item["procs"]))]
    elif kind == "mem_grow":
        argv += ["--target-mb", str(int(item["target_mb"])), "--pattern", str(item["pattern"])]
    elif kind == "io_write":
        if "iofile" not in item:
            raise ValueError("mixed io_write item needs an 'iofile' path")
        argv += ["--rate-mbps", str(item["rate_mbps"]), "--iofile", str(item["iofile"])]
    else:
        raise ValueError("unsupported mixed sub-load type: %r" % kind)
    argv += ["--duration", "%g" % duration_s]
    return argv


def run_mixed(spec: list[dict[str, Any]], duration_s: float) -> str:
    children: list[subprocess.Popen] = []
    try:
        for item in spec:
            children.append(subprocess.Popen(mixed_child_argv(item, duration_s)))
        _sleep_until(time.monotonic() + duration_s)
    finally:
        _terminate(children)
    return "parts=%s" % ",".join(str(item["type"]) for item in spec)


def run_variant(args: argparse.Namespace) -> str:
    if args.variant == "cpu_burn":
        return run_cpu_burn(args.procs, args.duration)
    if args.variant == "mem_grow":
        return run_mem_grow(args.target_mb, args.pattern, args.duration)
    if args.variant == "io_write":
        return run_io_write(args.rate_mbps, args.duration, args.iofile)
    if args.variant == "fork_light":
        return run_fork_light(args.procs_per_s, args.duration)
    spec = json.loads(args.spec)
    if not isinstance(spec, list) or not spec:
        raise ValueError("--spec must be a non-empty JSON list")
    return run_mixed(spec, args.duration)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WorkloadPilot dataset-v2 neighbor stressor (one phase per run).")
    sub = parser.add_subparsers(dest="variant", required=True)

    cpu = sub.add_parser("cpu_burn")
    cpu.add_argument("--procs", type=int, required=True)
    cpu.add_argument("--duration", type=float, required=True)

    mem = sub.add_parser("mem_grow")
    mem.add_argument("--target-mb", type=int, required=True)
    mem.add_argument("--pattern", choices=("step", "ramp", "spike", "sawtooth"), required=True)
    mem.add_argument("--duration", type=float, required=True)

    io_write = sub.add_parser("io_write")
    io_write.add_argument("--rate-mbps", type=float, required=True)
    io_write.add_argument("--duration", type=float, required=True)
    io_write.add_argument("--iofile", required=True)

    fork = sub.add_parser("fork_light")
    fork.add_argument("--procs-per-s", type=float, required=True)
    fork.add_argument("--duration", type=float, required=True)

    mixed = sub.add_parser("mixed")
    mixed.add_argument("--spec", required=True, help="JSON list of sub-loads")
    mixed.add_argument("--duration", type=float, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.duration <= 0:
        raise SystemExit("error: --duration must be > 0")
    signal.signal(signal.SIGTERM, _on_stop)
    signal.signal(signal.SIGINT, _on_stop)

    print("STRESSOR START type=%s duration=%gs pid=%d" % (args.variant, args.duration, os.getpid()), flush=True)
    started = time.monotonic()
    detail = run_variant(args)
    print("STRESSOR END type=%s elapsed=%.1fs %s" % (args.variant, time.monotonic() - started, detail), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
