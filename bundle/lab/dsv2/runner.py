#!/usr/bin/env python3
"""WorkloadPilot dataset-v2 run orchestrator: one scenario -> one run directory.

Starts the sampler (and controller unless mode is none), runs the victim unit
and the neighbor unit through the scenario timeline, writes phases.log and
meta.json, and always cleans up units and helper processes in a finally block.
"""

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(HERE)
PYTHON = sys.executable
SAMPLER = os.path.join(BASE_DIR, "sampler.py")
STRESSOR = os.path.join(HERE, "stressor.py")
CONTROLLER = os.path.join(HERE, "controller.py")
VICTIM_SCRIPTS = {
    "latency": os.path.join(HERE, "victim_latency.py"),
    "throughput": os.path.join(HERE, "victim_throughput.py"),
}
CRITICAL_UNIT = "wlp-critical"
NEIGHBOR_UNIT = "wlp-neighbor"
SLICE = "wlp.slice"
CGROUP_ROOT = "/sys/fs/cgroup/wlp.slice"
IO_DEVICE = "8:48"
MIB = 1048576
SPIKE_CPU_PROCS = 4
MIXED_CPU_PROCS = 2
MIXED_IO_MBPS = 4
STOP_GRACE_S = 5.0
VALID_PHASE_TYPES = ("cpu_burn", "mem_grow", "io_write", "fork_light", "mixed", "spike_resolve")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def scale_seconds(value: float, time_scale: float) -> float:
    return round(value * time_scale, 3)


def fmt_seconds(value: float) -> str:
    return "%g" % value


