# M3 Test Tour v1 — summary

Seed 4010 (run-4010-mem) · throughput victim · neighbor quota 100% · memory.high 948 MB
Phases: mem_grow 54s; fork_light 22s; mem_grow 35s; mem_grow 34s; mem_grow 48s (warmup 10s, cooldown 28s)

Seed 4011 (run-4011-mixed) · latency victim · neighbor quota 50% · memory.high 716 MB
Phases: fork_light 98s; mixed[io_write+mem_grow+cpu_burn 131s] (warmup 12s, cooldown 20s)

Seed 4011 (run-4011-mixed-4b) · latency victim · neighbor quota 50% · memory.high 716 MB
Phases: fork_light 98s; mixed[io_write+mem_grow+cpu_burn 131s] (warmup 12s, cooldown 20s)

Seed 4029 (run-4029-cpu) · throughput victim · neighbor quota 300% · memory.high 586 MB
Phases: cpu_burn 133s; mem_grow 107s (warmup 14s, cooldown 15s)

Seed 4035 (run-4035-io) · latency victim · neighbor quota 25% · memory.high 208 MB
Phases: io_write 55s; mixed[mem_grow+io_write 58s]; io_write 70s (warmup 10s, cooldown 16s)

### Run seed 4010 (run-4010-mem) model workloadpilot/v2-2b

| metric | value |
|---|---|
| decisions / telemetry rows | 126 / 127 |
| pacing | 30.2 decisions/min over 250.1 s, max 1 per ts |
| model errors | 0 |
| tokens | 76311 |
| gate | 106 pass-no-write, 3 applied, 17 rejected |
| rejection reasons | cooldown x17 |
| peak neighbor pressure | psi_cpu max 0.0, throttled max 2087 us/s, mem events high max 269, min headroom 0 MB |

| action | chosen |
|---|---|
| do_nothing | 104 |
| increase_memory | 17 |
| decrease_memory | 1 |
| restrict_process_count | 2 |
| alert_operator | 2 |

| ts | action | write | next-3 telemetry (mem_high/pids/cpu_psi/io_psi) |
|---|---|---|---|
| 21:47:38 | restrict_process_count | wlp-neighbor pids.max 238->119 | 21:47:40: 948/5/0.0/0.0, 21:47:42: 948/5/0.0/0.0, 21:47:44: 948/5/0.0/0.0 |
| 21:48:44 | increase_memory | wlp-neighbor memory.high 994050048->1046478848 | 21:48:46: 998/2/0.0/0.4, 21:48:48: 998/2/0.0/0.7, 21:48:50: 998/2/0.0/0.5 |
| 21:49:18 | decrease_memory | wlp-neighbor memory.high 1046478848->994050048 | 21:49:20: 998/2/0.0/0.2, 21:49:22: 948/2/0.0/0.1, 21:49:24: 948/2/0.0/0.1 |

Outcome deltas (3 samples before vs 3 after; directional only, not causal proof):

| ts | action | victim before->after | cpu throttled us/s | mem events high /s | io psi avg10 | cpu psi avg10 |
|---|---|---|---|---|---|---|
| 21:47:38 | restrict_process_count | 1.01 -> 1.01 | 0 -> 0 | 0.00 -> 0.00 | 0.00 -> 0.00 | 0.00 -> 0.00 |
| 21:48:44 | increase_memory | 1.01 -> 1.01 | 0 -> 0 | 0.00 -> 32.48 | 0.00 -> 0.34 | 0.00 -> 0.00 |
| 21:49:18 | decrease_memory | 1.01 -> 1.01 | 0 -> 0 | 0.00 -> 0.00 | 0.04 -> 0.17 | 0.00 -> 0.00 |

### Run seed 4011 (run-4011-mixed) model workloadpilot/v2-2b

| metric | value |
|---|---|
| decisions / telemetry rows | 139 / 140 |
| pacing | 30.2 decisions/min over 276.1 s, max 1 per ts |
| model errors | 0 |
| tokens | 91641 |
| gate | 72 pass-no-write, 5 applied, 62 rejected |
| rejection reasons | cooldown x62 |
| peak neighbor pressure | psi_cpu max 52.3, throttled max 2703846 us/s, mem events high max 284, min headroom 0 MB |

| action | chosen |
|---|---|
| do_nothing | 70 |
| increase_memory | 64 |
| restrict_process_count | 3 |
| alert_operator | 2 |

