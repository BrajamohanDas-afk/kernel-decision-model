#!/usr/bin/env python3
"""WorkloadPilot Milestone 1 actuator: apply one bounded action to a wlp.slice cgroup.

Modes:
  CLI:  python3 actuator.py --action <name> --target <unit-name|both> [--approve]
  Pipe: printf '%s' '{"action": "...", "target": "..."}' | python3 actuator.py

Always prints exactly one JSON result line to stdout:
  {"action": str, "target": str|null, "applied": bool, "detail": str, "reason": str}

Writes are validated and clamped to hard bounds before they reach cgroupfs.
A missing unit, missing file or permission error yields applied=false with the
error text; the actuator never raises on a bad action or target.
"""

import argparse
import json
import os
import re
import sys
from typing import Any, Callable

CGROUP_ROOT = "/sys/fs/cgroup/wlp.slice"
UNITS: tuple[str, str] = ("wlp-critical", "wlp-neighbor")
TARGET_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@-]*$")

MIB = 1024 * 1024
CPU_QUOTA_MIN = 5000
CPU_QUOTA_MAX = 1000000
WEIGHT_MIN = 1
WEIGHT_MAX = 10000
PIDS_MIN = 16
PIDS_MAX = 100000
MEMORY_HIGH_MIN = 64 * MIB
MEMORY_STEP = 50 * MIB
MEMORY_HIGH_CAP = 4096 * MIB  # fallback cap for memory.high when memory.max is not numeric
IO_WEIGHT_DEFAULT = 100
IO_MAX_WBPS = MIB  # fallback write-bandwidth cap via io.max when the kernel has no io.weight (e.g. WSL)
PROTECT_WEIGHT = 400

UNIT_ACTIONS = (
    "increase_cpu",
    "decrease_cpu",
    "increase_memory",
    "decrease_memory",
    "throttle_io",
    "restrict_process_count",
)
NEVER_AUTOMATIC = ("isolate_workload", "restart_service", "kill_process")
ACTIONS = UNIT_ACTIONS + NEVER_AUTOMATIC + ("do_nothing", "protect_service", "alert_operator")


def make_result(
    action: str, target: str | None, applied: bool, detail: str, reason: str
) -> dict[str, Any]:
    return {
        "action": action,
        "target": target,
        "applied": applied,
        "detail": detail,
        "reason": reason,
    }


def cgroup_path(unit: str) -> str:
    return CGROUP_ROOT + "/" + unit + ".service"


