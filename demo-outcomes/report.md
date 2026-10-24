# WorkloadPilot measured outcome: M3 v3-2b vs static cgroup limits

**Run date:** 2026-10-18 (UTC) · **Scenario:** one 23.2 min, 17-phase workload · **Arms:** A static, B M3-controlled · **Model:** `workloadpilot/v3-2b`

## Verdict up front

- **CPU reservation fell 37%** (2,700 → 1,702 cores·s) and the idle tail fell 70% (2.0 → 0.6 cores), but **the saving is not a clean policy win**: the actuator's `increase_cpu` caps at one CPU, so one "increase" on a 120% quota actually cut 1.2 → 1.0 cores during saturation.
- **Memory reservation rose 7.2%** (1,080,000 → 1,157,600 MB·s). The controller raised `memory.high` from 800 → 850 → 900 MB and **never gave memory back** (0 applied `decrease_memory`). The tail ended at 900 MB vs 800 MB static (+12.5%).
- **Victim latency did not improve.** Overall p95 is 0.659 ms (A) vs 0.667 ms (B), +0.008 ms (+1.2%); mean is +0.013 ms (+4.2%). No material harm, but no benefit. During the mixed/decay phases B's p95 is 0.2–0.3 ms higher.
- **Controller cost:** 694 decisions, 450,816 input tokens, **$0.00316** at the project's $0.007/M-token convention. 13 applied writes (9 effective, 4 capped no-ops), 3 give-backs, 124 cooldown rejections, 0 model/controller errors.

This is a **partial / mixed result**: good CPU give-back in quiet regimes, worse memory reservation, no victim-latency gain, and a real actuator defect that inflates the CPU saving.

## Method

### Scenario (one JSON, identical for both arms)

Fixed neighbor limits for the whole run: `cpu.max = 200%` (2 cores), `memory.high = 800 MB`, `memory.max = 900 MB`, `pids.max = 200`. No per-phase limit overrides, no `io.max` cap at start. Victim: 100% CPU, 256 MB, 5 ms work / 20 ms loop.

| Phase group | Duration | Dynamics |
|---|---:|---|
| idle settle | 30 s | 0 processes |
| moderate burn | 150 s | 2 CPU burners |
| spike | 90 s | 9 CPU burners |
| cut-to-idle | 90 s | 0 processes |
| memory hold | 150 s | step to 720 MB (90% of `memory.high`) |
| memory release | 60 s | buffer freed |
| io | 90 s | 7 MB/s writes |
| io burst | 45 s | 12 MB/s writes |
| fork burst | 75 s | 150 forks/s |
| mixed | 120 s | CPU 2 + memory to 800 MB + io 4 MB/s |
| saturation | 120 s | CPU 10 → mixed → fork 150/s |
| decay | 180 s | CPU 5 → CPU 2 → 0 |
| idle tail | 150 s | 0 processes |

Total phases 1,350 s + 20 s warmup + 20 s cooldown = **1,390 s (23.2 min)**. Seed 7317; both runner meta statuses `ok`, both 675 neighbor-present telemetry samples.

### Arms

- **A static:** `runner.py --scenario scenario.json --run-dir .../static --controller-mode none --time-scale 1.0`. No controller.
- **B M3:** identical runner plus `live_controller.py --run-dir .../controlled --live --model v3-2b --cooldown 45 --poll 2`, started 12 s after the runner. This is the only cgroup writer.

Sequential arms, clean `wlp-*` units between them. Host: WSL2 `wlp-lab`, kernel 6.6.87.2-microsoft-standard-WSL2, cgroup v2, 12 CPUs, 7.8 GB RAM.

### Metrics

- **Allocation integral:** each 2 s telemetry sample counts `cpu.max` cores and `memory.high` MB while the neighbor cgroup exists: Σ(limit × 2 s). Tail = the 150 s `tail` phase.
- **Victim latency:** every `victim.log` sample, converted µs → ms; mean / p95 / p99 / max.
- **Controller:** `m3_decisions.jsonl` actions, applied writes, applied `decrease_*` (give-back), gate buckets, tokens, cost at $0.007 per 1M input tokens.
- Actual use is reported next to allocation (CPU from `cpu.stat.usage_usec` deltas, memory from `memory.current`) so reservation is not confused with demand.

## Results