| ts | action | write | next-3 telemetry (mem_high/pids/cpu_psi/io_psi) |
|---|---|---|---|
| 21:51:08 | restrict_process_count | wlp-neighbor pids.max 54->27 | 21:51:10: 716/13/0.0/0.0, 21:51:12: 716/13/0.0/0.0, 21:51:14: 716/13/0.0/0.0 |
| 21:53:02 | restrict_process_count | wlp-neighbor pids.max 27->16 |  |
| 21:53:04 | increase_memory | wlp-neighbor memory.high 750780416->803209216 | 21:53:06: 716/6/23.8/5.5, 21:53:08: 766/6/28.7/7.6, 21:53:10: 766/6/32.9/11.3 |
| 21:53:50 | increase_memory | wlp-neighbor memory.high 803209216->829423616 | 21:53:52: 766/6/49.5/28.2, 21:53:54: 791/6/49.8/27.2, 21:53:56: 791/6/49.7/27.4 |
| 21:54:34 | increase_memory | wlp-neighbor memory.high 829423616->829423616 | 21:54:36: 791/6/51.3/27.0, 21:54:38: 791/6/51.2/27.2, 21:54:40: 791/6/51.4/27.2 |

Outcome deltas (3 samples before vs 3 after; directional only, not causal proof):

| ts | action | victim before->after | cpu throttled us/s | mem events high /s | io psi avg10 | cpu psi avg10 |
|---|---|---|---|---|---|---|
| 21:51:08 | restrict_process_count | 0.55 -> 0.60 | - -> 0 | - -> 0.00 | 0.00 -> 0.00 | 0.00 -> 0.00 |
| 21:53:02 | restrict_process_count | 0.73 -> 0.58 | 0 -> 2679943 | 0.00 -> 68.98 | 0.00 -> 2.73 | 0.00 -> 14.87 |
| 21:53:04 | increase_memory | 0.70 -> 0.50 | 1258339 -> 2304751 | 0.00 -> 49.99 | 0.00 -> 5.25 | 2.44 -> 22.80 |
| 21:53:50 | increase_memory | 0.78 -> 0.78 | 1530758 -> 1516329 | 0.00 -> 0.00 | 27.96 -> 27.79 | 49.55 -> 49.68 |
| 21:54:34 | increase_memory | 0.64 -> 0.58 | 1608304 -> 1562186 | 0.00 -> 0.00 | 27.38 -> 27.08 | 50.87 -> 51.30 |

### Run seed 4011 (run-4011-mixed-4b) model workloadpilot/v2-4b-r2

| metric | value |
|---|---|
| decisions / telemetry rows | 139 / 140 |
| pacing | 30.2 decisions/min over 276.1 s, max 1 per ts |
| model errors | 0 |
| tokens | 91513 |
| gate | 71 pass-no-write, 5 applied, 63 rejected |
| rejection reasons | cooldown x62, unsafe/unsatisfiable: wlp-neighbor: io.weight missing (FileNotFoundError: [Errno 2] No such file or directory: '/sys/fs/cgroup/wlp.slice/wlp-neighbor.service/io.weight'); io.stat unreadable (FileNotFoundError: [Errno 2] No such file or directory: '/sys/fs/cgroup/wlp.slice/wlp-neighbor.service/io.stat') x1 |
| peak neighbor pressure | psi_cpu max 52.1, throttled max 2643659 us/s, mem events high max 216, min headroom -0 MB |

| action | chosen |
|---|---|
| do_nothing | 69 |
| increase_memory | 64 |
| throttle_io | 1 |
| restrict_process_count | 3 |
| alert_operator | 2 |

| ts | action | write | next-3 telemetry (mem_high/pids/cpu_psi/io_psi) |
|---|---|---|---|
| 08:16:42 | restrict_process_count | wlp-neighbor pids.max 54->27 | 08:16:44: 716/13/0.0/0.2, 08:16:46: 716/13/0.0/0.1, 08:16:48: 716/13/0.0/0.1 |
| 08:18:36 | restrict_process_count | wlp-neighbor pids.max 27->16 |  |
| 08:18:38 | increase_memory | wlp-neighbor memory.high 750780416->803209216 | 08:18:40: 716/6/23.9/6.2, 08:18:42: 766/6/29.2/8.3, 08:18:44: 766/6/31.7/11.7 |
| 08:19:26 | increase_memory | wlp-neighbor memory.high 803209216->829423616 | 08:19:28: 791/6/51.9/26.4, 08:19:30: 791/6/52.1/26.0, 08:19:32: 791/6/49.9/26.4 |
| 08:20:12 | increase_memory | wlp-neighbor memory.high 829423616->829423616 | 08:20:14: 791/6/49.7/28.3, 08:20:16: 791/6/49.7/28.3, 08:20:18: 791/6/48.3/28.2 |

