# WorkloadPilot

**A decision model for Linux resource management.** It watches cgroup v2 telemetry (PSI pressure, CPU throttling, memory headroom/events, IO writes, pid counts) and picks one of **12 resource actions** — `do_nothing`, `increase_cpu`, `decrease_cpu`, `increase_memory`, `decrease_memory`, `throttle_io`, `restrict_process_count`, `protect_service`, `isolate_workload`, `restart_service`, `kill_process`, `alert_operator` — behind a safety gate, with every decision and its outcome logged.

The kernel stays the deterministic enforcement layer. The model decides; cgroups enforce.

## Architecture

```
cgroup v2 telemetry (every 2 s)
        │
        ▼
┌──────────────────┐       decision call          ┌──────────────────────────┐
│  M3 live loop     │ ────────────────────────────▶ │  hosted decision model    │
│  (featurize,      │ ◀──────────────────────────── │  (base: decider-2b)       │
│   safety gate,    │        typed probabilities    └──────────────────────────┘
│   actuator,       │
│   outcome log)    │ ── shadow ──▶ continuous model (learns from traffic + corrections)
└──────────────────┘
        │
        ▼
  cgroup writes (cpu.max, cpu.weight, memory.high, pids.max, io.max)
```

Build order: **M0** measurement rig → **M1** rules teacher + dataset collection → **M2** hosted fine-tunes → **M3** closed loop with safety gate → **continuous learning**.

## Results (current model: `v3-2b`)

**Offline exam** — 2,640 held-out rows, 12-way action choice:

| Metric | Value |
|---|---|
| Accuracy | **88.4 %** |
| Macro-F1 | **0.663** |
| Calibration (ECE) | **0.0475** |
| Classes with meaningful recall | 8 / 9 present in data |

The four classes that were previously **impossible to learn** (a data-bound defect) are now alive: `decrease_cpu` 0.27, `decrease_memory` 0.48, `throttle_io` 0.61, `protect_service` 0.75. `restrict_process_count` (77 training rows) remains weak at 0.03 — the next data cycle targets it.

**Independent audit** (unseen scenario seeds, different machine):

- Unseen seeds: **95.5 %** (base model 71.3 %)
- Contributor hardware: **83.1 %** (base model 70.9 %)
- Serving latency: p50 366 ms · p95 542 ms

**Live closed loop** — 1-hour unscripted stress soak:

- 1,754 decisions at 30/min, **zero model errors**
- Real give-backs: `decrease_cpu` lowered `cpu.max` 100 % → 60 % when load dropped (the static baseline never gave anything back)
- Static-vs-controlled A/B: **−37 % CPU allocation** overall, **−70 %** in idle tail

**Public benchmark** (JevBench, decision models): the base family sits ~#30/70; our served path answered **76.2 %** argmax vs the published author-server's 71.0 % on identical items.

**Continuous learning** — a live learner seeded with 5,808 teacher-labelled rows reached **84.7 %** on the same exam (preview version, not yet promoted over `v3-2b`).

## Repo layout

| Path | Contents |
|---|---|
| `workloadpilot-m0-m1.md` | living project notes: status, findings, decisions |
| `lab-scripts/` | the lab kit: `scenario`/stress apps, `sampler.py`, **`rules.py`** (teacher), **`actuator.py`**, dataset pipeline (`dsv2/`) |
| `m2-pilot/` | evaluation/reporting scripts + result summaries (the private-beta platform SDK's training/serving scripts are not included) |
| `results/` | eval reports (HTML), per-class graphs, run summaries (raw rows excluded) |
| `m3-tour/`, `m3-soak/`, `m3-soak2/` | closed-loop live-test reports, charts, head-to-heads |
| `demo-outcomes/` | static-vs-controlled demo: report, charts, 2-minute script |
| `jevbench/` | public decision-model benchmark run (report, scores, pinned data) |
| `bundle/` | portable data-collection kit for Linux contributors (tar + preflight/collect scripts) |
| `share/` | comparison images and eval reports used for external review |
| `dataset/` | dataset sizing/collection plan |

Raw datasets and per-row evaluation files are **not** in this repo (reproducible; stored with the training platform).

## How it is built

- **Lab:** WSL2 Ubuntu distro, disposable. Scripts live in `lab-scripts/` (mirrors of the lab).
- **Teacher:** `rules.py` — deterministic, 12-action policy with explicit thresholds (PSI, throttle rate, memory ratios, pid deltas), debounced release logic.
- **Data pipeline:** scripted scenarios (victim + stressor, each in a systemd cgroup unit, own limits) → 2 s telemetry → teacher decisions → labeled rows, split by **run** (not row).
- **Training:** hosted decision-model platform (`decider-2b` base; LoRA). Recipe: inverse-frequency class weights capped 10× + soft targets + per-epoch probes.
- **Serving:** one synchronous decision call per row over the platform API — typed 12-way choice with calibrated probabilities (no free-text parsing).
- **Safety gate:** 12-action allow-list, human-approval actions blocked, parameter clamps, per-action cooldown, target restricted to the managed `wlp-*` cgroups, dry-run default.
- **Continuous learning:** shadow mode — production model serves, a continuous model learns from the same traffic; teacher disagreements become corrections (confidence- and rate-gated).

## Status & limitations

- Tested in synthetic scenarios on WSL2, plus one external contributor machine. **Not** deployed in production.
- Feature set (29 features) lacks explicit long-window state (35 s PSI history, previous-row counters), which caps some classes — known, planned next step.
- The 12-action vocabulary is opinionated; per-environment adaptation is expected.
- Training/serving scripts depend on a private-beta platform SDK and are therefore not included; the lab-side pipeline, evaluation tooling and all results are.

## Credits

- Base model: `decider-2b` (Mapika)
