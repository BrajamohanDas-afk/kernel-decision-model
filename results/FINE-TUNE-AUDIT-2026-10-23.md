# Fine-tune audit — `workloadpilot-v3-2b` (2026-10-23)

**Question:** did fine-tuning `mapika/decider-2b` actually improve the controller, or did we only
see a low training loss?

**Verdict:** yes, this is a real improvement on the task it was trained for — but the dashboard's
`loss 0.055` and `accuracy 100%` are **not** validation metrics and must not be quoted as such.
The model generalizes to unseen runs (+20.7 points over base), to four brand-new scenario seeds
(+24.1), and to a different machine (+12.2), while remaining weak on five rare action classes and
on states whose labels depend on information the features do not contain.

---

## 1. What the dashboard numbers actually are

| Claim | What it actually is | Independent measurement |
|---|---|---|
| loss **0.055** | the *last training batch* loss (single step 3086) | last-500-step mean **0.307**; first-500 mean 0.547; 300-step bin means 0.59 → 0.34 (noisy, plateau after ~2.1k steps) |
| accuracy **100%** | model metadata (`accuracy: 1.0`), not reproducible | full train set (8,230 rows): **92.48%**; 1,200-row random train sample: **93.92%**; heldout: **88.41%** |
| validation loss | **not logged** — the run has `train/loss` and `probe/acc`, no `probe/loss` | probe accuracy is the validation signal we have |

Validation probe (same run, from `runs.get(...).metrics()`):

| step | probe acc | probe macro-recall |
|---|---|---|
| 1,029 | 85.15% | 0.454 |
| 2,058 | **86.06%** | 0.602 |
| 3,087 (final) | 85.76% | 0.594 |

Probe accuracy peaked around step 2,058 and was 0.3 points lower at the final step. Training loss
was still slowly decreasing. That is **mild overfitting / no early stopping**, not divergence.
The checkpoint that shipped is slightly past the best validation point.

## 2. Test setup

| Set | Rows | Runs | Seen in training? |
|---|---|---|---|
| `dsv3_heldout` | 2,640 | 23 whole runs (seeds 2003…3031) | no (whole-run split; every 8th row was used as the training probe) |
| fresh seeds `4000–4003` | 506 | 4 new runs, rules-labelled | no — generated **after** training |
| friend machine | 2,491 | 24 runs, same seeds on different hardware | no (delivered after training) |
| train random sample | 1,200 | — | yes (memorization check) |
| full train set | 8,230 | — | yes (checks the 100% claim) |

Model: `workloadpilot-v3-2b`, LoRA rank 16 on `mapika/decider-2b`, 3,087 steps, production since
2026-10-22. All comparisons use the same rows and the same serving/eval stack. Fresh seeds were
generated with the rules teacher in `wlp-lab` after the model was frozen.

## 3. Headline results

| Set | v3-2b acc | base acc | Δ | v3-2b macro-F1 | base macro-F1 | v3-2b ECE | base ECE |
|---|---|---|---|---|---|---|---|
| heldout | **88.41%** | 67.73% | **+20.68** | 0.666 | 0.266 | 0.046 | 0.120 |
| fresh seeds | **95.45%** | 71.34% | **+24.11** | 0.765 | 0.267 | 0.021 | 0.161 |
| friend hardware | **83.10%** | 70.90% | **+12.20** | 0.451 | 0.268 | 0.084 | 0.145 |
| train sample (leak) | 93.92% | 73.67% | +20.25 | 0.755 | 0.272 | 0.017 | 0.143 |

Balanced accuracy (mean recall over present classes): heldout 0.642 vs 0.275; friend 0.470 vs
0.282. Agreement between the two models is 72.2% on heldout and 67.8% on friend data — the
fine-tune changes the policy substantially, it is not a cosmetic shift.

## 4. Where it improved and where it still fails

Recall by class (heldout → fresh seeds → friend):

| Class | support (heldout) | v3-2b | base | fresh v3-2b | friend v3-2b |
|---|---|---|---|---|---|
| do_nothing | 1,595 | 0.955 | 0.955 | 0.972 | 0.970 |
| increase_cpu | 226 | 0.925 | 0.770 | n/a (0 rows) | 0.911 |
| decrease_cpu | 41 | 0.293 | 0.049 | 0.500 (4) | 0.042 |
| increase_memory | 371 | 0.914 | **0.000** | 1.000 | 0.944 |
| decrease_memory | 59 | 0.475 | **0.000** | 0.909 (11) | 0.091 |
| throttle_io | 123 | 0.610 | 0.650 | 0.843 | **0.172** |
| restrict_process_count | 32 | **0.031** | 0.000 | 0.000 (3) | 0.103 |
| protect_service | 165 | 0.752 | 0.048 | 1.000 | **0.000** (36) |
| alert_operator | 28 | 0.821 | **0.000** | 1.000 (4) | 1.000 |

