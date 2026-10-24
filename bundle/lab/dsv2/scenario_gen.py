#!/usr/bin/env python3
"""WorkloadPilot dataset-v2 scenario generator (deterministic per --seed).

Draws one scenario: victim type, neighbor cgroup limits, warmup/cooldown,
2-5 load phases with gaps, plus for a fraction of seeds either a hard-negative
"brief spike then quiet" run or a mem_grow phase pushing toward memory.high.

Every duration written to the file is already multiplied by --time-scale, every
memory budget in MB is multiplied by --mem-scale, and the total
(warmup + phases + gaps + cooldown) is enforced to land in [150, 300] s, so the
emitted file can be executed as-is.
"""

import argparse
import json
import math
import random
from typing import Any

VICTIM_CPU_QUOTA_PCT = 100
VICTIM_MEMORY_MAX_MB = 256
NEIGHBOR_CPU_QUOTA_CHOICES = (25, 50, 100, 150, 200, 300, 400)
NEIGHBOR_HIGH_MB_RANGE = (64, 1024)
NEIGHBOR_MAX_EXTRA_MB_RANGE = (50, 150)
MEM_HIGH_FLOOR_MB = 128  # --mem-scale never pushes memory.high below this
MEM_MAX_GAP_MB = 64  # memory.max stays at least this far above memory.high
MEM_TARGET_FLOOR_MB = 64  # --mem-scale never pushes a phase memory target below this
VICTIM_MEMORY_MAX_FLOOR_MB = 64  # the victim stays runnable on tiny machines
IO_CAP_MBPS_RANGE = (1, 8)
PIDS_MAX_RANGE = (32, 256)
MEM_PATTERNS = ("step", "ramp", "spike", "sawtooth")
PHASE_TYPES = ("cpu_burn", "mem_grow", "io_write", "fork_light", "mixed")
MIXED_PART_TYPES = ("cpu_burn", "mem_grow", "io_write")
SPIKE_TYPES = ("cpu_burn", "mem_grow")
FORK_LIGHT_RATES = (5, 8, 12, 20, 30, 50)
PAD_FORK_RATES = (1, 2, 3)
PAD_IO_MBPS = (1, 2)
HARD_NEGATIVE_PROB = 0.18
MEM_PRESSURE_PROB = 0.35
WARMUP_S_RANGE = (10, 15)
COOLDOWN_S_RANGE = (15, 30)
PHASE_COUNT_RANGE = (2, 5)
GAP_S_RANGE = (0, 15)
TOTAL_S_RANGE = (150, 300)
FIT_TOTAL_S_RANGE = (190, 280)
MIN_PHASE_S = 5
FIT_ATTEMPTS = 25


class InfeasibleTimeline(Exception):
    """The drawn structure cannot be fitted into the required total."""


def phase_seconds(phase: dict[str, Any]) -> int:
    if phase["type"] == "spike_resolve":
        return int(phase["spike_s"]) + int(phase["quiet_s"])
    return int(phase["duration_s"])


def set_phase_seconds(phase: dict[str, Any], seconds: int) -> None:
    if phase["type"] == "spike_resolve":
        spike_s = max(1, min(int(phase["spike_s"]), seconds - 1))
        phase["spike_s"] = spike_s
        phase["quiet_s"] = max(1, seconds - spike_s)
    else:
        phase["duration_s"] = max(MIN_PHASE_S, seconds)


def scenario_total_s(scenario: dict[str, Any]) -> int:
    return (
        int(scenario["warmup_s"])
        + int(scenario["cooldown_s"])
        + sum(phase_seconds(phase) + int(phase["gap_s"]) for phase in scenario["phases"])
    )


def draw_neighbor(rng: random.Random) -> dict[str, Any]:
    high_mb = rng.randint(*NEIGHBOR_HIGH_MB_RANGE)
    return {
        "cpu_quota_pct": rng.choice(NEIGHBOR_CPU_QUOTA_CHOICES),
        "memory_high_mb": high_mb,
        "memory_max_mb": high_mb + rng.randint(*NEIGHBOR_MAX_EXTRA_MB_RANGE),
        "io_cap_mbps": None if rng.random() < 0.5 else rng.randint(*IO_CAP_MBPS_RANGE),
        "pids_max": None if rng.random() < 0.5 else rng.randint(*PIDS_MAX_RANGE),
    }


