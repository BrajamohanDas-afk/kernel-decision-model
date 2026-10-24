#!/usr/bin/env python3
"""WorkloadPilot M1 rules: pure, deterministic teacher for a cgroup resource controller.

Contract
--------
decide(prev_state, cur_state) -> {"action": str, "target": str | None,
                                  "reason": str, "confidence": float}

  prev_state / cur_state: consecutive sampler rows, schema exactly as written by
  sampler.py (out/telemetry.jsonl): {"ts", "uptime_s", "system", "cgroups"} where
  any field may be null and a cgroup block is null while its unit is not running.
  decide() is pure: no I/O, no randomness, no input mutation, deterministic.

Action vocabulary (fixed, 12):
  do_nothing, increase_cpu, decrease_cpu, increase_memory, decrease_memory,
  throttle_io, restrict_process_count, protect_service, isolate_workload,
  restart_service, kill_process, alert_operator

Safety
------
restart_service, kill_process and isolate_workload are NEVER returned: the
actuator's safety layer forbids automatic use. Situations that would want them
surface as alert_operator (severe mutual CPU contention) for a human operator.

Rule order (first match wins)
-----------------------------
 1 alert_operator          current row missing or a blank sampler row
 2 alert_operator          a previously readable unit block vanished or went dark
 3 alert_operator          memory.events max/oom/oom_kill grew, or memory near memory.max
 4 alert_operator          both units pinned at their CPU quota (isolation stays manual)
 5 protect_service         critical unit under pressure while the neighbor consumes hard
 6 increase_memory         a unit close to memory.high, or memory.events.high growing
 7 throttle_io             a unit writing fast with io pressure
 8 restrict_process_count  pids.current spiking above its recent level
 9 increase_cpu            a unit pinned at its CPU quota while system cpu pressure is high
10 decrease_memory         memory.high pressure released since the previous row
11 decrease_cpu            unit cpu pressure released since the previous row
12 do_nothing              default

Calibration (real M0 run, out/telemetry.jsonl, 2026-10-14, 2s cadence):
cpu hog throttled at ~2.5e6 usec/s with system psi_cpu avg10 up to 76; memory
stalled at 99.7% of memory.high with memory.events.high growing; io phase wrote
2.6-3.2 MB/s while this VM's SYSTEM psi_io stayed below 0.6, so a unit's own
io.pressure is the io gate.

CLI
---
  python3 rules.py --selftest                  crafted table + seeded fuzz, exit != 0 on failure
  python3 rules.py --file <telemetry.jsonl>    one decision per consecutive row pair
"""

import argparse
import copy
import json
import math
import random
import sys
from typing import Any

# --------------------------------------------------------------- vocabulary
ACTION_DO_NOTHING = "do_nothing"
ACTION_INCREASE_CPU = "increase_cpu"
ACTION_DECREASE_CPU = "decrease_cpu"
ACTION_INCREASE_MEMORY = "increase_memory"
ACTION_DECREASE_MEMORY = "decrease_memory"
ACTION_THROTTLE_IO = "throttle_io"
ACTION_RESTRICT_PROCESS_COUNT = "restrict_process_count"
ACTION_PROTECT_SERVICE = "protect_service"
ACTION_ISOLATE_WORKLOAD = "isolate_workload"
ACTION_RESTART_SERVICE = "restart_service"
ACTION_KILL_PROCESS = "kill_process"
ACTION_ALERT_OPERATOR = "alert_operator"

ACTIONS: tuple[str, ...] = (
    ACTION_DO_NOTHING,
    ACTION_INCREASE_CPU,
    ACTION_DECREASE_CPU,
    ACTION_INCREASE_MEMORY,
    ACTION_DECREASE_MEMORY,
    ACTION_THROTTLE_IO,
    ACTION_RESTRICT_PROCESS_COUNT,
    ACTION_PROTECT_SERVICE,
    ACTION_ISOLATE_WORKLOAD,
    ACTION_RESTART_SERVICE,
    ACTION_KILL_PROCESS,
    ACTION_ALERT_OPERATOR,
)

# The actuator refuses these automatically; decide() must never return them.
FORBIDDEN_AUTOMATIC: tuple[str, ...] = (
    ACTION_ISOLATE_WORKLOAD,
    ACTION_RESTART_SERVICE,
    ACTION_KILL_PROCESS,
)

REACHABLE_ACTIONS: tuple[str, ...] = tuple(
    action for action in ACTIONS if action not in FORBIDDEN_AUTOMATIC
)

UNIT_CRITICAL = "wlp-critical"
UNIT_NEIGHBOR = "wlp-neighbor"
TARGET_BOTH = "both"
TARGETS: tuple[Any, ...] = (UNIT_CRITICAL, UNIT_NEIGHBOR, TARGET_BOTH, None)

# ------------------------------------------------------------------ tuning
DEFAULT_SAMPLE_INTERVAL_S = 2.0  # fallback when uptime_s delta is unusable
MB_DIVISOR = 1024.0 * 1024.0  # sampler reports MB as MiB (bytes / 1048576)
CPU_THROTTLE_RATE_HIGH = 1_000_000.0  # usec/s: unit sitting on its quota (real run ~2.5e6)
CPU_THROTTLE_RATE_BUSY = 500_000.0  # usec/s: unit clearly competing for CPU
CPU_THROTTLE_RATE_LOW = 100_000.0  # usec/s: quota no longer binding
PSI_CPU_SOME_HIGH = 10.0  # system cpu.pressure avg10 % (real cpu phase: up to 76)
PSI_CPU_SOME_LOW = 2.0  # system cpu.pressure avg10 % that counts as quiet
UNIT_PSI_CPU_BUSY = 30.0  # unit cpu.pressure avg10 % = visibly queued (real: up to 82)
CRIT_PSI_CPU_PRESSURE = 5.0  # critical unit cpu.pressure avg10 % worth acting on
CRIT_PSI_MEM_PRESSURE = 5.0  # critical unit memory.pressure avg10 % worth acting on
MEMORY_HIGH_RATIO = 0.90  # memory.current / memory.high (real mem phase: 0.997)
MEMORY_HIGH_RATIO_EVENTS = 0.80  # ratio that counts when memory.events.high grows
MEMORY_HARD_RATIO_ALERT = 0.98  # memory.current / memory.max -> operator
MEMORY_RELEASE_RATIO = 0.50  # drop below this after >=90% -> decrease_memory
IO_WRITE_RATE_MBPS = 2.0  # MiB/s sustained writes (real io phase: 2.6-3.2)
PSI_IO_SOME_ELEVATED = 0.10  # unit io.pressure avg10/60 (real io phase median 0.30)
PIDS_GROWTH = 2  # pids.current increase between consecutive rows
PIDS_ABSOLUTE_HIGH = 32  # absolute process-count guard