def load_scenario(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        scenario = json.load(handle)
    for key in ("seed", "victim_type", "victim", "neighbor", "warmup_s", "cooldown_s", "phases"):
        if key not in scenario:
            raise ValueError("scenario missing key %r" % key)
    if scenario["victim_type"] not in VICTIM_SCRIPTS:
        raise ValueError("unknown victim_type %r" % scenario["victim_type"])
    if not scenario["phases"]:
        raise ValueError("scenario has no phases")
    for phase in scenario["phases"]:
        if phase["type"] not in VALID_PHASE_TYPES:
            raise ValueError("unknown phase type %r" % phase["type"])
    return scenario


def phase_seconds(phase: dict[str, Any], time_scale: float) -> float:
    if phase["type"] == "spike_resolve":
        return scale_seconds(phase["spike_s"], time_scale) + scale_seconds(phase["quiet_s"], time_scale)
    return scale_seconds(phase["duration_s"], time_scale)


def mixed_items(phase: dict[str, Any], neighbor: dict[str, Any], iofile: str) -> list[dict[str, Any]]:
    items = []
    for part in phase["parts"]:
        if part == "cpu_burn":
            items.append({"type": "cpu_burn", "procs": MIXED_CPU_PROCS})
        elif part == "mem_grow":
            items.append({"type": "mem_grow", "target_mb": int(neighbor["memory_high_mb"]), "pattern": "step"})
        elif part == "io_write":
            items.append({"type": "io_write", "rate_mbps": MIXED_IO_MBPS, "iofile": iofile})
        else:
            raise ValueError("unknown mixed part %r" % part)
    return items


def stressor_argv(phase: dict[str, Any], neighbor: dict[str, Any], iofile: str, time_scale: float) -> list[str]:
    """Stressors argv for one phase (spike_resolve -> the spike load only)."""
    kind = phase["type"]
    if kind == "spike_resolve":
        duration = fmt_seconds(scale_seconds(phase["spike_s"], time_scale))
        if phase["spike_type"] == "cpu_burn":
            return [STRESSOR, "cpu_burn", "--procs", str(SPIKE_CPU_PROCS), "--duration", duration]
        return [
            STRESSOR,
            "mem_grow",
            "--target-mb",
            str(int(neighbor["memory_high_mb"])),
            "--pattern",
            "step",
            "--duration",
            duration,
        ]
    if kind == "cpu_burn":
        return [STRESSOR, "cpu_burn", "--procs", str(phase["procs"]), "--duration", fmt_seconds(scale_seconds(phase["duration_s"], time_scale))]
    if kind == "mem_grow":
        return [
            STRESSOR,
            "mem_grow",
            "--target-mb",
            str(phase["target_mb"]),
            "--pattern",
            phase["pattern"],
            "--duration",
            fmt_seconds(scale_seconds(phase["duration_s"], time_scale)),
        ]
    if kind == "io_write":
        return [
            STRESSOR,
            "io_write",
            "--rate-mbps",
            str(phase["rate_mbps"]),
            "--iofile",
            iofile,
            "--duration",
            fmt_seconds(scale_seconds(phase["duration_s"], time_scale)),
        ]
    if kind == "fork_light":
        return [STRESSOR, "fork_light", "--procs-per-s", str(phase["procs_per_s"]), "--duration", fmt_seconds(scale_seconds(phase["duration_s"], time_scale))]
    if kind == "mixed":
        return [
            STRESSOR,
            "mixed",
            "--spec",
            json.dumps(mixed_items(phase, neighbor, iofile), separators=(",", ":")),
            "--duration",
            fmt_seconds(scale_seconds(phase["duration_s"], time_scale)),
        ]
    raise ValueError("unknown phase type %r" % kind)


def stressor_chain(phases: list[dict[str, Any]], neighbor: dict[str, Any], iofile: str, time_scale: float) -> str:
    """Single bash -c chain running every phase's stressor with gaps and quiet periods."""
    commands = []
    for phase in phases:
        argv = [PYTHON] + stressor_argv(phase, neighbor, iofile, time_scale)
        commands.append(" ".join(shlex.quote(token) for token in argv))
        if phase["type"] == "spike_resolve":
            commands.append("sleep " + fmt_seconds(scale_seconds(phase["quiet_s"], time_scale)))
        gap_s = int(phase.get("gap_s", 0))
        if gap_s > 0:
            commands.append("sleep " + fmt_seconds(scale_seconds(gap_s, time_scale)))
    return "; ".join(commands)


def sleep_until(deadline: float) -> None:
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(remaining)


def sleep_seconds(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def systemctl(*args: str) -> None:
    try:
        subprocess.run(["systemctl", *args], capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as error:
        print("warn: systemctl %s failed: %s" % (" ".join(args), error), file=sys.stderr)


def stop_unit(unit: str) -> None:
    systemctl("stop", unit + ".service")
    systemctl("reset-failed", unit + ".service")


def popen_logging(argv: list[str], log_path: str) -> subprocess.Popen:
    with open(log_path, "ab") as handle:
        return subprocess.Popen(argv, stdout=handle, stderr=subprocess.STDOUT)


def terminate_process(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=STOP_GRACE_S)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def systemd_run(argv: list[str], unit: str) -> None:
    result = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError("systemd-run %s failed: %s" % (unit, detail))


def start_victim(scenario: dict[str, Any], run_dir: str) -> None:
    script = VICTIM_SCRIPTS[scenario["victim_type"]]
    argv = [
        "systemd-run",
        "--collect",
        "--unit",
        CRITICAL_UNIT,
        "--slice",
        SLICE,
        "-p",
        "CPUQuota=%d%%" % int(scenario["victim"]["cpu_quota_pct"]),
        "-p",
        "MemoryMax=%dM" % int(scenario["victim"]["memory_max_mb"]),
        "-p",
        "IOAccounting=true",
        "--property",
        "WorkingDirectory=" + run_dir,
        PYTHON,
        script,
        "--out",
        os.path.join(run_dir, "victim.log"),
    ]
    systemd_run(argv, CRITICAL_UNIT)


def start_neighbor(scenario: dict[str, Any], run_dir: str, chain: str) -> None:
    limits = scenario["neighbor"]
    argv = [
        "systemd-run",
        "--collect",
        "--unit",
        NEIGHBOR_UNIT,
        "--slice",
        SLICE,
        "-p",
        "CPUQuota=%d%%" % int(limits["cpu_quota_pct"]),
        "-p",
        "MemoryHigh=%dM" % int(limits["memory_high_mb"]),
        "-p",
        "MemoryMax=%dM" % int(limits["memory_max_mb"]),
        "-p",
        "IOAccounting=true",
    ]
    if limits.get("pids_max") is not None:
        # TasksMax is the systemd property writing cgroup pids.max.
        argv += ["-p", "TasksMax=%d" % int(limits["pids_max"])]
    argv += ["--property", "WorkingDirectory=" + run_dir, "bash", "-c", chain]
    systemd_run(argv, NEIGHBOR_UNIT)


def wait_for_dir(path: str, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if os.path.isdir(path):
            return True
        time.sleep(0.1)
    return os.path.isdir(path)


def write_cgroup_file(path: str, value: str) -> None:
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(value)
    except OSError as error:
        print("warn: could not write %s: %s" % (path, error), file=sys.stderr)


def apply_cgroup_overrides(scenario: dict[str, Any]) -> None:
    """Best-effort io.max / pids.max writes after the neighbor unit is up."""
    limits = scenario["neighbor"]
    unit_dir = os.path.join(CGROUP_ROOT, NEIGHBOR_UNIT + ".service")
    if not wait_for_dir(unit_dir, 3.0):
        print("warn: neighbor cgroup %s not found; skipping io/pids overrides" % unit_dir, file=sys.stderr)
        return
    io_cap = limits.get("io_cap_mbps")
    if io_cap is not None:
        write_cgroup_file(os.path.join(unit_dir, "io.max"), "%s wbps=%d\n" % (IO_DEVICE, int(round(float(io_cap) * MIB))))
    pids_max = limits.get("pids_max")
    if pids_max is not None:
        write_cgroup_file(os.path.join(unit_dir, "pids.max"), "%d\n" % int(pids_max))


def mark_phase(run_dir: str, index: int, phase_type: str) -> None:
    with open(os.path.join(run_dir, "phases.log"), "a", encoding="utf-8") as handle:
        handle.write("%s %d %s\n" % (now_iso(), index, phase_type))
        handle.flush()


def write_meta(run_dir: str, seed: int, mode: str, duration_s: float, status: str) -> None:
    meta = {"seed": seed, "mode": mode, "duration_s": duration_s, "status": status}
    with open(os.path.join(run_dir, "meta.json"), "w", encoding="utf-8") as handle:
        json.dump(meta, handle, indent=2)
        handle.write("\n")


def run_scenario(scenario_path: str, run_dir: str, controller_mode: str, time_scale: float) -> int:
    scenario = load_scenario(scenario_path)
    os.makedirs(run_dir, exist_ok=True)
    shutil.copyfile(scenario_path, os.path.join(run_dir, "scenario.json"))
    started = time.monotonic()
    status = "ok"
    sampler: subprocess.Popen | None = None
    controller: subprocess.Popen | None = None
    try:
        stop_unit(NEIGHBOR_UNIT)
        stop_unit(CRITICAL_UNIT)
        sampler = popen_logging(
            [PYTHON, SAMPLER, "--out", os.path.join(run_dir, "telemetry.jsonl"), "--interval", "2"],
            os.path.join(run_dir, "sampler.log"),
        )
        if controller_mode != "none":
            if not os.path.isfile(CONTROLLER):
                raise RuntimeError("controller script not found: %s" % CONTROLLER)
            controller = popen_logging(
                [PYTHON, CONTROLLER, "--run-dir", run_dir, "--mode", controller_mode],
                os.path.join(run_dir, "controller.log"),
            )
        start_victim(scenario, run_dir)
        phases = scenario["phases"]
        iofile = os.path.join(run_dir, "iofile")
        sleep_until(started + scale_seconds(scenario["warmup_s"], time_scale))
        for index, phase in enumerate(phases):
            mark_phase(run_dir, index, phase["type"])
            if index == 0:
                start_neighbor(scenario, run_dir, stressor_chain(phases, scenario["neighbor"], iofile, time_scale))
                apply_cgroup_overrides(scenario)
            sleep_seconds(phase_seconds(phase, time_scale))
            gap_s = int(phase.get("gap_s", 0))
            sleep_seconds(scale_seconds(gap_s, time_scale))
        stop_unit(NEIGHBOR_UNIT)
        sleep_seconds(scale_seconds(scenario["cooldown_s"], time_scale))
        stop_unit(CRITICAL_UNIT)
    except Exception as error:
        status = "failed:%s" % str(error).replace("\n", " ")
    finally:
        stop_unit(NEIGHBOR_UNIT)
        stop_unit(CRITICAL_UNIT)
        terminate_process(sampler)
        terminate_process(controller)
    duration_s = round(time.monotonic() - started, 1)
    write_meta(run_dir, int(scenario["seed"]), controller_mode, duration_s, status)
    print("run seed=%d mode=%s status=%s duration=%ss dir=%s" % (scenario["seed"], controller_mode, status, duration_s, run_dir))
    return 0 if status == "ok" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one WorkloadPilot dataset-v2 scenario.")
    parser.add_argument("--scenario", required=True, help="scenario JSON path")
    parser.add_argument("--run-dir", required=True, help="output run directory")
    parser.add_argument("--controller-mode", choices=("rules", "explore", "none"), required=True)
    parser.add_argument("--time-scale", type=float, default=1.0, help="multiply every duration (default: 1.0)")
    args = parser.parse_args()
    if args.time_scale <= 0:
        parser.error("--time-scale must be > 0")
    return run_scenario(args.scenario, args.run_dir, args.controller_mode, args.time_scale)


if __name__ == "__main__":
    sys.exit(main())