The base model **never predicts increase_memory / decrease_memory / restrict / protect / alert**
on this distribution. The fine-tune unlocks all of them. But the same rare classes are still the
weak spot, and the drop on friend hardware is concentrated there: `throttle_io` 61% → 17%,
`protect_service` 75% → 0%, `decrease_memory` 48% → 9%. That is real domain shift, not noise
(2,491 rows).

Top heldout confusions: throttle_io → do_nothing (41), restrict → do_nothing (27),
do_nothing → increase_memory (27), do_nothing → alert (26), protect → do_nothing (25).
Confidently wrong (confidence ≥ 0.90) on 129/2,640 heldout rows (4.9%), 3/506 fresh (0.6%),
75/2,491 friend (3.0%). Calibration is decent overall but overconfident in the 0.7–0.9 bands
(e.g. 0.88 mean confidence → 82% actual).

## 5. Overfitting check

| Measure | Value |
|---|---|
| full-train accuracy | 92.48% |
| heldout accuracy | 88.41% |
| **gap** | **+4.07 points** (1,200-row sample gap: +5.51) |
| probe accuracy trend | 85.15 → 86.06 → 85.76 (flat/slightly down after step 2,058) |
| train loss (last-500 mean) | 0.307, still declining slowly at the end |

Interpretation: the model is **not** memorizing the training rows (a memorizer would show a much
larger train/heldout gap). It is also not fully converged on heldout quality — early stopping at
the step-2,058 probe would probably have produced a slightly better checkpoint. There is no
validation loss curve to inspect; the probe accuracy is the only validation signal.

## 6. Real inference behavior (serving path, `system_one`)

- 50 live requests per model: tuned p50 **366 ms**, p95 **542 ms**, max 1.45 s; base p50 333 ms,
  p95 458 ms. Tuned is slightly slower but the same order; its p95 is slightly above JevBench's
  500 ms upper reference.
- Stratified real-row probe (27 rows: 2 per class from heldout + 1 per class from friend):
  tuned 13/27, base 8/27. This oversamples rare classes on purpose, so it is not comparable to
  the 88.4% overall number — it shows the same rare-class weakness.
- Crafted edge cases (23, built with the real teacher + real featurizer):
  tuned 15/23, base 11/23. **All 10 “should do nothing” cases passed for the tuned model**
  (null units, NaN/Inf fields, high victim latency, high loadavg without PSI, high PSI without
  quota binding, io write without unit io pressure, and quiet states after `increase_cpu` /
  `throttle_io` / `alert` — no action inertia). The base model failed the `throttle_io` inertia
  case (kept throttling a quiet state).
- No forbidden action (`isolate_workload`, `restart_service`, `kill_process`) was predicted in
  any probe.
- Failures that matter:
  - `throttle_io` / `restrict_process_count` threshold cases → `do_nothing` (conservative).
  - `decrease_cpu` / `decrease_memory` release cases → `do_nothing` (**structural**, see §7).
  - both-units-pinned severe contention → `do_nothing` (should be `alert_operator`).
  - memory at `memory.max` / OOM → `increase_memory` (should be `alert_operator`; **structural**).

## 7. Doubts and limits (the honest part)

1. **The labels are teacher agreement, not real-world outcomes.** 88%/95% means “matches the
   rules teacher”; it does not prove the actions help the victim or the node. The M3 soak is the
   outcome-level evidence, and it is much thinner (one 58-min arc, 4 give-backs).
2. **Four classes are partially unlearnable from the current features.** The teacher labels
   `decrease_cpu` from up to 35 s of PSI history, `decrease_memory` from the *previous* row's
   memory ratio, and `alert_operator` from `memory.events.max/oom/oom_kill` or `memory.max`.
   None of those are in the 29-feature vector. The model can only guess them from proxies. This
   explains most of the residual rare-class errors and cannot be fixed by more training on the
   same features.
3. **`restrict_process_count` is effectively dead** (3.1% heldout, 0% fresh, 10% friend; only 77
   training rows). It was already the known straggler in the Oct-18 report.
4. **Friend-hardware transfer is uneven.** Overall +12.2 points, but `throttle_io` recall drops to
   17% and `protect_service` to 0% on the second machine. A 24-run, one-machine sample is not a
   production guarantee; run the same audit on a third machine or a real cluster before trusting
   the rare classes.
5. **The fresh-seed set has no `increase_cpu` rows** and is only 4 runs / 506 rows. The 95.5%
   headline is real but class coverage is thin (restrict n=3, alert n=4, decrease_cpu n=4).
6. **The heldout set was watched during training** (probe accuracy). Its 88.4% is a validation
   number, not a pristine test. The clean test is the fresh-seed 95.5% (and even that is one
   hardware/one teacher).