CONF_ALERT_BLIND = 0.60  # no current row at all
CONF_ALERT_GAP = 0.90  # sampler row is blank
CONF_ALERT_LOST = 0.90  # a unit's telemetry disappeared
CONF_ALERT_HARD_MEMORY = 0.95
CONF_ALERT_CONTENTION = 0.80
CONF_PROTECT_SERVICE = 0.85
CONF_INCREASE_MEMORY = 0.85
CONF_THROTTLE_IO = 0.75
CONF_RESTRICT_PROCESS_COUNT = 0.70
CONF_INCREASE_CPU = 0.80
CONF_DECREASE_MEMORY = 0.60
CONF_DECREASE_CPU = 0.60
CONF_DO_NOTHING = 0.80
CONF_DO_NOTHING_BLIND = 0.50

FUZZ_SEED = 20261015  # fixed so --selftest is deterministic
FUZZ_PAIRS = 3000


# ----------------------------------------------------------------- helpers
def _dict(value: Any) -> dict[str, Any]:
    """Schema access: anything that is not a dict reads as an empty block."""
    return value if isinstance(value, dict) else {}


def _num(value: Any) -> float | None:
    """Finite float or None; bools, strings, NaN and infinities read as None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _get(block: dict[str, Any], *path: str) -> Any:
    """Walk a nested field path; a broken link returns None, never raises."""
    cur: Any = block
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _delta(cur_value: Any, prev_value: Any) -> float | None:
    """cur - prev for monotonic counters; None if unknown or reset backwards."""
    cur_number, prev_number = _num(cur_value), _num(prev_value)
    if cur_number is None or prev_number is None or cur_number < prev_number:
        return None
    return cur_number - prev_number


def _rate(delta: float | None, dt: float) -> float | None:
    return None if delta is None else delta / dt


def _rate_mb(delta: float | None, dt: float) -> float | None:
    rate = _rate(delta, dt)
    return None if rate is None else rate / MB_DIVISOR


def _ratio(cur_value: Any, limit_value: Any) -> float | None:
    cur_number, limit_number = _num(cur_value), _num(limit_value)
    if cur_number is None or limit_number is None or limit_number <= 0.0:
        return None
    return cur_number / limit_number


def _memory_limit_mb(block: dict[str, Any]) -> float | None:
    """memory.high when set, otherwise memory.max ("max"/missing read as None)."""
    limit = _num(block.get("memory_high_mb"))
    if limit is None:
        limit = _num(block.get("memory_max_mb"))
    return limit


def _memory_ratio(block: dict[str, Any]) -> float | None:
    """memory.current as a fraction of memory.high (fallback: memory.max)."""
    return _ratio(block.get("memory_current_mb"), _memory_limit_mb(block))


def _dt_seconds(prev_state: dict[str, Any], cur_state: dict[str, Any]) -> float:
    """Seconds between the rows; sampler cadence when uptime is unusable."""
    delta = _delta(cur_state.get("uptime_s"), prev_state.get("uptime_s"))
    if delta is not None and delta > 0.0:
        return delta
    return DEFAULT_SAMPLE_INTERVAL_S


def _unit_usable(block: dict[str, Any]) -> bool:
    """True when a cgroup block carries at least one live metric."""
    return bool(block) and any(
        block.get(key) is not None
        for key in ("cpu_stat", "memory_current_mb", "pids_current")
    )


def _system_blind(system: dict[str, Any]) -> bool:
    """True when the system block carries no usable number at all."""
    loadavg = system.get("loadavg")
    load1 = _num(loadavg[0]) if isinstance(loadavg, list) and loadavg else None
    return (
        _num(_get(system, "psi_cpu_some", "avg10")) is None
        and _num(_get(system, "psi_io_some", "avg10")) is None
        and _num(system.get("mem_available_mb")) is None
        and load1 is None
    )


def _target_of(names: list[str]) -> str | None:
    if not names:
        return None
    return names[0] if len(names) == 1 else TARGET_BOTH


def _decision(action: str, target: str | None, reason: str, confidence: float) -> dict[str, Any]:
    """The single place the return contract is written."""
    return {"action": action, "target": target, "reason": reason, "confidence": float(confidence)}


def _fmt_mb(value: float | None) -> str:
    return "n/a" if value is None else "%.1fMB" % value


def _unit_signals(prev_block: dict[str, Any], cur_block: dict[str, Any], dt: float) -> dict[str, Any]:
    """Every per-unit number the rules read; anything unreadable stays None."""
    current_mb = _num(cur_block.get("memory_current_mb"))
    high_events = _delta(
        _get(cur_block, "memory_events", "high"), _get(prev_block, "memory_events", "high")
    )
    pids = _num(cur_block.get("pids_current"))
    pids_delta = _delta(cur_block.get("pids_current"), prev_block.get("pids_current"))
    memory_ratio = _memory_ratio(cur_block)
    return {
        "cur_usable": _unit_usable(cur_block),
        "cpu_throttle_rate": _rate(
            _delta(
                _get(cur_block, "cpu_stat", "throttled_usec"),
                _get(prev_block, "cpu_stat", "throttled_usec"),
            ),
            dt,
        ),
        "mem_current_mb": current_mb,
        "mem_ratio": memory_ratio,
        "mem_hard_ratio": _ratio(cur_block.get("memory_current_mb"), cur_block.get("memory_max_mb")),
        "prev_mem_ratio": _memory_ratio(prev_block),
        "mem_high_events_delta": high_events,
        "mem_max_events_delta": _delta(
            _get(cur_block, "memory_events", "max"), _get(prev_block, "memory_events", "max")
        ),
        "mem_oom_delta": _delta(
            _get(cur_block, "memory_events", "oom"), _get(prev_block, "memory_events", "oom")
        ),
        "mem_oom_kill_delta": _delta(
            _get(cur_block, "memory_events", "oom_kill"), _get(prev_block, "memory_events", "oom_kill")
        ),
        "pids": pids,
        "pids_delta": pids_delta,
        "wbytes_rate_mbs": _rate_mb(
            _delta(_get(cur_block, "io_stat", "wbytes"), _get(prev_block, "io_stat", "wbytes")),
            dt,
        ),
        "psi_cpu10": _num(_get(cur_block, "psi_cpu_some", "avg10")),
        "psi_mem10": _num(_get(cur_block, "psi_memory_some", "avg10")),
        "psi_io10": _num(_get(cur_block, "psi_io_some", "avg10")),
        "psi_io60": _num(_get(cur_block, "psi_io_some", "avg60")),
        "prev_psi_cpu10": _num(_get(prev_block, "psi_cpu_some", "avg10")),
    }


# ------------------------------------------------------- per-rule predicates
def _cpu_pinned(signals: dict[str, Any]) -> bool:
    """Unit sits on its CPU quota in this interval."""
    return signals["cur_usable"] and (signals["cpu_throttle_rate"] or 0.0) >= CPU_THROTTLE_RATE_HIGH


def _critical_pressured(signals: dict[str, Any]) -> bool:
    """Critical unit is visibly held back (cpu, memory or process pressure)."""
    if not signals["cur_usable"]:
        return False
    return (
        (signals["cpu_throttle_rate"] or 0.0) >= CPU_THROTTLE_RATE_BUSY
        or (signals["psi_cpu10"] or 0.0) >= CRIT_PSI_CPU_PRESSURE
        or (signals["mem_ratio"] or 0.0) >= MEMORY_HIGH_RATIO
        or (signals["psi_mem10"] or 0.0) >= CRIT_PSI_MEM_PRESSURE
        or (signals["pids_delta"] or 0.0) >= PIDS_GROWTH
    )


def _critical_why(signals: dict[str, Any]) -> str:
    if (signals["cpu_throttle_rate"] or 0.0) >= CPU_THROTTLE_RATE_BUSY:
        return "cpu throttled %.2fs/s" % ((signals["cpu_throttle_rate"] or 0.0) / 1_000_000.0)
    if (signals["psi_cpu10"] or 0.0) >= CRIT_PSI_CPU_PRESSURE:
        return "cpu.pressure avg10 %.1f" % (signals["psi_cpu10"] or 0.0)
    if (signals["mem_ratio"] or 0.0) >= MEMORY_HIGH_RATIO:
        return "memory at %.1f%% of high" % ((signals["mem_ratio"] or 0.0) * 100.0)
    if (signals["psi_mem10"] or 0.0) >= CRIT_PSI_MEM_PRESSURE:
        return "memory.pressure avg10 %.1f" % (signals["psi_mem10"] or 0.0)
    return "pids +%.0f in one interval" % (signals["pids_delta"] or 0.0)


def _neighbor_busy(signals: dict[str, Any]) -> bool:
    """Neighbor is a heavy consumer this interval."""
    if not signals["cur_usable"]:
        return False
    return (
        (signals["cpu_throttle_rate"] or 0.0) >= CPU_THROTTLE_RATE_BUSY
        or (signals["psi_cpu10"] or 0.0) >= UNIT_PSI_CPU_BUSY
        or (signals["mem_ratio"] or 0.0) >= MEMORY_HIGH_RATIO
        or (signals["wbytes_rate_mbs"] or 0.0) >= IO_WRITE_RATE_MBPS
    )


def _neighbor_why(signals: dict[str, Any]) -> str:
    if (signals["cpu_throttle_rate"] or 0.0) >= CPU_THROTTLE_RATE_BUSY:
        return "cpu throttled %.2fs/s" % ((signals["cpu_throttle_rate"] or 0.0) / 1_000_000.0)
    if (signals["psi_cpu10"] or 0.0) >= UNIT_PSI_CPU_BUSY:
        return "cpu.pressure avg10 %.1f" % (signals["psi_cpu10"] or 0.0)
    if (signals["mem_ratio"] or 0.0) >= MEMORY_HIGH_RATIO:
        return "memory at %.1f%% of high" % ((signals["mem_ratio"] or 0.0) * 100.0)
    return "writing %.1f MB/s" % (signals["wbytes_rate_mbs"] or 0.0)


def _hard_memory_alarm(signals: dict[str, Any]) -> bool:
    """Hard memory limit hit or imminent: memory.events max/oom growth or >=98% max."""
    if not signals["cur_usable"]:
        return False
    return (
        (signals["mem_max_events_delta"] or 0.0) > 0.0
        or (signals["mem_oom_delta"] or 0.0) > 0.0
        or (signals["mem_oom_kill_delta"] or 0.0) > 0.0
        or (signals["mem_hard_ratio"] or 0.0) >= MEMORY_HARD_RATIO_ALERT
    )


def _hard_memory_reason(name: str, signals: dict[str, Any]) -> str:
    events = sum(
        signals[key] or 0.0
        for key in ("mem_max_events_delta", "mem_oom_delta", "mem_oom_kill_delta")
    )
    if events > 0.0:
        return "%s hit its memory hard limit (events max/oom/oom_kill grew)" % name
    return "%s memory %s at %.1f%% of memory.max" % (
        name,
        _fmt_mb(signals["mem_current_mb"]),
        (signals["mem_hard_ratio"] or 0.0) * 100.0,
    )


def _memory_pressured(signals: dict[str, Any]) -> bool:
    """memory.current near memory.high, or memory.events.high growing."""
    ratio = signals["mem_ratio"]
    if ratio is None:
        return False
    if ratio >= MEMORY_HIGH_RATIO:
        return True
    return ratio >= MEMORY_HIGH_RATIO_EVENTS and (signals["mem_high_events_delta"] or 0.0) > 0.0


def _memory_reason(name: str, signals: dict[str, Any]) -> str:
    text = "%s memory %s = %.1f%% of memory.high" % (
        name,
        _fmt_mb(signals["mem_current_mb"]),
        (signals["mem_ratio"] or 0.0) * 100.0,
    )
    events = signals["mem_high_events_delta"] or 0.0
    if events > 0.0:
        text += ", memory.events.high +%.0f" % events
    return text


def _io_hammering(signals: dict[str, Any]) -> bool:
    """Sustained fast writes with the unit itself reporting io pressure."""
    if not signals["cur_usable"]:
        return False
    return (
        (signals["wbytes_rate_mbs"] or 0.0) >= IO_WRITE_RATE_MBPS
        and max(signals["psi_io10"] or 0.0, signals["psi_io60"] or 0.0) >= PSI_IO_SOME_ELEVATED
    )


def _pids_spiking(signals: dict[str, Any]) -> bool:
    if not signals["cur_usable"]:
        return False
    return (
        (signals["pids_delta"] or 0.0) >= PIDS_GROWTH
        or (signals["pids"] or 0.0) >= PIDS_ABSOLUTE_HIGH
    )


def _pids_reason(name: str, signals: dict[str, Any]) -> str:
    if (signals["pids_delta"] or 0.0) >= PIDS_GROWTH:
        return "%s pids +%.0f to %.0f in one interval" % (
            name,
            signals["pids_delta"] or 0.0,
            signals["pids"] or 0.0,
        )
    return "%s pids %.0f at or above the %d guard" % (
        name,
        signals["pids"] or 0.0,
        PIDS_ABSOLUTE_HIGH,
    )


def _memory_released(signals: dict[str, Any]) -> bool:
    """Previous row near memory.high, current row low, no further high events."""
    return (
        signals["cur_usable"]
        and (signals["prev_mem_ratio"] or 0.0) >= MEMORY_HIGH_RATIO
        and signals["mem_ratio"] is not None
        and signals["mem_ratio"] <= MEMORY_RELEASE_RATIO
        and (signals["mem_high_events_delta"] or 0.0) == 0.0
    )


def _cpu_released(signals: dict[str, Any]) -> bool:
    """Previous row showed unit cpu pressure, current row is quiet."""
    return (
        signals["cur_usable"]
        and (signals["prev_psi_cpu10"] or 0.0) >= UNIT_PSI_CPU_BUSY
        and (signals["cpu_throttle_rate"] or 0.0) <= CPU_THROTTLE_RATE_LOW
        and (signals["psi_cpu10"] or 0.0) <= PSI_CPU_SOME_LOW
    )


def _pick_max(candidates: dict[str, float]) -> str:
    """Deterministic winner: highest value, ties resolved by insertion order."""
    return max(candidates, key=lambda name: candidates[name])


# ------------------------------------------------------------- the teacher
def decide(prev_state: Any, cur_state: Any) -> dict[str, Any]:
    """Return the one safe action for the step prev_state -> cur_state."""
    prev = _dict(prev_state)
    cur = _dict(cur_state)

    # 1. no current row / blank sampler row -> nothing is trustworthy
    if not cur:
        return _decision(
            ACTION_ALERT_OPERATOR, None, "current state row is missing", CONF_ALERT_BLIND
        )
    cur_system = _dict(cur.get("system"))
    if not cur_system or _system_blind(cur_system):
        return _decision(
            ACTION_ALERT_OPERATOR, None, "current row has no usable system block", CONF_ALERT_GAP
        )

    prev_blocks = _dict(prev.get("cgroups"))
    cur_blocks = _dict(cur.get("cgroups"))
    dt = _dt_seconds(prev, cur)
    signals = {
        name: _unit_signals(_dict(prev_blocks.get(name)), _dict(cur_blocks.get(name)), dt)
        for name in (UNIT_CRITICAL, UNIT_NEIGHBOR)
    }
    critical, neighbor = signals[UNIT_CRITICAL], signals[UNIT_NEIGHBOR]
    sys_cpu10 = _num(_get(cur_system, "psi_cpu_some", "avg10"))

    # 2. a unit that reported before is gone or dark now -> crash or telemetry loss
    lost = [
        name
        for name in (UNIT_CRITICAL, UNIT_NEIGHBOR)
        if _unit_usable(_dict(prev_blocks.get(name))) and not _unit_usable(_dict(cur_blocks.get(name)))
    ]
    if lost:
        return _decision(
            ACTION_ALERT_OPERATOR,
            _target_of(lost),
            "unit telemetry lost: " + ", ".join(lost),
            CONF_ALERT_LOST,
        )

    # 3. hard memory trouble: memory.max hit or OOM happened -> human decides
    hard = [
        name
        for name in (UNIT_CRITICAL, UNIT_NEIGHBOR)
        if _hard_memory_alarm(signals[name])
    ]
    if hard:
        return _decision(
            ACTION_ALERT_OPERATOR,
            _target_of(hard),
            _hard_memory_reason(hard[0], signals[hard[0]]),
            CONF_ALERT_HARD_MEMORY,
        )

    # 4. both units pinned at their quota -> oversubscribed; isolation is an operator call
    if _cpu_pinned(critical) and _cpu_pinned(neighbor) and (sys_cpu10 or 0.0) >= PSI_CPU_SOME_HIGH:
        return _decision(
            ACTION_ALERT_OPERATOR,
            TARGET_BOTH,
            "severe contention: both units pinned at their cpu quota",
            CONF_ALERT_CONTENTION,
        )

    # 5. the critical unit suffers while the neighbor consumes hard -> protect it
    if _critical_pressured(critical) and _neighbor_busy(neighbor):
        return _decision(
            ACTION_PROTECT_SERVICE,
            TARGET_BOTH,
            "critical pressured (%s) while neighbor busy (%s)"
            % (_critical_why(critical), _neighbor_why(neighbor)),
            CONF_PROTECT_SERVICE,
        )

    # 6. a unit is running out of its memory.high allowance -> give it headroom
    memory_candidates = {
        name: signals[name]["mem_ratio"]
        for name in (UNIT_CRITICAL, UNIT_NEIGHBOR)
        if _memory_pressured(signals[name])
    }
    if memory_candidates:
        winner = _pick_max(memory_candidates)
        return _decision(
            ACTION_INCREASE_MEMORY,
            winner,
            _memory_reason(winner, signals[winner]),
            CONF_INCREASE_MEMORY,
        )

    # 7. sustained fast writes with io pressure -> throttle the writer
    io_candidates = {
        name: signals[name]["wbytes_rate_mbs"]
        for name in (UNIT_CRITICAL, UNIT_NEIGHBOR)
        if _io_hammering(signals[name])
    }
    if io_candidates:
        winner = _pick_max(io_candidates)
        psi = max(signals[winner]["psi_io10"] or 0.0, signals[winner]["psi_io60"] or 0.0)
        return _decision(
            ACTION_THROTTLE_IO,
            winner,
            "writing %.1f MB/s with io.pressure avg10/60 %.2f" % (io_candidates[winner], psi),
            CONF_THROTTLE_IO,
        )

    # 8. pids.current spiking vs its recent level -> cut the process count
    pids_candidates = {
        name: signals[name]["pids"]
        for name in (UNIT_CRITICAL, UNIT_NEIGHBOR)
        if _pids_spiking(signals[name])
    }
    if pids_candidates:
        winner = _pick_max(pids_candidates)
        return _decision(
            ACTION_RESTRICT_PROCESS_COUNT,
            winner,
            _pids_reason(winner, signals[winner]),
            CONF_RESTRICT_PROCESS_COUNT,
        )

    # 9. a unit pinned at its quota while the box is cpu-starved -> raise its quota
    throttle_candidates = {
        name: signals[name]["cpu_throttle_rate"]
        for name in (UNIT_CRITICAL, UNIT_NEIGHBOR)
        if _cpu_pinned(signals[name])
    }
    if throttle_candidates and (sys_cpu10 or 0.0) >= PSI_CPU_SOME_HIGH:
        winner = _pick_max(throttle_candidates)
        return _decision(
            ACTION_INCREASE_CPU,
            winner,
            "%s cpu throttled %.2fs/s, system psi_cpu avg10 %.1f"
            % (winner, throttle_candidates[winner] / 1_000_000.0, sys_cpu10 or 0.0),
            CONF_INCREASE_CPU,
        )

    # 10. memory.high pressure released since last row -> reclaim the allowance
    released_memory = {
        name: signals[name]["prev_mem_ratio"]
        for name in (UNIT_CRITICAL, UNIT_NEIGHBOR)
        if _memory_released(signals[name])
    }
    if released_memory:
        winner = _pick_max(released_memory)
        return _decision(
            ACTION_DECREASE_MEMORY,
            winner,
            "%s memory released (%.1f%% -> %.1f%% of memory.high)"
            % (
                winner,
                (signals[winner]["prev_mem_ratio"] or 0.0) * 100.0,
                (signals[winner]["mem_ratio"] or 0.0) * 100.0,
            ),
            CONF_DECREASE_MEMORY,
        )

    # 11. unit cpu pressure released since last row -> lower its quota
    released_cpu = {
        name: signals[name]["prev_psi_cpu10"]
        for name in (UNIT_CRITICAL, UNIT_NEIGHBOR)
        if _cpu_released(signals[name])
    }
    if released_cpu and (sys_cpu10 or 0.0) <= PSI_CPU_SOME_LOW:
        winner = _pick_max(released_cpu)
        return _decision(
            ACTION_DECREASE_CPU,
            winner,
            "%s cpu pressure released (psi_cpu avg10 %.1f -> %.1f)"
            % (
                winner,
                released_cpu[winner],
                signals[winner]["psi_cpu10"] or 0.0,
            ),
            CONF_DECREASE_CPU,
        )

    # 12. nothing crossed a threshold -> leave the system alone
    if not critical["cur_usable"] and not neighbor["cur_usable"]:
        return _decision(
            ACTION_DO_NOTHING, None, "no usable cgroup telemetry in this row", CONF_DO_NOTHING_BLIND
        )
    return _decision(ACTION_DO_NOTHING, None, "no threshold crossed", CONF_DO_NOTHING)


# ------------------------------------------------------------- selftest data
_QUIET_SYSTEM: dict[str, Any] = {
    "psi_cpu_some": {"avg10": 0.0, "avg60": 0.0, "avg300": 0.0, "total": 0},
    "psi_memory_some": {"avg10": 0.0, "avg60": 0.0, "avg300": 0.0, "total": 0},
    "psi_memory_full": {"avg10": 0.0, "avg60": 0.0, "avg300": 0.0, "total": 0},
    "psi_io_some": {"avg10": 0.0, "avg60": 0.0, "avg300": 0.0, "total": 0},
    "psi_io_full": {"avg10": 0.0, "avg60": 0.0, "avg300": 0.0, "total": 0},
    "loadavg": [0.0, 0.0, 0.0],
    "mem_available_mb": 7000.0,
    "swap_used_mb": 0.0,
}

_BLANK_SYSTEM: dict[str, Any] = {
    "psi_cpu_some": None,
    "psi_memory_some": None,
    "psi_memory_full": None,
    "psi_io_some": None,
    "psi_io_full": None,
    "loadavg": None,
    "mem_available_mb": None,
    "swap_used_mb": None,
}

_QUIET_CRITICAL: dict[str, Any] = {
    "cpu_max": "50000 100000",
    "cpu_weight": "100",
    "cpu_stat": {
        "usage_usec": 0,
        "user_usec": 0,
        "system_usec": 0,
        "nr_periods": 0,
        "nr_throttled": 0,
        "throttled_usec": 0,
    },
    "memory_current_mb": 5.0,
    "memory_high_mb": 120.0,
    "memory_max_mb": 150.0,
    "memory_events": {"low": 0, "high": 0, "max": 0, "oom": 0, "oom_kill": 0},
    "io_stat": {"rbytes": 0, "wbytes": 0},
    "pids_current": 1,
    "psi_cpu_some": {"avg10": 0.0, "avg60": 0.0, "avg300": 0.0, "total": 0},
    "psi_memory_some": {"avg10": 0.0, "avg60": 0.0, "avg300": 0.0, "total": 0},
    "psi_memory_full": {"avg10": 0.0, "avg60": 0.0, "avg300": 0.0, "total": 0},
    "psi_io_some": {"avg10": 0.0, "avg60": 0.0, "avg300": 0.0, "total": 0},
}

_QUIET_NEIGHBOR: dict[str, Any] = {
    "cpu_max": "50000 100000",
    "cpu_weight": "100",
    "cpu_stat": {
        "usage_usec": 0,
        "user_usec": 0,
        "system_usec": 0,
        "nr_periods": 0,
        "nr_throttled": 0,
        "throttled_usec": 0,
    },
    "memory_current_mb": 8.0,
    "memory_high_mb": 200.0,
    "memory_max_mb": 250.0,
    "memory_events": {"low": 0, "high": 0, "max": 0, "oom": 0, "oom_kill": 0},
    "io_stat": {"rbytes": 0, "wbytes": 0},
    "pids_current": 2,
    "psi_cpu_some": {"avg10": 0.0, "avg60": 0.0, "avg300": 0.0, "total": 0},
    "psi_memory_some": {"avg10": 0.0, "avg60": 0.0, "avg300": 0.0, "total": 0},
    "psi_memory_full": {"avg10": 0.0, "avg60": 0.0, "avg300": 0.0, "total": 0},
    "psi_io_some": {"avg10": 0.0, "avg60": 0.0, "avg300": 0.0, "total": 0},
}

_NULL_UNIT: dict[str, Any] = {
    "cpu_max": None,
    "cpu_weight": None,
    "cpu_stat": None,
    "memory_current_mb": None,
    "memory_high_mb": None,
    "memory_max_mb": None,
    "memory_events": None,
    "io_stat": None,
    "pids_current": None,
    "psi_cpu_some": None,
    "psi_memory_some": None,
    "psi_memory_full": None,
    "psi_io_some": None,
}


def _with(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Deep-copied base with a nested patch applied (selftest only)."""
    out = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _with(out[key], value)
        else:
            out[key] = value
    return out


