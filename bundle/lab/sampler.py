#!/usr/bin/env python3
"""WorkloadPilot Milestone 0 recorder: cgroup v2 + PSI telemetry snapshotter.

Writes one JSON object per line (JSONL), one line per tick, flushed per line.
Any field whose source file is missing, unreadable or malformed is null; the
recorder never raises on a bad read and always writes a line every tick.

Unit -> cgroup mapping: /sys/fs/cgroup/wlp.slice/<unit>/.
"""

import argparse
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Any

CGROUP_ROOT = "/sys/fs/cgroup/wlp.slice"
MB_DIVISOR = 1024.0 * 1024.0
PSI_FIELDS = ("avg10", "avg60", "avg300", "total")
CPU_STAT_FIELDS = (
    "usage_usec",
    "user_usec",
    "system_usec",
    "nr_periods",
    "nr_throttled",
    "throttled_usec",
)
MEMORY_EVENT_FIELDS = ("low", "high", "max", "oom", "oom_kill")

_running: bool = True


def _handle_stop(signum: int, frame: Any) -> None:
    global _running
    _running = False


def now_iso() -> str:
    """ISO8601 UTC with milliseconds, e.g. 2026-10-15T12:34:56.789Z."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def read_text(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return None


def bytes_to_mb(value: int) -> float:
    return round(value / MB_DIVISOR, 2)


def parse_psi(text: str | None, kind: str) -> dict[str, float | int] | None:
    """Parse the "some"/"full" line of a PSI file into avg10/avg60/avg300/total."""
    if text is None:
        return None
    for line in text.splitlines():
        tokens = line.split()
        if not tokens or tokens[0] != kind:
            continue
        parsed: dict[str, float | int] = {}
        for token in tokens[1:]:
            key, separator, raw = token.partition("=")
            if not separator:
                continue
            try:
                parsed[key] = int(raw) if key == "total" else float(raw)
            except ValueError:
                return None
        if not all(field in parsed for field in PSI_FIELDS):
            return None
        return {field: parsed[field] for field in PSI_FIELDS}
    return None


def parse_kv_ints(text: str | None, keys: tuple[str, ...]) -> dict[str, int | None] | None:
    """Parse "key value" lines, returning exactly `keys` (absent keys -> None)."""
    if text is None:
        return None
    values: dict[str, int | None] = dict.fromkeys(keys)
    for line in text.splitlines():
        tokens = line.split()
        if len(tokens) == 2 and tokens[0] in values:
            try:
                values[tokens[0]] = int(tokens[1])
            except ValueError:
                pass
    return values


def parse_io_stat(text: str | None) -> dict[str, int] | None:
    """Sum rbytes/wbytes over all device lines of an io.stat file."""
    if text is None:
        return None
    rbytes = 0
    wbytes = 0
    for line in text.splitlines():
        for token in line.split()[1:]:
            key, separator, raw = token.partition("=")
            if not separator:
                continue
            try:
                value = int(raw)
            except ValueError:
                continue
            if key == "rbytes":
                rbytes += value
            elif key == "wbytes":
                wbytes += value
    return {"rbytes": rbytes, "wbytes": wbytes}


def parse_meminfo(text: str | None) -> dict[str, float] | None:
    """Parse /proc/meminfo into {key: kB value}."""
    if text is None:
        return None
    values: dict[str, float] = {}
    for line in text.splitlines():
        key, separator, rest = line.partition(":")
        if not separator:
            continue
        tokens = rest.split()
        if not tokens:
            continue
        try:
            values[key.strip()] = float(tokens[0])
        except ValueError:
            continue
    return values


def read_uptime() -> float | None:
    text = read_text("/proc/uptime")
    if not text:
        return None
    tokens = text.split()
    if not tokens:
        return None
    try:
        return float(tokens[0])
    except ValueError:
        return None


def read_loadavg() -> list[float] | None:
    text = read_text("/proc/loadavg")
    if not text:
        return None
    tokens = text.split()
    if len(tokens) < 3:
        return None
    try:
        return [float(tokens[0]), float(tokens[1]), float(tokens[2])]
    except ValueError:
        return None


def read_memory_mb(text: str | None) -> float | None:
    """"max" (or empty) -> None, otherwise bytes -> MB rounded to 2 decimals."""
    if text is None:
        return None
    stripped = text.strip()
    if stripped in ("", "max"):
        return None
    try:
        return bytes_to_mb(int(stripped))
    except ValueError:
        return None


def read_int(text: str | None) -> int | None:
    if text is None:
        return None
    try:
        return int(text.strip())
    except ValueError:
        return None


def system_block() -> dict[str, Any]:
    memory_pressure = read_text("/proc/pressure/memory")
    meminfo = parse_meminfo(read_text("/proc/meminfo"))
    mem_available_mb = None
    swap_used_mb = None
    if meminfo is not None:
        if "MemAvailable" in meminfo:
            mem_available_mb = round(meminfo["MemAvailable"] / 1024.0, 2)
        if "SwapTotal" in meminfo and "SwapFree" in meminfo:
            swap_used_mb = round((meminfo["SwapTotal"] - meminfo["SwapFree"]) / 1024.0, 2)
    return {
        "psi_cpu_some": parse_psi(read_text("/proc/pressure/cpu"), "some"),
        "psi_memory_some": parse_psi(memory_pressure, "some"),
        "psi_memory_full": parse_psi(memory_pressure, "full"),
        "psi_io_some": parse_psi(read_text("/proc/pressure/io"), "some"),
        "psi_io_full": parse_psi(read_text("/proc/pressure/io"), "full"),
        "loadavg": read_loadavg(),
        "mem_available_mb": mem_available_mb,
        "swap_used_mb": swap_used_mb,
    }


def cgroup_block(unit: str) -> dict[str, Any] | None:
    directory = os.path.join(CGROUP_ROOT, unit)
    if not os.path.isdir(directory):
        return None

    def read(name: str) -> str | None:
        return read_text(os.path.join(directory, name))

    cpu_max_text = read("cpu.max")
    cpu_weight_text = read("cpu.weight")
    memory_pressure = read("memory.pressure")
    return {
        "cpu_max": cpu_max_text.strip() if cpu_max_text else None,
        "cpu_weight": cpu_weight_text.strip() if cpu_weight_text else None,
        "cpu_stat": parse_kv_ints(read("cpu.stat"), CPU_STAT_FIELDS),
        "memory_current_mb": read_memory_mb(read("memory.current")),
        "memory_high_mb": read_memory_mb(read("memory.high")),
        "memory_max_mb": read_memory_mb(read("memory.max")),
        "memory_events": parse_kv_ints(read("memory.events"), MEMORY_EVENT_FIELDS),
        "io_stat": parse_io_stat(read("io.stat")),
        "pids_current": read_int(read("pids.current")),
        "psi_cpu_some": parse_psi(read("cpu.pressure"), "some"),
        "psi_memory_some": parse_psi(memory_pressure, "some"),
        "psi_memory_full": parse_psi(memory_pressure, "full"),
        "psi_io_some": parse_psi(read("io.pressure"), "some"),
    }


def unit_key(unit: str) -> str:
    return unit[: -len(".service")] if unit.endswith(".service") else unit


def build_sample(units: list[str]) -> dict[str, Any]:
    return {
        "ts": now_iso(),
        "uptime_s": read_uptime(),
        "system": system_block(),
        "cgroups": {unit_key(unit): cgroup_block(unit) for unit in units},
    }


def blank_sample(units: list[str]) -> dict[str, Any]:
    """Schema-shaped fallback so a tick can always emit a parseable line."""
    return {
        "ts": now_iso(),
        "uptime_s": None,
        "system": {
            "psi_cpu_some": None,
            "psi_memory_some": None,
            "psi_memory_full": None,
            "psi_io_some": None,
            "psi_io_full": None,
            "loadavg": None,
            "mem_available_mb": None,
            "swap_used_mb": None,
        },
        "cgroups": {unit_key(unit): None for unit in units},
    }


def sleep_sliced(seconds: float) -> None:
    """Sleep up to `seconds`, waking every 100 ms so signals stop promptly."""
    deadline = time.monotonic() + seconds
    while _running:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(0.1, remaining))


def run(out_path: str, interval: float, duration: float, units: list[str]) -> None:
    start = time.monotonic()
    deadline = start + duration if duration > 0 else None
    with open(out_path, "w", encoding="utf-8") as out:
        while _running:
            if deadline is not None and time.monotonic() >= deadline:
                break
            try:
                sample = build_sample(units)
            except Exception as error:  # a tick must always emit a line, never crash
                print("warn: sample failed: {!r}".format(error), file=sys.stderr)
                sample = blank_sample(units)
            out.write(json.dumps(sample, separators=(",", ":")) + "\n")
            out.flush()
            if not _running:
                break
            if deadline is None:
                wait = interval
            else:
                wait = min(interval, deadline - time.monotonic())
                if wait <= 0:
                    break
            sleep_sliced(wait)


def main() -> int:
    parser = argparse.ArgumentParser(description="Snapshot cgroup v2 + PSI telemetry to JSONL.")
    parser.add_argument("--out", required=True, help="output JSONL path")
    parser.add_argument("--interval", type=float, default=2.0, help="seconds between samples (default: 2)")
    parser.add_argument("--duration", type=float, default=0.0, help="total seconds to run, 0 = forever (default: 0)")
    parser.add_argument("--units", default="wlp-critical.service,wlp-neighbor.service",
                        help="comma-separated systemd unit names")
    args = parser.parse_args()

    if args.interval <= 0:
        parser.error("--interval must be greater than 0")
    if args.duration < 0:
        parser.error("--duration must be >= 0")

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    units = [unit.strip() for unit in args.units.split(",") if unit.strip()]
    run(args.out, args.interval, args.duration, units)
    return 0


if __name__ == "__main__":
    sys.exit(main())