def draw_mem_target(rng: random.Random, neighbor: dict[str, Any]) -> int:
    high_mb = int(neighbor["memory_high_mb"])
    low = max(64, int(high_mb * 0.40))
    high = max(low, int(high_mb * 0.95))
    return rng.randint(low, high)


def draw_pressure_target(rng: random.Random, neighbor: dict[str, Any]) -> int:
    """Target inside 90-105% of memory.high, clamped below memory.max."""
    high_mb = int(neighbor["memory_high_mb"])
    target = int(round(high_mb * rng.uniform(0.90, 1.05)))
    return max(16, min(target, int(neighbor["memory_max_mb"]) - 16))


def draw_phase(rng: random.Random, neighbor: dict[str, Any]) -> dict[str, Any]:
    kind = rng.choice(PHASE_TYPES)
    if kind == "cpu_burn":
        return {"type": kind, "procs": rng.randint(1, 4), "duration_s": rng.randint(25, 45)}
    if kind == "mem_grow":
        return {
            "type": kind,
            "target_mb": draw_mem_target(rng, neighbor),
            "pattern": rng.choice(MEM_PATTERNS),
            "duration_s": rng.randint(30, 55),
        }
    if kind == "io_write":
        return {"type": kind, "rate_mbps": rng.randint(2, 10), "duration_s": rng.randint(25, 45)}
    if kind == "fork_light":
        return {"type": kind, "procs_per_s": rng.choice(FORK_LIGHT_RATES), "duration_s": rng.randint(20, 40)}
    return {
        "type": kind,
        "parts": rng.sample(MIXED_PART_TYPES, k=rng.randint(2, 3)),
        "duration_s": rng.randint(30, 60),
    }


def draw_benign_pad(rng: random.Random) -> dict[str, Any]:
    """Light background load used to pad hard-negative runs to the time budget."""
    if rng.random() < 0.5:
        return {"type": "fork_light", "procs_per_s": rng.choice(PAD_FORK_RATES), "duration_s": rng.randint(30, 45)}
    return {"type": "io_write", "rate_mbps": rng.choice(PAD_IO_MBPS), "duration_s": rng.randint(30, 45)}


def apply_memory_pressure(rng: random.Random, phases: list[dict[str, Any]], neighbor: dict[str, Any]) -> None:
    """p ~= 0.35: one mem workload targets 90-105% of memory.high."""
    candidates = [phase for phase in phases if phase["type"] == "mem_grow"]
    if not candidates:
        convertible = [phase for phase in phases if phase["type"] != "spike_resolve"]
        if not convertible:
            return
        chosen = rng.choice(convertible)
        chosen.clear()
        chosen.update({"type": "mem_grow", "pattern": rng.choice(MEM_PATTERNS), "duration_s": 30})
    else:
        chosen = rng.choice(candidates)
    chosen["target_mb"] = draw_pressure_target(rng, neighbor)


def draw_phases(rng: random.Random, neighbor: dict[str, Any], hard_negative: bool, body_min_s: int) -> list[dict[str, Any]]:
    if hard_negative:
        spike = {
            "type": "spike_resolve",
            "spike_type": rng.choice(SPIKE_TYPES),
            "spike_s": rng.randint(10, 15),
            "quiet_s": rng.randint(35, 50),
        }
        phases: list[dict[str, Any]] = [spike]
        remaining_s = body_min_s - phase_seconds(spike)
        pad_count = min(PHASE_COUNT_RANGE[1] - 1, max(1, math.ceil(remaining_s / 40.0))) if remaining_s > 0 else 0
        for _ in range(pad_count):
            phases.append(draw_benign_pad(rng))
        return phases
    phases = [draw_phase(rng, neighbor) for _ in range(rng.randint(*PHASE_COUNT_RANGE))]
    if rng.random() < MEM_PRESSURE_PROB:
        apply_memory_pressure(rng, phases, neighbor)
    return phases