def _row(
    uptime_s: float,
    system: dict[str, Any] | None,
    critical: dict[str, Any] | None,
    neighbor: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "ts": "selftest",
        "uptime_s": uptime_s,
        "system": system,
        "cgroups": {UNIT_CRITICAL: critical, UNIT_NEIGHBOR: neighbor},
    }


def _selftest_cases() -> list[tuple[str, Any, Any, str, str | None]]:
    """(name, prev, cur, expected_action, expected_target)."""
    quiet_prev = _row(100.0, _QUIET_SYSTEM, _QUIET_CRITICAL, _QUIET_NEIGHBOR)
    quiet_cur = _row(102.0, _QUIET_SYSTEM, _QUIET_CRITICAL, _QUIET_NEIGHBOR)

    cpu_prev = _row(
        200.0,
        _with(_QUIET_SYSTEM, {"psi_cpu_some": {"avg10": 30.0}}),
        _QUIET_CRITICAL,
        _QUIET_NEIGHBOR,
    )
    cpu_cur = _row(
        202.0,
        _with(_QUIET_SYSTEM, {"psi_cpu_some": {"avg10": 45.0}}),
        _QUIET_CRITICAL,
        _with(
            _QUIET_NEIGHBOR,
            {
                "cpu_stat": {"throttled_usec": 5_000_000},
                "psi_cpu_some": {"avg10": 70.0},
            },
        ),
    )

    crit_alone_cur = _row(
        302.0,
        _with(_QUIET_SYSTEM, {"psi_cpu_some": {"avg10": 20.0}}),
        _with(
            _QUIET_CRITICAL,
            {
                "cpu_stat": {"throttled_usec": 2_000_000},
                "psi_cpu_some": {"avg10": 15.0},
            },
        ),
        _with(_QUIET_NEIGHBOR, {"psi_cpu_some": {"avg10": 1.0}}),
    )

    protect_cur = _row(
        402.0,
        _with(_QUIET_SYSTEM, {"psi_cpu_some": {"avg10": 50.0}}),
        _with(_QUIET_CRITICAL, {"psi_cpu_some": {"avg10": 9.0}}),
        _with(
            _QUIET_NEIGHBOR,
            {
                "cpu_stat": {"throttled_usec": 3_000_000},
                "psi_cpu_some": {"avg10": 70.0},
            },
        ),
    )

    both_pinned_cur = _row(
        502.0,
        _with(_QUIET_SYSTEM, {"psi_cpu_some": {"avg10": 60.0}}),
        _with(_QUIET_CRITICAL, {"cpu_stat": {"throttled_usec": 3_000_000}}),
        _with(_QUIET_NEIGHBOR, {"cpu_stat": {"throttled_usec": 3_000_000}}),
    )

    memory_prev = _row(
        600.0,
        _QUIET_SYSTEM,
        _QUIET_CRITICAL,
        _with(_QUIET_NEIGHBOR, {"memory_current_mb": 100.0}),
    )
    memory_cur = _row(
        602.0,
        _QUIET_SYSTEM,
        _QUIET_CRITICAL,
        _with(_QUIET_NEIGHBOR, {"memory_current_mb": 190.0}),
    )
    memory_edge_cur = _row(
        602.0,
        _QUIET_SYSTEM,
        _QUIET_CRITICAL,
        _with(_QUIET_NEIGHBOR, {"memory_current_mb": 180.0}),
    )
    crit_memory_cur = _row(
        602.0,
        _QUIET_SYSTEM,
        _with(_QUIET_CRITICAL, {"memory_current_mb": 112.0}),
        _QUIET_NEIGHBOR,
    )
    memory_events_prev = _row(
        600.0,
        _QUIET_SYSTEM,
        _QUIET_CRITICAL,
        _with(
            _QUIET_NEIGHBOR,
            {"memory_current_mb": 170.0, "memory_events": {"high": 0}},
        ),
    )
    memory_events_cur = _row(
        602.0,
        _QUIET_SYSTEM,
        _QUIET_CRITICAL,
        _with(
            _QUIET_NEIGHBOR,
            {"memory_current_mb": 165.0, "memory_events": {"high": 40}},
        ),
    )
    memory_released_prev = _row(
        700.0,
        _QUIET_SYSTEM,
        _QUIET_CRITICAL,
        _with(_QUIET_NEIGHBOR, {"memory_current_mb": 190.0}),
    )
    memory_released_cur = _row(
        702.0,
        _QUIET_SYSTEM,
        _QUIET_CRITICAL,
        _with(_QUIET_NEIGHBOR, {"memory_current_mb": 8.0}),
    )

    io_cur = _row(
        802.0,
        _with(
            _QUIET_SYSTEM,
            {"psi_io_some": {"avg10": 0.30, "avg60": 0.20, "avg300": 0.10, "total": 0}},
        ),
        _QUIET_CRITICAL,
        _with(
            _QUIET_NEIGHBOR,
            {
                "io_stat": {"wbytes": 6_000_000},
                "psi_io_some": {"avg10": 0.35, "avg60": 0.20, "avg300": 0.10, "total": 0},
            },
        ),
    )

    pids_cur = _row(
        902.0,
        _QUIET_SYSTEM,
        _QUIET_CRITICAL,
        _with(_QUIET_NEIGHBOR, {"pids_current": 6}),
    )

    cpu_released_prev = _row(
        1000.0,
        _with(_QUIET_SYSTEM, {"psi_cpu_some": {"avg10": 40.0}}),
        _QUIET_CRITICAL,
        _with(_QUIET_NEIGHBOR, {"psi_cpu_some": {"avg10": 60.0}}),
    )
    cpu_released_cur = _row(
        1002.0,
        _with(_QUIET_SYSTEM, {"psi_cpu_some": {"avg10": 0.5}}),
        _QUIET_CRITICAL,
        _with(_QUIET_NEIGHBOR, {"psi_cpu_some": {"avg10": 0.4}}),
    )

    max_event_cur = _row(
        1102.0,
        _QUIET_SYSTEM,
        _QUIET_CRITICAL,
        _with(
            _QUIET_NEIGHBOR,
            {"memory_current_mb": 240.0, "memory_events": {"max": 1}},
        ),
    )
    oom_kill_cur = _row(
        1202.0,
        _QUIET_SYSTEM,
        _QUIET_CRITICAL,
        _with(
            _QUIET_NEIGHBOR,
            {"memory_current_mb": 230.0, "memory_events": {"oom_kill": 1}},
        ),
    )

    lost_cur = _row(1302.0, _QUIET_SYSTEM, _QUIET_CRITICAL, None)
    both_lost_cur = _row(1402.0, _QUIET_SYSTEM, None, None)
    blank_cur = _row(1502.0, _BLANK_SYSTEM, None, None)
    started_cur = _row(1602.0, _QUIET_SYSTEM, _QUIET_CRITICAL, _QUIET_NEIGHBOR)
    null_prev = _row(1700.0, _QUIET_SYSTEM, _NULL_UNIT, _NULL_UNIT)
    null_cur = _row(1702.0, _QUIET_SYSTEM, _NULL_UNIT, _NULL_UNIT)
    garbage_cur = _row(
        1802.0,
        _QUIET_SYSTEM,
        _QUIET_CRITICAL,
        _with(
            _QUIET_NEIGHBOR,
            {
                "memory_current_mb": "max",
                "pids_current": float("nan"),
                "cpu_stat": {"throttled_usec": float("inf")},
                "psi_cpu_some": {"avg10": "junk"},
                "memory_events": {"high": "many"},
            },
        ),
    )

    return [
        ("cold_start_no_prev_row", {}, quiet_cur, ACTION_DO_NOTHING, None),
        ("idle_pair_is_do_nothing", quiet_prev, quiet_cur, ACTION_DO_NOTHING, None),
        (
            "neighbor_throttled_under_system_pressure",
            cpu_prev,
            cpu_cur,
            ACTION_INCREASE_CPU,
            UNIT_NEIGHBOR,
        ),
        (
            "critical_throttled_alone",
            _row(300.0, _QUIET_SYSTEM, _QUIET_CRITICAL, _QUIET_NEIGHBOR),
            crit_alone_cur,
            ACTION_INCREASE_CPU,
            UNIT_CRITICAL,
        ),
        (
            "protect_service_when_critical_pressured",
            _row(
                400.0,
                _with(_QUIET_SYSTEM, {"psi_cpu_some": {"avg10": 20.0}}),
                _with(_QUIET_CRITICAL, {"psi_cpu_some": {"avg10": 1.0}}),
                _QUIET_NEIGHBOR,
            ),
            protect_cur,
            ACTION_PROTECT_SERVICE,
            TARGET_BOTH,
        ),
        (
            "both_pinned_is_alert_not_isolate",
            _row(500.0, _QUIET_SYSTEM, _QUIET_CRITICAL, _QUIET_NEIGHBOR),
            both_pinned_cur,
            ACTION_ALERT_OPERATOR,
            TARGET_BOTH,
        ),
        (
            "memory_near_high_increases_memory",
            memory_prev,
            memory_cur,
            ACTION_INCREASE_MEMORY,
            UNIT_NEIGHBOR,
        ),
        (
            "memory_at_exact_high_threshold",
            memory_prev,
            memory_edge_cur,
            ACTION_INCREASE_MEMORY,
            UNIT_NEIGHBOR,
        ),
        (
            "critical_memory_near_high",
            _row(
                600.0,
                _QUIET_SYSTEM,
                _with(_QUIET_CRITICAL, {"memory_current_mb": 20.0}),
                _QUIET_NEIGHBOR,
            ),
            crit_memory_cur,
            ACTION_INCREASE_MEMORY,
            UNIT_CRITICAL,
        ),
        (
            "memory_high_events_growth_counts_as_pressure",
            memory_events_prev,
            memory_events_cur,
            ACTION_INCREASE_MEMORY,
            UNIT_NEIGHBOR,
        ),
        (
            "memory_released_decreases_memory",
            memory_released_prev,
            memory_released_cur,
            ACTION_DECREASE_MEMORY,
            UNIT_NEIGHBOR,
        ),
        (
            "fast_writes_throttle_io",
            _row(800.0, _QUIET_SYSTEM, _QUIET_CRITICAL, _QUIET_NEIGHBOR),
            io_cur,
            ACTION_THROTTLE_IO,
            UNIT_NEIGHBOR,
        ),
        (
            "pids_spike_restricts_process_count",
            _row(900.0, _QUIET_SYSTEM, _QUIET_CRITICAL, _QUIET_NEIGHBOR),
            pids_cur,
            ACTION_RESTRICT_PROCESS_COUNT,
            UNIT_NEIGHBOR,
        ),
        (
            "cpu_pressure_released_decreases_cpu",
            cpu_released_prev,
            cpu_released_cur,
            ACTION_DECREASE_CPU,
            UNIT_NEIGHBOR,
        ),
        (
            "memory_max_event_alerts",
            _row(1100.0, _QUIET_SYSTEM, _QUIET_CRITICAL, _QUIET_NEIGHBOR),
            max_event_cur,
            ACTION_ALERT_OPERATOR,
            UNIT_NEIGHBOR,
        ),
        (
            "oom_kill_alerts",
            _row(1200.0, _QUIET_SYSTEM, _QUIET_CRITICAL, _QUIET_NEIGHBOR),
            oom_kill_cur,
            ACTION_ALERT_OPERATOR,
            UNIT_NEIGHBOR,
        ),
        (
            "unit_telemetry_lost_alerts",
            quiet_prev,
            lost_cur,
            ACTION_ALERT_OPERATOR,
            UNIT_NEIGHBOR,
        ),
        (
            "both_units_lost_alerts_both",
            quiet_prev,
            both_lost_cur,
            ACTION_ALERT_OPERATOR,
            TARGET_BOTH,
        ),
        (
            "blank_sampler_row_alerts",
            quiet_prev,
            blank_cur,
            ACTION_ALERT_OPERATOR,
            None,
        ),
        (
            "no_current_state_alerts",
            quiet_prev,
            {},
            ACTION_ALERT_OPERATOR,
            None,
        ),
        (
            "null_heavy_rows_are_do_nothing",
            null_prev,
            null_cur,
            ACTION_DO_NOTHING,
            None,
        ),
        (
            "unit_first_appearance_is_do_nothing",
            _row(1600.0, _QUIET_SYSTEM, _QUIET_CRITICAL, None),
            started_cur,
            ACTION_DO_NOTHING,
            None,
        ),
        (
            "garbage_fields_are_ignored",
            _row(1800.0, _QUIET_SYSTEM, _QUIET_CRITICAL, _QUIET_NEIGHBOR),
            garbage_cur,
            ACTION_DO_NOTHING,
            None,
        ),
    ]


