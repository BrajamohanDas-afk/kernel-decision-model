# WorkloadPilot dataset — sample & guide

*For humans. The real machine-readable dataset is `..\results\m1-v2\decision_train.jsonl` (162 rows, one JSON object per line) + `decision_heldout.jsonl` (40 rows, the "exam").*

## What this dataset is

Training examples for a decision model. Each row = one moment in a lab experiment: the workload numbers at that moment → the action the rules teacher chose. Built from a 7-minute run on the `wlp-lab` sandbox (Windows → WSL2). **Contains only synthetic telemetry numbers from the sandbox — no personal data, no user files; safe to share.**

**Label distribution:** `do_nothing` 83 · `increase_cpu` 43 · `throttle_io` 35 · `increase_memory` 1
(unbalanced on purpose at this scale — rare situations need more runs; the 1-row class is a known gap)

## Row anatomy

```
id        ← unique name (timestamp-based)
state     ← 15 numbers the model reads (the "input")
questions ← one question: "Which resource action should the controller take now?"
            with the 12 actions as answer options
labels    ← the correct action (from the rules teacher)
weight    ← 1.0
```

State fields: `n_*` = the "bad neighbor" workload (cpu quota, cumulative throttled time, cpu wait-pressure, memory current/limit, memory pushback events, disk bytes written, process count, PSI cpu/mem/io) · `c_*` = the "innocent app" · `sys_*` = whole-machine pressure + load.

## Three real example rows (these are actual rows)

**1 → teacher chose: `increase_cpu`** (neighbor is throttle-suffering, machine CPU pressure high)
```json
{"n_cpu_max_cores": 0.5, "n_cpu_throttled_usec": 12312110, "n_cpu_psi_avg10": 27.05,
 "n_mem_current_mb": 18.05, "n_mem_high_mb": 200.0, "n_mem_events_high": 0,
 "n_io_wbytes_mb": 0.0, "n_pids": 5,
 "c_cpu_throttled_usec": 0, "c_mem_current_mb": 4.54, "c_psi_cpu_avg10": 0.0,
 "sys_psi_cpu_avg10": 20.44, "sys_psi_mem_avg10": 0.0, "sys_psi_io_avg10": 0.0, "sys_load1": 0.46}
```

**2 → teacher chose: `throttle_io`** (neighbor has written 207 MB; disk-phase ongoing)
```json
{"n_cpu_max_cores": 1.0, "n_cpu_throttled_usec": 197230399, "n_cpu_psi_avg10": 0.0,
 "n_mem_current_mb": 8.21, "n_mem_high_mb": 250.0, "n_mem_events_high": 608,
 "n_io_wbytes_mb": 207.77, "n_pids": 1, "c_cpu_throttled_usec": 0, "c_mem_current_mb": 4.68,
 "c_psi_cpu_avg10": 0.0, "sys_psi_cpu_avg10": 0.0, "sys_psi_mem_avg10": 0.0,
 "sys_psi_io_avg10": 0.0, "sys_load1": 0.54}
```

**3 → teacher chose: `increase_memory`** (neighbor at 199.9 of its 200 MB limit, 608 pushback events)
```json
{"n_cpu_max_cores": 1.0, "n_cpu_throttled_usec": 197230399, "n_cpu_psi_avg10": 64.9,
 "n_mem_current_mb": 199.9, "n_mem_high_mb": 200.0, "n_mem_events_high": 608,
 "n_io_wbytes_mb": 201.77, "n_pids": 2, "c_cpu_throttled_usec": 0, "c_mem_current_mb": 4.67,
 "c_psi_cpu_avg10": 0.0, "sys_psi_cpu_avg10": 61.52, "sys_psi_mem_avg10": 0.0,
 "sys_psi_io_avg10": 0.0, "sys_load1": 0.73}
```

36 of 162 rows have `n_*` / `c_*` = null: those are moments when no stress workload was running (start, baseline, end) — the teacher correctly answers `do_nothing`.

## Known limits (to fix with more data)

1. **One machine, one scenario shape.** Fine for proving the pipeline; not proof that "everyone's systems" behave like this. Fix: randomized scenario generator + many runs (free) → broader coverage.
2. **Cumulative counters, no deltas yet.** A single row can't show "rate of change" for throttled time or bytes. Next dataset version adds delta/rate features.
3. **Class imbalance** (83 do_nothing vs 1 increase_memory). Fix: more runs + row weights at training time.

## Files around this one

| File | What it is |
|---|---|
| `..\results\m1-v2\decision_train.jsonl` | **The dataset** (162 training rows) |
| `..\results\m1-v2\decision_heldout.jsonl` | Held-out exam rows (40, never trained on) |
| `..\results\m1-v2\outcomes.jsonl` | What actually happened 90 s after each decision |
| `..\results\m1-v2\decisions.jsonl` | Full decisions log (incl. what was applied) |