def assign_gaps(rng: random.Random, phases: list[dict[str, Any]]) -> None:
    for index, phase in enumerate(phases):
        phase["gap_s"] = 0 if index == len(phases) - 1 else rng.randint(*GAP_S_RANGE)


def fit_proportional(
    phases: list[dict[str, Any]],
    warmup_s: int,
    cooldown_s: int,
    target_total_s: int,
    scalable_indices: list[int],
) -> None:
    """Scale the scalable phases' durations and gaps so the timeline hits target_total_s."""
    scalable = set(scalable_indices)
    fixed_s = warmup_s + cooldown_s
    for index, phase in enumerate(phases):
        if index not in scalable:
            fixed_s += phase_seconds(phase) + int(phase["gap_s"])
    spans = [phase_seconds(phases[index]) for index in scalable_indices]
    gaps = [int(phases[index]["gap_s"]) for index in scalable_indices]
    movable_s = sum(spans) + sum(gaps)
    room_s = target_total_s - fixed_s
    if movable_s <= 0 or room_s < len(scalable_indices) * MIN_PHASE_S:
        raise InfeasibleTimeline("no room for %d scalable phases in %ds" % (len(scalable_indices), target_total_s))
    factor = room_s / movable_s
    new_spans = [max(MIN_PHASE_S, int(round(span * factor))) for span in spans]
    new_gaps = [max(0, int(round(gap * factor))) for gap in gaps]
    overflow_s = (fixed_s + sum(new_spans) + sum(new_gaps)) - target_total_s
    new_spans[-1] = max(MIN_PHASE_S, new_spans[-1] - overflow_s)
    for phase_index, span_s, gap_s in zip(scalable_indices, new_spans, new_gaps):
        set_phase_seconds(phases[phase_index], span_s)
        phases[phase_index]["gap_s"] = gap_s


def scale_seconds(value: int, time_scale: float, minimum: int) -> int:
    return max(minimum, int(round(value * time_scale)))


def scale_scenario(scenario: dict[str, Any], time_scale: float) -> dict[str, Any]:
    if time_scale == 1.0:
        return scenario
    phases = []
    for phase in scenario["phases"]:
        scaled = dict(phase)
        if scaled["type"] == "spike_resolve":
            scaled["spike_s"] = scale_seconds(scaled["spike_s"], time_scale, 1)
            scaled["quiet_s"] = scale_seconds(scaled["quiet_s"], time_scale, 1)
        else:
            scaled["duration_s"] = scale_seconds(scaled["duration_s"], time_scale, 1)
        scaled["gap_s"] = scale_seconds(scaled["gap_s"], time_scale, 0)
        phases.append(scaled)
    return {
        **scenario,
        "warmup_s": scale_seconds(scenario["warmup_s"], time_scale, 1),
        "cooldown_s": scale_seconds(scenario["cooldown_s"], time_scale, 1),
        "phases": phases,
    }


def scale_mb(value_mb: float, mem_scale: float, floor_mb: int) -> int:
    return max(floor_mb, int(round(value_mb * mem_scale)))


def apply_mem_scale(scenario: dict[str, Any], mem_scale: float) -> dict[str, Any]:
    """Multiply every memory budget in the drawn scenario, keeping the floors.

    At mem_scale 1.0 this returns the scenario object untouched, so the emitted
    JSON is byte-identical to a generator without --mem-scale.
    """
    if mem_scale == 1.0:
        return scenario
    neighbor = dict(scenario["neighbor"])
    neighbor["memory_high_mb"] = scale_mb(neighbor["memory_high_mb"], mem_scale, MEM_HIGH_FLOOR_MB)
    neighbor["memory_max_mb"] = scale_mb(
        neighbor["memory_max_mb"], mem_scale, neighbor["memory_high_mb"] + MEM_MAX_GAP_MB
    )
    victim = dict(scenario["victim"])
    victim["memory_max_mb"] = scale_mb(victim["memory_max_mb"], mem_scale, VICTIM_MEMORY_MAX_FLOOR_MB)
    phases = []
    for phase in scenario["phases"]:
        if "target_mb" in phase:
            phase = {**phase, "target_mb": scale_mb(phase["target_mb"], mem_scale, MEM_TARGET_FLOOR_MB)}
        phases.append(phase)
    return {**scenario, "victim": victim, "neighbor": neighbor, "phases": phases}