Outcome deltas (3 samples before vs 3 after; directional only, not causal proof):

| ts | action | victim before->after | cpu throttled us/s | mem events high /s | io psi avg10 | cpu psi avg10 |
|---|---|---|---|---|---|---|
| 08:16:42 | restrict_process_count | 0.74 -> 0.69 | - -> 0 | - -> 0.00 | 0.30 -> 0.18 | 0.00 -> 0.00 |
| 08:18:36 | restrict_process_count | 0.57 -> 0.57 | 0 -> 2597893 | 0.00 -> 41.48 | 0.00 -> 3.71 | 0.00 -> 14.57 |
| 08:18:38 | increase_memory | 0.56 -> 0.58 | 1259416 -> 2367095 | 0.00 -> 53.97 | 0.27 -> 6.30 | 2.35 -> 22.74 |
| 08:19:26 | increase_memory | 0.74 -> 0.66 | 1568666 -> 1550663 | 0.00 -> 0.00 | 26.38 -> 26.17 | 51.28 -> 51.84 |
| 08:20:12 | increase_memory | 0.66 -> 0.66 | 1552624 -> 1554049 | 0.00 -> 0.00 | 28.30 -> 28.33 | 49.02 -> 49.59 |

### Run seed 4029 (run-4029-cpu) model workloadpilot/v2-2b

| metric | value |
|---|---|
| decisions / telemetry rows | 135 / 136 |
| pacing | 30.2 decisions/min over 268.1 s, max 1 per ts |
| model errors | 0 |
| tokens | 80739 |
| gate | 135 pass-no-write, 0 applied, 0 rejected |
| rejection reasons | - |
| peak neighbor pressure | psi_cpu max 0.0, throttled max 0 us/s, mem events high max 0, min headroom 345 MB |

| action | chosen |
|---|---|
| do_nothing | 133 |
| alert_operator | 2 |

### Run seed 4035 (run-4035-io) model workloadpilot/v2-2b

| metric | value |
|---|---|
| decisions / telemetry rows | 110 / 111 |
| pacing | 30.3 decisions/min over 218.1 s, max 1 per ts |
| model errors | 0 |
| tokens | 71591 |
| gate | 108 pass-no-write, 2 applied, 0 rejected |
| rejection reasons | - |
| peak neighbor pressure | psi_cpu max 3.9, throttled max 475488 us/s, mem events high max 711, min headroom 0 MB |

| action | chosen |
|---|---|
| do_nothing | 106 |
| increase_memory | 1 |
| restrict_process_count | 1 |
| alert_operator | 2 |

| ts | action | write | next-3 telemetry (mem_high/pids/cpu_psi/io_psi) |
|---|---|---|---|
| 21:43:45 | increase_memory | wlp-neighbor memory.high 218103808->270532608 |  |
| 21:43:49 | restrict_process_count | wlp-neighbor pids.max 230->115 | 21:43:51: 258/4/2.6/2.5, 21:43:53: 258/4/2.1/2.0, 21:43:55: 258/4/1.7/2.0 |

Outcome deltas (3 samples before vs 3 after; directional only, not causal proof):

| ts | action | victim before->after | cpu throttled us/s | mem events high /s | io psi avg10 | cpu psi avg10 |
|---|---|---|---|---|---|---|
| 21:43:45 | increase_memory | 0.79 -> 0.69 | 0 -> 55340 | 0.00 -> 152.92 | 0.16 -> 2.29 | 0.00 -> 3.55 |
| 21:43:49 | restrict_process_count | 0.77 -> 0.71 | 110680 -> 0 | 305.85 -> 0.00 | 1.91 -> 2.52 | 3.75 -> 2.63 |

## Cross-scenario aggregate

| metric | value |
|---|---|
| runs | 5 |
| decisions | 649 |
| total tokens | 411795 |
| estimated cost | $0.00320 |
| actions chosen at least once | 6 / 12 |
| never chosen | increase_cpu, decrease_cpu, protect_service, isolate_workload, restart_service, kill_process |
| rejection histogram | cooldown x141, unsafe/unsatisfiable: wlp-neighbor: io.weight missing (FileNotFoundError: [Errno 2] No such file or directory: '/sys/fs/cgroup/wlp.slice/wlp-neighbor.service/io.weight'); io.stat unreadable (FileNotFoundError: [Errno 2] No such file or directory: '/sys/fs/cgroup/wlp.slice/wlp-neighbor.service/io.stat') x1 |