| Metric | A static | B M3 | Δ (B−A) |
|---|---:|---:|---:|
| Telemetry span (s) | 1,388.8 | 1,388.7 | -0.0 |
| Telemetry samples | 675 | 675 | 0 |
| **CPU allocation (cores·s)** | **2,700.0** | **1,702.2** | **-997.8 (-37.0%)** |
| Mean cpu.max (cores) | 2.000 | 1.261 | -0.739 (-37.0%) |
| **Memory allocation (MB·s)** | **1,080,000** | **1,157,600** | **+77,600 (+7.2%)** |
| Mean memory.high (MB) | 800.0 | 857.5 | +57.5 (+7.2%) |
| Tail CPU allocation (cores·s) | 300.0 | 90.0 | -210.0 (-70.0%) |
| Tail memory allocation (MB·s) | 120,000 | 135,000 | +15,000 (+12.5%) |
| CPU used (cores·s) | 1,159.0 | 845.3 | -313.7 (-27.1%) |
| Mean CPU used (cores) | 0.859 | 0.627 | -0.233 (-27.1%) |
| Mean memory used (MB) | 198.0 | 202.5 | +4.5 (+2.3%) |
| CPU throttled (s) | 1,060.21 | 1,371.20 | +310.98 (+29.3%) |
| `memory.events.high` (count) | 4,323 | 0 | -4,323 (-100%) |
| Victim samples | 68,163 | 68,092 | -71 |
| Victim mean (ms) | 0.306 | 0.319 | +0.013 (+4.2%) |
| **Victim p95 (ms)** | **0.659** | **0.667** | **+0.008 (+1.2%)** |
| Victim p99 (ms) | 0.806 | 0.817 | +0.011 (+1.4%) |
| Victim max (ms) | 6.617 | 4.876 | -1.741 (-26.3%) |
| Controller decisions | 0 | 694 | +694 |
| Applied writes | 0 | 13 | +13 |
| Give-back writes (`decrease_*`) | 0 | 3 | +3 |
| Tokens | 0 | 450,816 | +450,816 |
| Cost estimate (USD) | 0 | 0.003156 | +0.003156 |

### Where the CPU saving came from

Arm B's quota history (675 samples × 2 s = 1,350 s):

| cpu.max | Time | Driver |
|---:|---:|---|
| 2.0 cores | 312 s | start through cut-to-idle |
| 1.2 cores | 592 s | applied `decrease_cpu` 200%→120% at cut-to-idle |
| 1.0 core | 216 s | applied `increase_cpu` 120%→100% (**capped at 1 CPU**, actually a cut) |
| 0.9 core | 46 s | applied `increase_cpu` 60%→90% |
| 0.6 core | 184 s | applied `decrease_cpu` 100%→60% in decay-off |

So the 37% reduction combines three genuine `decrease_cpu` give-backs (cut-to-idle, decay, decay-off) with one mislabeled decrease at saturation. **Treat -37% as an upper bound on intentional give-back, not a policy result.** The tail's 0.6 cores is genuine: the last applied write before the tail cut 1.0 → 0.6 and nothing raised it again.

On the reservation-vs-use view, unused CPU reservation (allocation − usage) fell from 1,541 to 857 cores·s. That gap is not a pure efficiency gain either: the neighbor's CPU use fell 27% because it was throttled more, not because demand disappeared.

### Where the memory increase came from

`memory.high` was 800 MB until t+382 s, 850 MB until t+802 s, and 900 MB from the mixed phase to the end. The controller chose `increase_memory` 90 times, applied it 6 times (two effective steps and four no-ops at the 900 MB cap), chose `decrease_memory` **0 times**, and applied 0. The idle tail therefore reserved 900 MB, 12.5% above the static arm.

### Victim latency: no improvement

Overall p95 is flat within 0.008 ms. Per regime, the differences are sub-millisecond and not systematic:

| Regime | A mean / p95 (ms) | B mean / p95 (ms) |
|---|---|---|
| moderate | 0.170 / 0.276 | 0.153 / 0.231 |
| spike | 0.352 / 0.712 | 0.348 / 0.699 |
| cut-to-idle | 0.383 / 0.697 | 0.403 / 0.682 |
| mem hold | 0.388 / 0.695 | 0.395 / 0.680 |
| io / io burst | 0.372 / 0.683 · 0.339 / 0.670 | 0.377 / 0.679 · 0.349 / 0.669 |
| fork | 0.319 / 0.685 | 0.302 / 0.669 |
| mixed | 0.149 / 0.243 | 0.223 / 0.546 |
| saturation | 0.228 / 0.577 | 0.288 / 0.643 |
| decay | 0.226 / 0.565 | 0.299 / 0.662 |
| tail | 0.389 / 0.676 | 0.344 / 0.680 |

B is slightly better in moderate/fork/mem-hold, slightly worse in mixed/saturation/decay, and identical in the idle tail. The overall p95 delta is +1.2%; this is not a latency win. A plausible mechanism for the mixed/decay regression: B's higher `memory.high` removed reclaim pressure (0 vs 4,323 `memory.events.high`), so the neighbor kept doing work instead of being slowed by reclaim, while B's quota sawtooth (1.2 → 1.0 → 0.6 → 0.9 → 1.0 → 0.6) added scheduling jitter. One run cannot separate these.

### Controller behavior

- **694 decisions in 1,387 s** (~30/min at 2 s polling). Action mix: `do_nothing` 555 (80%), `increase_memory` 90, `increase_cpu` 43, `decrease_cpu` 3, `throttle_io` 1, `alert_operator` 2. Zero `decrease_memory`.
- **Gate:** 557 pass-no-write, 13 applied, 124 rejected — all 124 were the per-action 45 s cooldown. No unknown actions, no precondition failures, no actuator refusals, no model/controller errors.
- **Applied writes (effective):**

| UTC | Phase | Action | Write |
|---|---|---|---|
| 17:48:04 | cut-to-idle | `decrease_cpu` | cpu.max 200% → 120% |
| 17:48:56 | mem hold | `increase_memory` | memory.high 800 → 850 MB |
| 17:55:56 | mixed | `increase_memory` | memory.high 850 → 900 MB |
| 17:57:55 | saturation | `throttle_io` | io.max 1 MiB/s (device 8:48) |
| 17:57:57 | saturation | `increase_cpu` | cpu.max 120% → 100% (**capped at 1 CPU**) |
| 17:59:55 | decay | `decrease_cpu` | cpu.max 100% → 60% |
| 18:00:05 | decay | `increase_cpu` | cpu.max 60% → 90% |
| 18:00:51 | decay | `increase_cpu` | cpu.max 90% → 100% |
| 18:02:29 | decay-off | `decrease_cpu` | cpu.max 100% → 60% |

Four more `increase_memory` writes at 17:56:41, 17:57:27, 17:58:27 and 17:59:13 were **no-ops** at the 900 MB cap (`memory.high 900M->900M`, `applied=True`). They are excluded from the table but counted in the 13 applied.

## What improved vs what didn't

**Improved**

- CPU reservation in quiet regimes: the controller cut 2.0 → 1.2 cores at cut-to-idle, 1.0 → 0.6 in decay, and ended the tail at 0.6 cores vs 2.0 (-70% tail reservation).
- Neighbor memory pressure: `memory.events.high` fell from 4,323 to 0 after `memory.high` was raised to 900 MB. No `memory.events.max` or OOM events in either arm.
- Victim safety was not sacrificed: overall p95 +0.008 ms, p99 +0.011 ms, max actually lower (4.9 vs 6.6 ms).
- Cost is negligible: $0.00316 for 23 minutes of closed-loop control.

**Did not improve / got worse**

- **Victim latency did not improve** (the headline safety metric). The mean is 4.2% higher, and the mixed/decay phases are visibly worse in chart 2.
- **Memory waste increased 7.2%**; the controller never gave memory back and the tail ends at the 900 MB cap.
- **Neighbor CPU throttling increased 29%** (1,060 → 1,371 s). The CPU reservation saving was partly paid by the neighbor doing less work — that is a throughput cost, not free efficiency.
- **The model rarely acts:** 80% `do_nothing`; 124 of 694 decisions were suppressed by cooldown. In a 23-minute run it made 9 effective writes.
- **No memory give-back policy:** 90 `increase_memory` choices and zero `decrease_memory` choices; the model does not reclaim memory when the hold is released.

## Defects found (must fix before claiming a CPU win)