def read_text(path: str) -> tuple[str | None, str | None]:
    """Return (stripped text, error); error is None on success."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read().strip(), None
    except OSError as error:
        return None, type(error).__name__ + ": " + str(error)


def write_text(path: str, text: str) -> str | None:
    """Write text to a cgroup file; returns None on success, error text otherwise."""
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return None
    except OSError as error:
        return type(error).__name__ + ": " + str(error)


def parse_int(text: str | None) -> int | None:
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def clamp(value: int, low: int, high: int) -> tuple[int, bool]:
    """Clamp to [low, high]; returns (value, was_clamped)."""
    if value < low:
        return low, True
    if value > high:
        return high, True
    return value, False


def write_cpu_weight(unit: str, transform: Callable[[int], int]) -> tuple[bool, str]:
    """Read cpu.weight, transform it, write it back. Returns (ok, note)."""
    path = cgroup_path(unit) + "/cpu.weight"
    text, error = read_text(path)
    if text is None:
        return False, "cpu.weight unavailable (" + str(error) + ")"
    current = parse_int(text)
    if current is None:
        return False, "cpu.weight unparseable (" + text + ")"
    candidate, clamped = clamp(transform(current), WEIGHT_MIN, WEIGHT_MAX)
    write_error = write_text(path, str(candidate))
    if write_error is not None:
        return False, "cpu.weight write failed (" + write_error + ")"
    note = "cpu.weight " + str(current) + "->" + str(candidate)
    if clamped:
        note += " [clamped to " + str(WEIGHT_MIN) + ".." + str(WEIGHT_MAX) + "]"
    return True, note


def memory_cap(unit: str) -> tuple[int, str]:
    """Upper bound for memory.high: numeric memory.max when present, else sane cap."""
    text, _error = read_text(cgroup_path(unit) + "/memory.max")
    limit = parse_int(text)
    if limit is None:
        return MEMORY_HIGH_CAP, "sane cap " + str(MEMORY_HIGH_CAP // MIB) + "M"
    return limit, "memory.max " + str(limit // MIB) + "M"


def apply_increase_cpu(unit: str) -> tuple[bool, str, str]:
    path = cgroup_path(unit) + "/cpu.max"
    text, error = read_text(path)
    if text is None:
        return False, "", "cpu.max unreadable (" + str(error) + ")"
    tokens = text.split()
    if not tokens or tokens[0] == "max":
        return False, "", "no cpu quota set (cpu.max=" + text + ")"
    quota = parse_int(tokens[0]) if len(tokens) > 0 else None
    period = parse_int(tokens[1]) if len(tokens) > 1 else None
    if quota is None or period is None:
        return False, "", "unparseable cpu.max (" + text + ")"
    notes: list[str] = []
    candidate = int(quota * 1.5)
    if candidate > period:
        candidate = period
        notes.append("capped at 1 CPU (period " + str(period) + ")")
    candidate, clamped = clamp(candidate, CPU_QUOTA_MIN, CPU_QUOTA_MAX)
    if clamped:
        notes.append("clamped to " + str(CPU_QUOTA_MIN) + ".." + str(CPU_QUOTA_MAX))
    write_error = write_text(path, str(candidate) + " " + str(period))
    if write_error is not None:
        return False, "", "cpu.max write failed (" + write_error + ")"
    _weight_ok, weight_note = write_cpu_weight(unit, lambda value: min(WEIGHT_MAX, value * 2))
    detail = "cpu.max " + str(quota) + "->" + str(candidate) + " (period " + str(period) + ")"
    detail += "; " + weight_note
    if notes:
        detail += "; " + "; ".join(notes)
    return True, detail, ""


def apply_decrease_cpu(unit: str) -> tuple[bool, str, str]:
    path = cgroup_path(unit) + "/cpu.max"
    text, error = read_text(path)
    if text is None:
        return False, "", "cpu.max unreadable (" + str(error) + ")"
    tokens = text.split()
    if not tokens or tokens[0] == "max":
        return False, "", "no cpu quota set (cpu.max=" + text + ")"
    quota = parse_int(tokens[0]) if len(tokens) > 0 else None
    period = parse_int(tokens[1]) if len(tokens) > 1 else None
    if quota is None or period is None:
        return False, "", "unparseable cpu.max (" + text + ")"
    notes: list[str] = []
    candidate = int(quota * 0.6)
    candidate, clamped = clamp(candidate, CPU_QUOTA_MIN, CPU_QUOTA_MAX)
    if clamped:
        notes.append("clamped to " + str(CPU_QUOTA_MIN) + ".." + str(CPU_QUOTA_MAX))
    write_error = write_text(path, str(candidate) + " " + str(period))
    if write_error is not None:
        return False, "", "cpu.max write failed (" + write_error + ")"
    _weight_ok, weight_note = write_cpu_weight(unit, lambda value: max(1, value // 2))
    detail = "cpu.max " + str(quota) + "->" + str(candidate) + " (period " + str(period) + ")"
    detail += "; " + weight_note
    if notes:
        detail += "; " + "; ".join(notes)
    return True, detail, ""


def apply_increase_memory(unit: str) -> tuple[bool, str, str]:
    path = cgroup_path(unit) + "/memory.high"
    text, error = read_text(path)
    if text is None:
        return False, "", "memory.high unreadable (" + str(error) + ")"
    if text == "max":
        return False, "", "no high limit set"
    current = parse_int(text)
    if current is None:
        return False, "", "unparseable memory.high (" + text + ")"
    cap, cap_note = memory_cap(unit)
    notes: list[str] = []
    candidate = current + MEMORY_STEP
    if candidate > cap:
        candidate = cap
        notes.append("capped at " + cap_note)
    candidate, clamped = clamp(candidate, min(MEMORY_HIGH_MIN, cap), cap)
    if clamped:
        notes.append("clamped to " + str(MEMORY_HIGH_MIN // MIB) + "M.." + str(cap // MIB) + "M")
    write_error = write_text(path, str(candidate))
    if write_error is not None:
        return False, "", "memory.high write failed (" + write_error + ")"
    detail = (
        "memory.high " + str(current // MIB) + "M->" + str(candidate // MIB) + "M"
        + " (was " + str(current) + " bytes)"
    )
    if notes:
        detail += "; " + "; ".join(notes)
    return True, detail, ""


def apply_decrease_memory(unit: str) -> tuple[bool, str, str]:
    path = cgroup_path(unit) + "/memory.high"
    text, error = read_text(path)
    if text is None:
        return False, "", "memory.high unreadable (" + str(error) + ")"
    if text == "max":
        return False, "", "memory.high is max; nothing to decrease"
    current = parse_int(text)
    if current is None:
        return False, "", "unparseable memory.high (" + text + ")"
    cap, cap_note = memory_cap(unit)
    notes: list[str] = []
    candidate = current - MEMORY_STEP
    if candidate < MEMORY_HIGH_MIN:
        candidate = MEMORY_HIGH_MIN
        notes.append("floored at " + str(MEMORY_HIGH_MIN // MIB) + "M")
    candidate, clamped = clamp(candidate, min(MEMORY_HIGH_MIN, cap), cap)
    if clamped:
        notes.append("capped at " + cap_note)
    write_error = write_text(path, str(candidate))
    if write_error is not None:
        return False, "", "memory.high write failed (" + write_error + ")"
    detail = (
        "memory.high " + str(current // MIB) + "M->" + str(candidate // MIB) + "M"
        + " (was " + str(current) + " bytes)"
    )
    if notes:
        detail += "; " + "; ".join(notes)
    return True, detail, ""


def apply_throttle_io(unit: str) -> tuple[bool, str, str]:
    # Prefer the weight interface where it exists; fall back to a hard bytes-per-second
    # cap via io.max (WSL kernels expose io.max/io.stat but no io.weight at all).
    weight_path = cgroup_path(unit) + "/io.weight"
    text, weight_error = read_text(weight_path)
    if text is not None:
        tokens = text.split()
        current = parse_int(tokens[-1]) if tokens else None
        note = ""
        if current is None:
            current = IO_WEIGHT_DEFAULT
            note = "io.weight unparseable (" + text + "), assumed " + str(current) + "; "
        candidate, clamped = clamp(max(1, current // 2), WEIGHT_MIN, WEIGHT_MAX)
        payload = "default " + str(candidate) if tokens and tokens[0] == "default" else str(candidate)
        write_error = write_text(weight_path, payload)
        if write_error is not None:
            return False, "", "io.weight write failed (" + write_error + ")"
        detail = note + "io.weight " + str(current) + "->" + str(candidate)
        if clamped:
            detail += " [clamped]"
        return True, detail, ""
    return throttle_io_via_max(unit, str(weight_error))


def throttle_io_via_max(unit: str, weight_error: str) -> tuple[bool, str, str]:
    """Fallback throttle: cap write bandwidth on the device from this cgroup's io.stat."""
    stat_text, stat_error = read_text(cgroup_path(unit) + "/io.stat")
    if stat_text is None:
        return False, "", (
            "io.weight missing (" + weight_error + "); io.stat unreadable (" + str(stat_error) + ")"
        )
    # Device choice: prefer the filesystem backing "/" (where the lab workloads write).
    # A first version picked the busiest device from io.stat and once capped the SWAP
    # device (8:32) instead of the root disk (8:48), so the cap had no effect.
    device = None
    source = ""
    try:
        root_stat = os.stat("/")
        device = "{}:{}".format(os.major(root_stat.st_dev), os.minor(root_stat.st_dev))
        source = "root filesystem device"
    except OSError:
        pass
    if device is None:
        best_wbytes = -1
        for line in stat_text.splitlines():
            tokens = line.split()
            if not tokens:
                continue
            wbytes = 0
            for token in tokens[1:]:
                if token.startswith("wbytes="):
                    wbytes = parse_int(token.split("=", 1)[1]) or 0
            if wbytes > best_wbytes:
                best_wbytes = wbytes
                device = tokens[0]
                source = "busiest device in io.stat"
    if device is None:
        return False, "", "io.weight missing (" + weight_error + "); no device in io.stat"
    max_path = cgroup_path(unit) + "/io.max"
    write_error = write_text(max_path, device + " wbps=" + str(IO_MAX_WBPS))
    if write_error is not None:
        return False, "", "io.max write failed (" + write_error + ")"
    detail = (
        "io.weight unavailable; io.max capped " + device + " writes to "
        + str(IO_MAX_WBPS // MIB) + " MiB/s (" + source + ")"
    )
    return True, detail, ""


def apply_restrict_process_count(unit: str) -> tuple[bool, str, str]:
    directory = cgroup_path(unit)
    max_text, max_error = read_text(directory + "/pids.max")
    if max_text is None:
        return False, "", "pids.max unreadable (" + str(max_error) + ")"
    current_text, current_error = read_text(directory + "/pids.current")
    current = parse_int(current_text)
    if current is None:
        return False, "", "pids.current unreadable (" + str(current_error) + ")"
    notes: list[str] = []
    if max_text == "max":
        candidate = current + 50
        notes.append("pids.max was max")
    else:
        limit = parse_int(max_text)
        if limit is None:
            return False, "", "unparseable pids.max (" + max_text + ")"
        candidate = max(current + 5, limit // 2)
    candidate, clamped = clamp(candidate, PIDS_MIN, PIDS_MAX)
    if clamped:
        notes.append("clamped to " + str(PIDS_MIN) + ".." + str(PIDS_MAX))
    write_error = write_text(directory + "/pids.max", str(candidate))
    if write_error is not None:
        return False, "", "pids.max write failed (" + write_error + ")"
    detail = (
        "pids.max " + max_text + "->" + str(candidate) + " (pids.current " + str(current) + ")"
    )
    if notes:
        detail += "; " + "; ".join(notes)
    return True, detail, ""


def apply_protect_service() -> tuple[bool, str, str]:
    """Boost wlp-critical cpu.weight to 400 and halve wlp-neighbor cpu.weight."""
    critical_ok, critical_note = write_cpu_weight("wlp-critical", lambda value: PROTECT_WEIGHT)
    neighbor_ok, neighbor_note = write_cpu_weight("wlp-neighbor", lambda value: value // 2)
    applied = critical_ok or neighbor_ok
    detail = "wlp-critical: " + critical_note + "; wlp-neighbor: " + neighbor_note
    reason = "" if applied else critical_note + "; " + neighbor_note
    return applied, detail, reason


UNIT_HANDLERS: dict[str, Callable[[str], tuple[bool, str, str]]] = {
    "increase_cpu": apply_increase_cpu,
    "decrease_cpu": apply_decrease_cpu,
    "increase_memory": apply_increase_memory,
    "decrease_memory": apply_decrease_memory,
    "throttle_io": apply_throttle_io,
    "restrict_process_count": apply_restrict_process_count,
}


def apply_action(action: str, target: str | None, approve: bool) -> dict[str, Any]:
    if action == "do_nothing":
        return make_result(action, target, True, "no-op", "")
    if action == "alert_operator":
        return make_result(action, target, False, "operator alert logged", "")
    if action in NEVER_AUTOMATIC:
        if not approve:
            return make_result(action, target, False, "no write performed", "requires approval")
        return make_result(
            action,
            target,
            False,
            "human approval flow not implemented in lab",
            "approval flow not implemented in lab",
        )
    if action == "protect_service":
        applied, detail, reason = apply_protect_service()
        return make_result(action, target, applied, detail, reason)
    if action not in UNIT_HANDLERS:
        return make_result(action, target, False, "", "unknown action")
    if target is None:
        return make_result(
            action, None, False, "", "target required (unit name, wlp-critical, wlp-neighbor or both)"
        )
    if target == "both":
        units = list(UNITS)
    elif TARGET_PATTERN.match(target):
        units = [target]
    else:
        return make_result(
            action,
            target,
            False,
            "",
            "unknown target (unit name, wlp-critical, wlp-neighbor or both)",
        )
    outcomes = [(unit, UNIT_HANDLERS[action](unit)) for unit in units]
    applied = all(ok for _unit, (ok, _detail, _reason) in outcomes)
    detail = "; ".join(
        unit + ": " + part_detail for unit, (_ok, part_detail, _reason) in outcomes if part_detail
    )
    reason = "; ".join(part_reason for _unit, (_ok, _detail, part_reason) in outcomes if part_reason)
    return make_result(action, target, applied, detail, reason)


def run(argv: list[str]) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="WorkloadPilot M1 cgroup actuator")
    parser.add_argument("--action", help="action name (" + ", ".join(ACTIONS) + ")")
    parser.add_argument("--target", help="wlp-critical, wlp-neighbor, both or a lab unit name")
    parser.add_argument("--approve", action="store_true", help="acknowledge gated actions")
    args = parser.parse_args(argv)

    action: Any = args.action
    target: Any = args.target
    approve = bool(args.approve)

    if action is None:
        if not sys.stdin.isatty():
            try:
                payload = json.load(sys.stdin)
            except (json.JSONDecodeError, OSError) as error:
                return make_result("", None, False, "", "invalid stdin json: " + str(error))
            if not isinstance(payload, dict):
                return make_result("", None, False, "", "stdin json must be an object")
            action = payload.get("action")
            target = payload.get("target")
            approve = approve or bool(payload.get("approve", False))

    if not isinstance(action, str) or action == "":
        return make_result("", None, False, "", "no action given")
    if target is not None and not isinstance(target, str):
        return make_result(action, None, False, "", "target must be a string")
    return apply_action(action, target, approve)


def main(argv: list[str]) -> int:
    print(json.dumps(run(argv), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
