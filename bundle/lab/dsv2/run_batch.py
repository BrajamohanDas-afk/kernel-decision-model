#!/usr/bin/env python3
"""WorkloadPilot dataset-v2 batch driver.

Runs N scenarios sequentially (seed = start-seed + i), picks rules/explore per
run, and appends one index.jsonl row per run next to the run directories.
A failed run is logged, followed by a settle pause, and never aborts the batch.
"""

import argparse
import json
import os
import random
import subprocess
import sys
import time
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable
SCENARIO_GEN = os.path.join(HERE, "scenario_gen.py")
RUNNER = os.path.join(HERE, "runner.py")
GEN_TIMEOUT_S = 60.0
RUN_TIMEOUT_S = 900.0
RECOVERY_PAUSE_S = 60.0


def count_lines(path: str) -> int:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return sum(1 for _ in handle)
    except OSError:
        return 0


def read_meta(run_dir: str) -> dict[str, Any] | None:
    path = os.path.join(run_dir, "meta.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def append_index(index_path: str, record: dict[str, Any]) -> None:
    with open(index_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
        handle.flush()


def stop_leftover_units() -> None:
    for unit in ("wlp-neighbor.service", "wlp-critical.service"):
        try:
            subprocess.run(["systemctl", "stop", unit], capture_output=True, timeout=30)
            subprocess.run(["systemctl", "reset-failed", unit], capture_output=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as error:
            print("warn: could not stop %s: %s" % (unit, error), file=sys.stderr)


def run_one(
    seed: int,
    mode: str,
    run_dir: str,
    scenario_path: str,
    index_path: str,
    time_scale: float,
    mem_scale: float,
) -> str:
    started = time.monotonic()
    status = "failed:unknown"
    try:
        subprocess.run(
            [PYTHON, SCENARIO_GEN, "--seed", str(seed), "--out", scenario_path, "--mem-scale", "%g" % mem_scale],
            check=True,
            capture_output=True,
            text=True,
            timeout=GEN_TIMEOUT_S,
        )
        subprocess.run(
            [
                PYTHON,
                RUNNER,
                "--scenario",
                scenario_path,
                "--run-dir",
                run_dir,
                "--controller-mode",
                mode,
                "--time-scale",
                "%g" % time_scale,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT_S,
        )
        status = "ok"
    except subprocess.CalledProcessError as error:
        status = "failed:exit-%d" % error.returncode
        tail = [line for line in (error.stderr or error.stdout or "").strip().splitlines() if line][-3:]
        if tail:
            print("  runner output: %s" % " | ".join(tail), file=sys.stderr)
    except subprocess.TimeoutExpired:
        status = "failed:timeout"
        stop_leftover_units()
    except OSError as error:
        status = "failed:%s" % error
    finally:
        try:
            os.remove(scenario_path)
        except OSError:
            pass

    duration_s = round(time.monotonic() - started, 1)
    meta = read_meta(run_dir)
    if meta is not None:
        status = str(meta.get("status", status))
        duration_s = float(meta.get("duration_s", duration_s))
    record = {
        "seed": seed,
        "mode": mode,
        "status": status,
        "rows": count_lines(os.path.join(run_dir, "telemetry.jsonl")),
        "duration_s": duration_s,
    }
    append_index(index_path, record)
    print(
        "[seed=%d mode=%s status=%s rows=%d duration=%ss]" % (seed, mode, status, record["rows"], duration_s),
        flush=True,
    )
    return str(status)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a batch of WorkloadPilot dataset-v2 scenarios.")
    parser.add_argument("--runs", type=int, required=True, help="number of runs")
    parser.add_argument("--start-seed", type=int, required=True, help="first seed")
    parser.add_argument("--mode-mix", type=float, default=0.7, help="P(rules) per run (default: 0.7)")
    parser.add_argument("--runs-dir", required=True, help="directory for run dirs and index.jsonl")
    parser.add_argument("--time-scale", type=float, default=1.0, help="passed through to runner (default: 1.0)")
    parser.add_argument("--mem-scale", type=float, default=1.0, help="memory budget multiplier passed to scenario_gen (default: 1.0)")
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be >= 1")
    if not 0.0 <= args.mode_mix <= 1.0:
        parser.error("--mode-mix must be in [0, 1]")
    if args.time_scale <= 0:
        parser.error("--time-scale must be > 0")
    if args.mem_scale <= 0:
        parser.error("--mem-scale must be > 0")

    os.makedirs(args.runs_dir, exist_ok=True)
    index_path = os.path.join(args.runs_dir, "index.jsonl")
    rng = random.Random(args.start_seed)
    for offset in range(args.runs):
        seed = args.start_seed + offset
        mode = "explore" if rng.random() >= args.mode_mix else "rules"
        run_dir = os.path.join(args.runs_dir, "run-%d-%s" % (seed, mode))
        scenario_path = os.path.join(args.runs_dir, ".scenario-%d.json" % seed)
        print("[%d/%d] running seed=%d mode=%s" % (offset + 1, args.runs, seed, mode), flush=True)
        status = run_one(seed, mode, run_dir, scenario_path, index_path, args.time_scale, args.mem_scale)
        if str(status).startswith("failed") and offset < args.runs - 1:
            print(
                "run failed (%s) - letting the machine settle for %ds before the next run" % (status, RECOVERY_PAUSE_S),
                flush=True,
            )
            time.sleep(RECOVERY_PAUSE_S)
    print("batch done: %d runs, index=%s" % (args.runs, index_path), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
