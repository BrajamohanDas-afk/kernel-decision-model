# Dataset v2 — build report (Oct 15, 2026)

*60 scripted runs (seeds 2000–2059, ~70% rules / 30% exploration), run-level splits, rate/delta features.*

## Totals

| Split | Runs | Rows |
|---|---|---|
| **train** | 45 (seeds 2000–2058, every 4th held out) | **4,888** |
| **heldout** | 15 (seeds …,2055, 2059 — *entire runs, never trained on*) | **1,640** |

Build log: `ok=60 fail=0`. Files: `train.jsonl`, `heldout.jsonl`, `analysis.jsonl`, `manifest.json`, `class_counts.json`.

## Class coverage (train / heldout)

| Action | Train | Heldout | vs ≥200-target |
|---|---|---|---|
| do_nothing | 3,414 | 1,054 | ✅ (dominant, as expected) |
| increase_memory | 583 | 266 | ✅ |
| increase_cpu | 554 | 180 | ✅ |
| protect_service | 73 | 31 | ⚠️ thin |
| restrict_process_count | 66 | 26 | ⚠️ thin |
| throttle_io | 57 | 20 | ⚠️ thin |
| decrease_memory | 52 | 25 | ⚠️ thin |
| decrease_cpu | 44 | 18 | ⚠️ thin |
| alert_operator | 45 | 20 | ⚠️ thin (was **0** in M1 data — now learnable) |
| isolate/restart/kill | 0 | 0 | by design — never automatic |

## Verdict

- **A real step up from the pilot:** 4.9k rows vs 324; 9 action classes vs 3; whole runs held out vs row-level split; rate features vs cumulative counters; 45 exploration-generated examples where the rules never fired (`alert_operator` fixed, `increase_memory` 45× richer).
- **Notable:** `do_nothing` is 70% of train — natural for this lab (most time is calm), handled at training time with capped class weights (sqrt-rebalance, cap 8×) rather than deleting rows.
- **If the trained model shows weak classes** (expected for the thin six), **batch 2 targets them**: e.g., a throttle-heavy scenario mix (fewer io-calm runs), more pids-spike scenarios, more alert-edge runs. 30–40 more runs ≈ +3k rows ≈ 2h.

*Generated automatically from the build manifest; mirrors live in `results\dataset-v2\`.*