7. **The shipped checkpoint is not the best-validation checkpoint.** Probe accuracy peaked at
   step 2,058; the model was saved at 3,087. Re-training with early stopping is cheap.
8. **The “100%” metadata is wrong as a generalization claim.** It is not even the full-train
   accuracy (92.48%). Do not quote it.
9. **No validation loss exists** in the run metrics. If loss curves matter for future decisions,
   log a heldout loss per probe step.
10. **There is a second, unrelated new fine-tune**: `workloadpilot-live` v1 (continuous learning,
    245 decisions, loss 2.7324, reported accuracy 36.3%, **preview only, not production**). A
    30-row probe scored 18/30 (60%) but predicted `do_nothing` 26/30 times — it is mostly riding
    the do_nothing prior. It is not the 0.055/100% model and it is not ready to serve.

## 8. Verdict and next actions

**Call it a successful in-domain fine-tune, not yet a production success.**
The improvement is real and survives unseen runs, new seeds, and a different machine. The
dashboard numbers overstate certainty: the true numbers are 88.4% heldout, 95.5% fresh-seed,
83.1% cross-machine, with 0.67/0.77/0.45 macro-F1 and 0.046/0.021/0.084 ECE.

Cheapest next steps, in order:
1. Add `prev_psi_cpu`, `prev_mem_ratio`, `mem_max_ratio`, `mem_events_max/oom` to the feature
   vector — this directly targets the structural errors in §7.2.
2. Retrain with early stopping at the best probe step (~2,058) and log `probe/loss`.
3. Targeted `restrict_process_count` batch (the recipe already exists in `dsv2/`), plus a small
   class-weight boost; expect the biggest macro-F1 gain.
4. Re-run this audit on the friend machine's rare classes / a third machine; focus on
   `throttle_io` and `protect_service` transfer.
5. Only then promote; keep `workloadpilot-live` preview-only until it beats v3-2b.

## Update 2026-10-24 — continuous-learning v2 is not better than v3-2b

A new preview appeared overnight: `workloadpilot-live` **v2** (5,438 decisions, reported
accuracy **92.5%**, interval 88.7–95.2, loss 0.1802, against-accuracy 70.2, preview only).
That 92.5% is on the continuous project's own learning holdout, so I probed it on the same dsv3
rows. The continuous model has no dataset-eval API; this used 148 live `system_one` calls
(100 random + 48 rare-class rows) plus 36 friend rows, and compared against the already-recorded
v3-2b predictions on the identical rows.

| Slice | v2 (preview) | v3-2b | agreement |
|---|---|---|---|
| 100 random heldout rows | 90.0% | **91.0%** | 92% |
| 148 rows (rare-class oversample) | 77.0% | **79.1%** | 88.5% |
| 36 friend-hardware rows | **72.2%** | 66.7% | — |

Per class (147-row probe): v2 is better on `decrease_memory` (100% vs 67%) and `throttle_io`
(61% vs 50%), but worse on `increase_cpu` (63% vs 100%), `decrease_cpu` (0% vs 38%) and
`alert_operator` (0% vs 100%); `restrict` is 0% in both. The slices are small (2–8 rows for
several classes), so treat this as **no clear winner**, not as proof that v2 regressed.

**Verdict:** the 92.5% does not transfer to the dsv3 test rows; v2 is roughly tied with v3-2b
(90 vs 91 on the unbiased slice). Keep v3-2b serving. The continuous mechanism clearly improved
(v1 36.3% → v2 92.5% internal), but promoting v2 requires a larger same-row A/B (≥500 rows,
rare classes included), not the vendor's own holdout number.

## Artifacts

- `m2-pilot/audit_ft.py` — evaluations, metrics, serving probes
- `m2-pilot/audit_details.py` — confusion/calibration/confident errors
- `m2-pilot/audit_v2.py` — continuous-learning preview probe (v2 vs v3-2b on identical rows)
- `m2-pilot/gen_audit_cases.py` — teacher-consistent edge cases (runs in `wlp-lab`)
- `m2-pilot/run_unseen.sh` + `build_unseen.sh` — regenerate the fresh 4000–4003 test set in `wlp-lab`
- `m2-pilot/results/audit/` — all raw results, rows, `audit_summary.json`,
  `detailed_metrics.json`, `training_curve.json`, `behavior.json`, `continuous_v2_probe.json`
- fresh-seed runs: `wlp-lab:/root/workloadpilot/dsv2/runs-unseen` (seeds 4000–4003)
- training run: `run_Mc0yan8t4YXuLHsC` (the platform), W&B
  `https://wandb.ai/brajamohandas0390-kiit/platform-workloadpilot/runs/run_Mc0yan8t4YXuLHsC`