def draw_scenario(rng: random.Random, seed: int, time_scale: float) -> dict[str, Any]:
    fit_low_s = math.ceil(FIT_TOTAL_S_RANGE[0] / time_scale)
    fit_high_s = math.floor(FIT_TOTAL_S_RANGE[1] / time_scale)
    if fit_high_s - fit_low_s < MIN_PHASE_S:
        raise ValueError("time-scale %g is outside the supported range" % time_scale)

    victim_type = "latency" if rng.random() < 0.5 else "throughput"
    neighbor = draw_neighbor(rng)
    warmup_s = rng.randint(*WARMUP_S_RANGE)
    cooldown_s = rng.randint(*COOLDOWN_S_RANGE)
    hard_negative = rng.random() < HARD_NEGATIVE_PROB
    target_total_s = rng.randint(fit_low_s, fit_high_s)
    body_min_s = max(MIN_PHASE_S, target_total_s - warmup_s - cooldown_s - GAP_S_RANGE[1])

    phases = draw_phases(rng, neighbor, hard_negative, body_min_s)
    assign_gaps(rng, phases)
    # A hard-negative spike keeps its drawn 10-15s length; only benign pads are resized.
    scalable_indices = [index for index, phase in enumerate(phases) if phase["type"] != "spike_resolve"]
    total_s = warmup_s + cooldown_s + sum(phase_seconds(phase) + int(phase["gap_s"]) for phase in phases)
    if total_s < fit_low_s or total_s > fit_high_s:
        fit_proportional(phases, warmup_s, cooldown_s, target_total_s, scalable_indices)

    scenario = {
        "seed": seed,
        "victim_type": victim_type,
        "victim": {"cpu_quota_pct": VICTIM_CPU_QUOTA_PCT, "memory_max_mb": VICTIM_MEMORY_MAX_MB},
        "neighbor": neighbor,
        "warmup_s": warmup_s,
        "cooldown_s": cooldown_s,
        "phases": phases,
        "controller_mode": "explore" if rng.random() < 0.5 else "rules",
    }
    scenario = scale_scenario(scenario, time_scale)
    scaled_total_s = scenario_total_s(scenario)
    if scaled_total_s < TOTAL_S_RANGE[0] or scaled_total_s > TOTAL_S_RANGE[1]:
        raise InfeasibleTimeline("scaled total %ds outside %s" % (scaled_total_s, TOTAL_S_RANGE))
    return scenario


def generate(seed: int, time_scale: float, mem_scale: float) -> dict[str, Any]:
    rng = random.Random(seed)
    for _ in range(FIT_ATTEMPTS):
        try:
            scenario = draw_scenario(rng, seed, time_scale)
        except InfeasibleTimeline:
            continue
        return apply_mem_scale(scenario, mem_scale)
    raise RuntimeError("could not fit a scenario for seed %d at time-scale %g" % (seed, time_scale))


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate one WorkloadPilot dataset-v2 scenario.")
    parser.add_argument("--seed", type=int, required=True, help="deterministic seed")
    parser.add_argument("--out", required=True, help="output scenario JSON path")
    parser.add_argument("--time-scale", type=float, default=1.0, help="multiply every duration (default: 1.0)")
    parser.add_argument("--mem-scale", type=float, default=1.0, help="multiply every memory budget in MB (default: 1.0)")
    args = parser.parse_args()
    if args.time_scale <= 0:
        parser.error("--time-scale must be > 0")
    if args.mem_scale <= 0:
        parser.error("--mem-scale must be > 0")

    scenario = generate(args.seed, args.time_scale, args.mem_scale)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(scenario, handle, indent=2)
        handle.write("\n")
    print(
        "wrote %s seed=%d victim=%s hard_negative=%s total=%ds phases=%d"
        % (
            args.out,
            scenario["seed"],
            scenario["victim_type"],
            any(phase["type"] == "spike_resolve" for phase in scenario["phases"]),
            scenario_total_s(scenario),
            len(scenario["phases"]),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