def _decision_is_valid(decision: Any) -> bool:
    """Full contract check, including the forbidden-action safety promise."""
    if not isinstance(decision, dict) or set(decision) != {"action", "target", "reason", "confidence"}:
        return False
    if decision["action"] not in ACTIONS or decision["action"] in FORBIDDEN_AUTOMATIC:
        return False
    if decision["target"] not in TARGETS:
        return False
    if not isinstance(decision["reason"], str) or not decision["reason"]:
        return False
    confidence = decision["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, float):
        return False
    return 0.0 <= confidence <= 1.0


def _fuzzify(value: Any, rng: random.Random, pool: tuple[Any, ...]) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if rng.random() < 0.05:
                continue
            out[key] = _fuzzify(item, rng, pool)
        return out
    if isinstance(value, list):
        return list(value)
    return rng.choice(pool) if rng.random() < 0.30 else value


def _fuzz_row(rng: random.Random, pool: tuple[Any, ...]) -> Any:
    """A schema-shaped row full of noise; sometimes the whole row is junk."""
    roll = rng.random()
    if roll < 0.04:
        return rng.choice((None, "garbage", 42, [], {}))
    row: dict[str, Any] = {"ts": "fuzz", "uptime_s": rng.choice((None, 0.0, 2.0, 2.4, 1e9, "x"))}
    if rng.random() >= 0.05:
        row["system"] = _fuzzify(_QUIET_SYSTEM, rng, pool)
    if rng.random() >= 0.05:
        row["cgroups"] = {
            UNIT_CRITICAL: None if rng.random() < 0.20 else _fuzzify(_QUIET_CRITICAL, rng, pool),
            UNIT_NEIGHBOR: None if rng.random() < 0.20 else _fuzzify(_QUIET_NEIGHBOR, rng, pool),
        }
    return row


def _fuzz_check(pairs: int) -> list[str]:
    """Garbage in must never crash, break the contract, or mutate inputs."""
    rng = random.Random(FUZZ_SEED)
    pool: tuple[Any, ...] = (
        None,
        0,
        1,
        2,
        3,
        7,
        64,
        500_000,
        5_000_000,
        0.0,
        0.35,
        120.0,
        199.5,
        7000.0,
        -1.0,
        1e12,
        "max",
        "",
        "junk",
        float("nan"),
        float("inf"),
        True,
    )
    problems: list[str] = []
    for index in range(pairs):
        prev = _fuzz_row(rng, pool)
        cur = _fuzz_row(rng, pool)
        prev_before = json.dumps(prev, sort_keys=True, default=str)
        cur_before = json.dumps(cur, sort_keys=True, default=str)
        try:
            decision = decide(prev, cur)
        except Exception as error:  # a teacher must never crash on garbage
            problems.append("fuzz pair %d raised %r" % (index, error))
            if len(problems) >= 10:
                break
            continue
        if not _decision_is_valid(decision):
            problems.append("fuzz pair %d invalid decision %r" % (index, decision))
        if (
            json.dumps(prev, sort_keys=True, default=str) != prev_before
            or json.dumps(cur, sort_keys=True, default=str) != cur_before
        ):
            problems.append("fuzz pair %d mutated its inputs" % index)
        if len(problems) >= 10:
            problems.append("stopping after 10 fuzz problems")
            break
    return problems


def _run_selftests() -> int:
    failures: list[str] = []
    seen_actions: set[str] = set()
    cases = _selftest_cases()
    for name, prev, cur, expected_action, expected_target in cases:
        decision = decide(prev, cur)
        seen_actions.add(decision["action"])
        problems: list[str] = []
        if not _decision_is_valid(decision):
            problems.append("invalid decision shape")
        if decision["action"] != expected_action:
            problems.append("action %s != expected %s" % (decision["action"], expected_action))
        if decision["target"] != expected_target:
            problems.append("target %s != expected %s" % (decision["target"], expected_target))
        if problems:
            failures.append("%s: %s" % (name, "; ".join(problems)))
            print(
                "FAIL %-44s -> %s/%s (expected %s/%s) %s"
                % (
                    name,
                    decision["action"],
                    decision["target"],
                    expected_action,
                    expected_target,
                    decision["reason"],
                )
            )
        else:
            print(
                "PASS %-44s -> %-22s %-13s conf=%.2f %s"
                % (
                    name,
                    decision["action"],
                    str(decision["target"]),
                    decision["confidence"],
                    decision["reason"],
                )
            )

    missing = set(REACHABLE_ACTIONS) - seen_actions
    if missing:
        failures.append("actions never exercised: " + ", ".join(sorted(missing)))

    for problem in _fuzz_check(FUZZ_PAIRS):
        failures.append("fuzz: " + problem)

    print("selftest: %d crafted cases, %d fuzz pairs" % (len(cases), FUZZ_PAIRS))
    if failures:
        print("selftest FAILED (%d problem(s)):" % len(failures))
        for failure in failures:
            print("  - %s" % failure)
        return 1
    print("selftest OK")
    return 0


# ------------------------------------------------------------------ preview
def _preview(path: str) -> int:
    """Print one decision line per consecutive row pair of a telemetry JSONL file."""
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError as error:
        print("error: cannot read %s: %s" % (path, error), file=sys.stderr)
        return 1

    rows: list[Any] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as error:
            print("warn: skipping line %d: %s" % (line_number, error), file=sys.stderr)

    count = 0
    for index in range(1, len(rows)):
        decision = decide(rows[index - 1], rows[index])
        ts = _dict(rows[index]).get("ts")
        target = decision["target"] if decision["target"] is not None else "-"
        print(
            "%s %-22s %-13s conf=%.2f %s"
            % (ts, decision["action"], target, decision["confidence"], decision["reason"])
        )
        count += 1
    print("preview: %d decisions from %d rows" % (count, len(rows)), file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="WorkloadPilot M1 rules: pure decision teacher.")
    parser.add_argument("--selftest", action="store_true", help="run crafted cases + seeded fuzz")
    parser.add_argument("--file", dest="file_path", metavar="JSONL", help="preview decisions over telemetry")
    args = parser.parse_args()
    if args.selftest:
        return _run_selftests()
    if args.file_path:
        return _preview(args.file_path)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