1. **`increase_cpu` caps at one CPU.** For any quota above one CPU, `actuator.apply_increase_cpu` and `gate.project_cpu` compute `quota * 1.5`, then clamp to `period` (100000 µs), so the "increase" is really a decrease. At saturation it turned 120% into 100% (1.2 → 1.0 cores); from the full 200% start it would turn 200% into 100%. The event passed the gate and inflates the demo's CPU saving. Fix: allow quota > period up to `CPU_QUOTA_MAX`, or reject an "increase" whose projection is lower than the current value.
2. **No-op "applied" writes.** Four `increase_memory` writes at `memory.high = memory.max = 900 MB` wrote 900 → 900 and were logged as applied. The gate should reject when the projected value equals the current value.
3. **`throttle_io` has no undo.** The 1 MiB/s `io.max` cap applied at saturation stayed set for the rest of the run. There is no action in the taxonomy that restores IO; the demo's later phases had no IO load, so the measured impact is limited to the saturation mixed phase, but the cgroup state was left throttled.
4. **No memory give-back in the learned policy.** The model's `decrease_memory` probability is effectively zero in this state distribution; a memory-specific reclaim rule or training data with memory-release labels is needed before the controller can reduce memory reservation.

## Caveats

- **One run per arm, sequential, no randomization.** Differences below ~0.02 ms overall are within run-to-run noise; the per-regime differences are consistent in direction but not replicated. The p95 delta (+0.008 ms) should not be read as a statistically established effect.
- **The host is not contended.** 12 CPUs, 7.8 GB RAM, neighbor capped at 2 cores and 800 MB, victim has its own 1 core and 256 MB. The victim has little room to improve, so this demo measures reservation accounting and neighbor pressure more than hard contention. A constrained host (fewer cores, memory pressure) is the next experiment.
- **Allocation integral counts limits, not harm.** It is Σ(limit × 2 s), as specified. The dashed usage lines in chart 1 show the demand; the gap is unused reservation, not necessarily waste that hurts anyone.
- **Cost is an estimate** at the project convention of $0.007 per 1M input tokens, not an invoice. Total for this experiment is $0.00316; including the smoke test and API probes, ~$0.0035.
- **The controller's state distribution is narrow.** The scenario's mixed phase always targets 800 MB (the static `memory.high`), so once B raises `memory.high` to 900 MB it has 100 MB of headroom and never triggers reclaim again. A workload that grows past 900 MB would behave differently (and would hit `memory.max`).
- **Smoke test:** a 0.1× rehearsal ran the same supervisor/controller path (149 s, 69 decisions, 4 applied). It is not part of the comparison.

## Charts

- `charts/01-allocation-envelopes.png` — cpu.max and memory.high envelopes over the full run, both arms, with actual use dashed.
- `charts/02-victim-p95.png` — victim p95 per 10 s bin, both arms, phase boundaries and idle tail.
- `charts/03-arm-b-actions.png` — arm B's envelope, effective applied writes, and the chosen-action timeline with gate status.

## Reproduce (lab)

```bash
python3 /root/workloadpilot/m3/demo/gen_scenario.py
bash /root/workloadpilot/m3/demo/run_arm.sh static
# stage C:\Users\Braju\AppData\Local\Temp\opencode\m3key.tmp first
bash /root/workloadpilot/m3/demo/run_arm.sh controlled
python3 /root/workloadpilot/m3/demo/analyze.py run /root/workloadpilot/m3/demo/static --label static --out /root/workloadpilot/m3/demo/static/metrics.json
python3 /root/workloadpilot/m3/demo/analyze.py run /root/workloadpilot/m3/demo/controlled --label controlled --out /root/workloadpilot/m3/demo/controlled/metrics.json
python3 /root/workloadpilot/m3/demo/analyze.py compare /root/workloadpilot/m3/demo/static/metrics.json /root/workloadpilot/m3/demo/controlled/metrics.json --out-md /root/workloadpilot/m3/demo/compare.md
```

Raw artifacts: `/root/workloadpilot/m3/demo/{static,controlled}/` (`telemetry.jsonl`, `victim.log`, `m3_decisions.jsonl`, `m3_outcomes.jsonl`, `controller.log`, `phases.log`, `scenario.json`, `meta.json`, `metrics.json`). Charts are rendered from the two `metrics.json` files with `make_charts.py`.