Action totals across runs: do_nothing 482, increase_memory 146, alert_operator 10, restrict_process_count 9, decrease_memory 1, throttle_io 1

## A/B seed 4011: workloadpilot/v2-2b vs workloadpilot/v2-4b-r2

| metric | workloadpilot/v2-2b | workloadpilot/v2-4b-r2 |
|---|---|---|
| decisions | 139 | 139 |
| tokens | 91641 | 91513 |
| applied / rejected | 5 / 62 | 5 / 63 |
| aligned samples (elapsed s) | 139 | (common span 276 s) |
| same-elapsed action agreement | 138 / 139 (99%) | (col 2) |
| action do_nothing | 70 | 69 |
| action increase_memory | 64 | 64 |
| action throttle_io | 0 | 1 |
| action restrict_process_count | 3 | 3 |
| action alert_operator | 2 | 2 |

First disagreements (elapsed s): +256s do_nothing vs throttle_io

## Caveats

* Outcome deltas use 3 telemetry samples per side (6 s windows): directional evidence, not causal proof.
* Victim rows are dense (100 ms), so victim windows carry many points; pressure rates need >= 2 counter samples.
* Cooldown (45 s) suppresses repeated writes, so chosen-action counts exceed applied counts by design.

## Anomalies & observations

1. **CPU-family run (4029) produced zero writes — correctly.** The neighbor never throttled there (peak 0 us/s, psi_cpu 0.0, 0 memory-high events, 345 MB headroom): the seed's `cpu_burn` (quota 300 %, 2 burners) does not pressure a 3-core allowance. The 133 `do_nothing` are consistent with the training teacher (which triggers on throttling/psi), not a model failure.
2. **increase_memory dominance.** 146 choices across the tour (64 in each seed-4011 run), 141 cooldown rejections total. The model re-asks for memory on every sample while headroom is 0; cooldown + `memory.max` bound the effect.
3. **No-op "applied" writes at the cap.** Seed 4011, both models (`21:54:34` / `08:20:12`): `memory.high 829423616->829423616` — already at `memory.max`. The log shows it honestly (before == after) but `applied: true` overstates it.
4. **Floors and caps engaged.** `pids.max 238->119` (mem run), `230->115` (io run), `27->16` (= PIDS_MIN floor, mixed run); `memory.high` hit the `memory.max` cap (974 MB in seed-3100, 791 MB in seed-4011).
5. **Gate caught an unperformable action live.** v2-4b-r2's single `throttle_io` (seed 4011, +256 s) was rejected because this WSL cgroup exposes no `io.weight`/`io.stat`; clear reason logged, nothing written.
6. **Outcome windows can be truncated by design.** A new applied action 2 s later flushes the pending window (seed 4011, +130 s: `pids.max 27->16` has no samples; its `m3_outcomes` row is `complete: false`).
7. **alert_operator 10×** across the tour (2 per run) — logged as a no-write alert; the lab has no operator-notification channel.
8. **A/B: v2-4b-r2 ≈ v2-2b on this scenario** — 99 % same-elapsed action agreement (138/139), identical applied counts (5), tokens within 0.1 %. The larger model did not change behavior on this state distribution; its one extra idea (`throttle_io`) was gate-rejected.
9. **Infra note.** Run E's first attempt was killed by an agent-server restart mid-run; it was re-run from scratch (all data above is from the complete run). WSL's clock re-synced after the restart, so run E timestamps are +10 h; within-run pacing and elapsed alignment are unaffected.

## Recommendations

1. **Scenario coverage:** for a genuine CPU-pressure run pick quota ≤ 100 % with burners > cores (4005/4037-style draws); quota 300 % + 2 burners is a no-pressure configuration.
2. **No-op guard:** when the projected write equals the current value, either skip the actuator call or mark `applied_noop` (small change in `gate.check`/`live_controller`), so "applied" means the cgroup value actually changed.
3. **Model-side cooldown awareness:** the cooldown is controller-side and invisible to the model, which is why it re-asks for memory every sample. Adding "seconds since last applied action of this class" to the v2.5 feature set (or a per-class write budget in the gate) would cut decision churn.
4. **Coverage of rare actions:** no CPU, io, or protect_service action was ever chosen live; the trained distribution (do_nothing + memory) transfers. If those branches matter, use scenarios that actually throttle CPU, and note that io actions cannot execute on this WSL kernel (no io.weight/io.stat) — the gate rejects them cleanly.
5. **Statistical honesty:** outcome deltas are 3-sample directional reads; repeat runs per scenario are needed before any outcome claim beyond direction.
