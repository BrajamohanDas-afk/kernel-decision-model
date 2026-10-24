# Dataset v2 — scaling plan (locked spec)

*Created Oct 15. Supersedes the "known limits" section of `platform-dataset-sample.md` as the plan of record.*

## Goal

Turn ~162 rows from one scenario shape into a **run-diverse, rate-featured, outcome-aware** dataset (~10–15k rows), so the trained model can generalize beyond "one run on one machine" — and can potentially beat the rules teacher instead of only copying it.

## Pipeline (each stage a separate script; raw data kept forever)

```
scenario_gen.py  (seed) → runs in wlp-lab → results/dataset-v2/run-<seed>/
    scenario.json (the drawn config)           telemetry.jsonl   (raw, kept)
    decisions.jsonl (controller actions)       phases.log
 → featurize.py   (deltas/rates, no leakage)  → rows.jsonl
 → labeler.py     (rules label + outcome score + exploration flag) → labeled.jsonl
 → split_by_run.py (whole runs either train or heldout) → train.jsonl / heldout.jsonl + split manifest
```

Re-featurize or re-label any time without re-running experiments.

## Scenario generator (randomized, seeded)

- **Workload types (v1, stdlib-only):** cpu_burn (1–4 procs) · mem_grow (step/ramp, 64–512 MB) · io_write (paced 0.5–8 MB/s) · fork_light (20–200 short procs) · mixed (cpu+mem, cpu+io) · **spike/self-resolve** (hard negatives — brief spikes that heal without action).
- **Randomized limits:** cpu.max 0.25–4 cores · memory.high 64–1024 MB · io.max varied · pids.max varied.
- **Randomized timing:** phase start offsets, durations (10–60 s), ramps (step / ramp / spike / sawtooth).
- **Victim variety:** latency-sensitive (current `critical_app`) and throughput-sensitive (rates measured, stalls visible).
- **Realistic servers (nginx+wrk, Postgres+pgbench):** phase 2, after the first batch — they need installed packages and behave differently; also add at least one non-WSL run if a second machine ever appears.
- **Every run saves its seed + drawn config** in `scenario.json` → fully reproducible.

## Feature spec (the model's input) — rates/deltas, not cumulative lore

Per state (1–2 s ticks), computed by `featurize.py`:
- neighbor: cpu throttled **us/s over 10 s**, cpu PSI avg10, memory.current, headroom (high − current), memory.events.high **per 30 s**, io wbytes **MB/s over 10 s**, pids, pids delta
- victim: latency p95 over last 10 s (or throughput deviation), victim PSI cpu/mem
- system: PSI cpu/mem/io avg10 + **slope** (avg10 − avg60); load1
- context: **previous action** (one-hot), **seconds since last action**

Dropped from model input: raw cumulative counters (throttled_usec, total wbytes, events counters) and anything that encodes *where in the run we are* (timestamps, phase labels) — those let a model memorize run position and look smart. Raw values stay in the raw files (for debugging/analysis) but don't reach training.

## Labeling (v2)

- **Rules runs (~70 %):** label = what the rules teacher decided.
- **Exploration runs (~30 %):** controller picks among **safe actions only** (`do_nothing`, `increase_cpu`, `decrease_cpu`, `increase_memory`, `decrease_memory`, `throttle_io`, `restrict_process_count`, `protect_service`) with weighting toward underrepresented classes; safety envelope unchanged (never kill/restart/isolate).
- **Outcome score** per decision (from the existing outcome window logic): improved/unchanged/harmful, from
  `victim_p95_delta + system_psi_cpu_delta + neighbor_psi_deltas − penalties (OOM, throttling growth)`.
  - Training weight: 1.0 good/neutral · 0.2 harmful · raw score kept in the row for analysis.
- **Counterfactuals (deferred):** replay the same seed with a forced different action. Phase 3 — after the first big batch proves the fundamentals.

## Class balance

- Targeted scenarios per rare class: a memory-grower that reliably hits `memory.high` (→ `increase_memory` rows on demand); pids spike (→ `restrict_process_count`); etc.
- Track per-class counts after every batch; add targeted scenarios until every class has ≥200 rows.
- Use the row `weight` field at training time rather than duplicating rows.

## Splits (this matters)

- **By run, never by row.** Consecutive rows of one run are near-duplicates — row-splits leak.
- Batch of N runs → ~75 % train / 25 % heldout, whole runs, split manifest saved.
- Goal after scaling: at least one heldout set from a **different machine/WSL config**; not possible yet (single machine) — noted.

## Sizing — what's enough

| Rows | What it can do | Verdict |
|---|---|---|
| ~300 (v1+v2 today) | trains, but memorizes one run; held-out looks good for the wrong reason | pipeline proof only (M2 pilot) |
| ~3,000 | common patterns learned; rare actions shaky; held-out-by-run becomes honest | first real signal |
| **~8–10k** (batch 1: 60 runs × ~130 rows) | teacher policy learnable AND generalizable across unseen runs; every class ≥200 | **initial training target** |
| ~25–30k (batch 2) | solid; near the ceiling of one machine's data (the platform cap: 50k rows/dataset) | later |

Two minimums must both hold for "enough": **≥200 examples per reachable class** (targeted scenarios enforce this) and **≥15 held-out runs** for a valid exam. Diversity beats volume — the randomized generator is what makes 60 runs ≈ 9k *effective* rows.

## Run plan

| Batch | What | Size | Time |
|---|---|---|---|
| 1 | Pipeline shakeout (mix rules/exploration) | **60 runs** (~4 min each) | ~4–5 h (overnight) |
| 2 | Full scale-out | **200+ runs** | ~13 h (overnight) |

Cost: **$0** (wall-clock only). Runs are strictly sequential — parallel runs would contaminate the telemetry.

## Sampling / noise

- 2 s ticks kept; idle stretches trimmed by the featurizer (do_nothing-while-idle must not dominate).
- Hard negatives included by design (spike/self-resolve type).
- Add mild background noise (a small random sleeper process per run) so the model doesn't depend on a spotless lab.

## Order of work

1. Build pipeline scripts (agents) + freeze interfaces → smoke test on 3 short runs.
2. M2 **pilot** on merged v1+v2 (324 rows) whenever `PLATFORM_API_KEY` is set — validates the platform plumbing + the live dashboard on a small, fast run.
3. Overnight batch 1 (60 runs) → inspect → batch 2 (200+).
4. M2 **real**: fine-tune on dataset v2, evaluate against rules on held-out runs, live dashboard.

## Open decisions (user)

1. Workloads: stdlib-only v1 now, nginx/Postgres in phase 2? (recommended)
2. Batch 1 = 60 runs first, then scale? (recommended)
3. M2 pilot before/after the overnight batch? (recommended: pilot first)
