# JevBench run — workloadpilot/decider-2b and workloadpilot/v3-2b

Run date: 2026-10-18 (UTC). Everything below is measured; nothing is estimated except where marked.
No API key material is stored in any artifact in this folder.

## TL;DR

| Model | Items | Intelligence (public-231) | Calibration (v1.3-compat., hard) | Speed (client obs.) | Cost ($/1k dec.) | Indicative composite |
|---|---:|---:|---:|---:|---:|---:|
| `workloadpilot/decider-2b` (base) | 231 | 43.61 | 50.27 | 74.58 | $0.006957 → 74.73 | **43.71** |
| `workloadpilot/v3-2b` (fine-tune) | 231 | 34.97 | 51.40 | 74.39 | $0.008353 → 72.34 | **25.98** |
| published `decider-2b` (v1.5.4 board) | 1,624 | 42.34 | 71.53 | 94.40 | $0.014771 → 64.92 | **45.10, #30** |

The composite is a public-split analogue assembled with the official v1.5 headline-A formula, not the official score
(see [Why this is not the official score](#why-this-is-not-the-official-score)). The fine-tune does **not** improve on
JevBench: it matches the base on choice within 1 competence point, is ~2 points lower on score, and loses ~23
competence points on `noul`, largely because it abstains on 56.8% of Noul items (the v1.5 rule abstains between
P(yes) 0.2 and 0.8 and counts that as wrong).

## 1. Reference verification (read this first)

The brief's reference points match **JevBench v1.5.4**, not the repo snapshot's latest committed results and not the
current v1.6.1 release:

| Reference (brief) | Found on v1.5.4 | Notes |
|---|---|---|
| decider-2b = 45.11, #30 | 45.098 → 45.10, #30 | rounding only |
| decider-4b v2 = 71.29, #7 | 71.285 → 71.28, #7 | rounding only |
| TypeSafe Jev 1.13 = 72.14, #3 | 72.128 → 72.13, #3 | rounding only |

Everything in this run is compared against **v1.5.4**, pinned artifact
`benchmarkheaven.com/api/jevbench/v1.5.4`, `source_sha256 = 452885de2a84cd5b9ed393d541fd8d6c6a540f9d7f762f9d2df9349383f26173`
(the benchlm.ai page mirrors this release). The repo clone (`fstandhartinger/jevbench @ 609a664`, 2026-10-15) carries the
v1.5 method but its own results artifacts stop at v1.4.2.2, where scoring is different (decider-2b = 61.68 there).
The live manifest now advertises **v1.6.1**, a different, newer protocol on which decider-2b is 7.67; releases
must not be mixed. The provided numbers are v1.5.4, so v1.5.4 is the comparison target.

## 2. Items used (what the "open split" actually exposes)

Official v1.5.4 open split: **904 decisions**, of which the method text calls 601 published; sealed is 720 decisions
(50% of official Intelligence). The public repo contains only the 231 v1.2 public items:

| Tier | choice | noul | score | total |
|---|---:|---:|---:|---:|
| easy | 36 | 12 | 0 | 48 |
| standard | 36 | 24 | 12 | 72 |
| hard | 67 | 38 | 6 | 111 |
| **total** | **139** | **74** | **18** | **231** |

Coverage of the official open split: 139/439 choice, 74/315 noul, 18/150 score — **231/904 = 25.6%**.
The **judge tier is entirely absent** (its 146 items are imported third-party text and are not redistributed), and all
held-out halves are absent. The 370 new v1.5 public drafts (120 authored + 250 drawn from the sealed pool) are described
as published in `docs/METHOD-v1.5.md` §1.1 but are **not present** in the repo tree or in the Benchmark Heaven
Hugging Face export (only aggregate leaderboard files are there). That is the concrete blocker for a full open-split run.

Sanity of the item files: 231/231 have a non-null `expected`, 0 with `exclude_reason`, 0 label-set violations.
Max choice options 6 (the platform limit 255), max score levels 5 (the platform limit 10) → **skips = 0**.

## 3. Adapter and scoring method

* Repo: `fstandhartinger/jevbench` @ `609a664e81f46e03731600bd7bd9f1b7a61257c5`; method
  `docs/METHOD-v1.5.md` + `docs/METHOD-v1.5-ADDENDUM-HEADLINE-A-EQUAL-TYPES.md` (headline A).
* Adapter: each item's `state`, `question.instructions` and `question.criteria` are passed verbatim as one the platform
  question (`{"state": ..., "questions": {"decision": {...}}}`). Criteria option order is the file order; no gold
  labels, no expected values, no prompt tuning. Noul answers are mapped `false/true → no/yes`; choice/score
  probabilities are used natively. All criteria came back with the exact label set for all 462 answers.
* Calls: `client.predict(model, rows)` in chunks of 50 (5 chunks per model), `progress=False`. Every chunk succeeded on
  the first attempt; there were **0 failures, 0 fallbacks**. 231 valid distributions per model (sums within 2e-7 of 1).
* Competence (v1.5 §3):
  * choice `CC = 100·(acc − c̄)/(1 − c̄)`, `c̄` = mean 1/options over the cell;
  * noul: P(yes) ≤ 0.20 → No, ≥ 0.80 → Yes, between → abstention counted wrong; `CC = 100·(acc − 0.5)/0.5`;
  * score: `CC = 100·(1 − mean nMAE / mean nMAE_chance)`, prediction = expected position `Σ k·pₖ`;
  * per-tier weights 0.10/0.20/0.30/0.40 (renormalised when a tier has no items — no judge here);
  * equal type weights (1/3 each), then clipped to [0, 100] for the axis.
* Calibration: JevBench's own `composite_v13.calibration` semantics on **public hard-tier items** (top-label ECE on
  111 items + 100·(1 − mean TVD) on the 67 hard choice items, averaged). This is the definition their committed code
  supports. The v1.5 typed calibration (pooled open+sealed, 50/25/25 type weights) uses a scorer that is **not in the
  public repo** and whose score-family term cannot be reconstructed exactly from published aggregates, so it is not
  claimed here.
* Speed: 57–58 serial single-row calls per model, wall time from this Windows host to the platform API, network included;
  score `100 − 20·log10(s/0.1)`, mean of p50 and p95, no load adjustment.
* Cost: the platform's own usage ledger delta over the run window; decider-2b input price $0.007/M, no output tokens.
* Composite: harmonic mean (`p = −1`) with equal 25% axis weights and the official gates (I, Speed, Cost each square
  their axis/50 when below 50).
* **Scoring arithmetic was re-verified against their code**: our v1.3-compatible calibration, speed points, cost axis
  and harmonic composite match `jevbench.composite_v13` / `composite_v14` to machine precision (0.0 difference).

Raw per-item predictions, per-chunk logs and the latency samples are in `predictions/`.

## 4. Results

### 4.1 Per-type competence (public 231, v1.5 definitions)

| Model | choice CC (acc) | noul CC (thr. acc / argmax acc) | score CC (argmax acc) | Intelligence |
|---|---:|---:|---:|---:|
| `workloadpilot/decider-2b` | 63.81 (0.770) | −6.14 (0.486 / 0.716) | 73.17 (0.889) | **43.61** |
| `workloadpilot/v3-2b` | 62.81 (0.763) | −28.82 (0.365 / 0.662) | 70.93 (0.889) | **34.97** |
| published decider-2b, open split (904 items, from the v1.5.4 artifact) | 52.02 | 35.24 | 59.11 | 48.79 (`I_open`) |

Per-tier detail (CC / accuracy / n):

| | choice easy | choice std | choice hard | noul easy | noul std | noul hard | score std | score hard |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| decider-2b | 100.00 / 1.000 / 36 | 93.01 / .944 / 36 | 40.16 / .552 / 67 | 100.00 / 1.000 / 12 | −8.33 / .458 / 24 | −31.58 / .342 / 38 | 82.13 / 1.000 / 12 | 68.68 / .667 / 6 |
| v3-2b | 100.00 / 1.000 / 36 | 89.51 / .917 / 36 | 40.16 / .552 / 67 | 66.67 / .833 / 12 | −50.00 / .250 / 24 | −42.11 / .289 / 38 | 82.99 / 1.000 / 12 | 64.90 / .667 / 6 |

Noul diagnostics (threshold rule is why this axis is negative):

| Model | abstention rate | accuracy on answered | Brier(P(yes)) | accuracy argmax |
|---|---:|---:|---:|---:|
| decider-2b | 40.5% | 81.8% | 0.1962 | 71.6% |
| v3-2b | 56.8% | 84.4% | 0.1958 | 66.2% |
| published decider-2b, all 495 open+sealed noul items | 22.4% | — | — | — |

### 4.2 Axes and indicative composite

| Model | Intelligence | Calibration (v1.3 hard) | Speed | Cost | Composite (v1.5 A formula) |
|---|---:|---:|---:|---:|---:|
| decider-2b | 43.61 | 50.27 (ECE 0.2640, TVD 0.4666) | 74.58 (p50 1.795 s, p95 1.941 s) | 74.73 ($0.006957/1k) | **43.71** |
| v3-2b | 34.97 | 51.40 (ECE 0.2184, TVD 0.5353) | 74.39 (p50 1.843 s, p95 1.976 s) | 72.34 ($0.008353/1k) | **25.98** |
| published decider-2b (v1.5.4) | 42.34 | 71.53 | 94.40 | 64.92 | **45.10 (#30)** |

Other diagnostics: paraphrase consistency over the 36 paired public items — base 31/36 (86.1%), v3 29/36 (80.6%).
Hard-tier family accuracy for both models is in `scores.json` (`hard_by_family`).

### 4.3 Sanity check against the published run, same 231 items

The repo publishes per-item outcomes for the author's own decider-2b run on the 231 public items
(`results/v1.2/jevbench-v1.2-per-task.json`). Comparing argmax correctness item by item:

| Tier | n | the platform decider-2b | the platform v3-2b | published run, same items |
|---|---:|---:|---:|---:|
| easy | 48 | 1.000 | 1.000 | 1.000 |
| standard | 72 | 0.889 | 0.847 | 0.847 |
| hard | 111 | 0.577 | 0.559 | 0.495 |
| all | 231 | **0.762** | **0.740** | **0.710** |

Item-level agreement with the published run: base 195/231 (84.4%), v3 192/231 (83.1%). Under the same renormalised
tier weights used above, the published run's public-only choice CC is 60.53 (our base 63.81, v3 62.81). So the platform
serving is not a worse decision-maker on these items — it is **slightly better on argmax** — but its Noul readout is
much softer, which the official 0.2/0.8 threshold rule punishes.

Base and fine-tune agree on 203/231 labels (87.9%), with no confident disagreements (both > 0.95), so the fine-tune is
a close variant rather than a different decision policy. Context: `v3-2b` scores 88.4% on its own workloadpilot
held-out set (`m2-pilot/results/eval_summary-v3-2b.json`); that in-domain accuracy does not transfer to JevBench.

## 5. Why this is not the official score

The published decider-2b score (45.10) and our indicative composite (43.71) are numerically close by coincidence, not
agreement. The inputs differ in five ways:

1. **Scope.** Official I = 50% open (904) + 50% sealed (720). Ours = 231 public items, 0 sealed. Sealed is the half the
   benchmark holds out; it cannot be run.
2. **Difficulty mix.** No judge tier at all, and only the public halves of the other tiers. Published per-tier figures
   mix public and unpublished items, so our per-tier numbers and theirs are not the same population.
3. **Calibration definition.** Ours is v1.3-compatible hard-tier ECE+TVD (50.3/51.4). The official v1.5 typed
   calibration is pooled over open+sealed and worth 71.53 for decider-2b; with the same calibration the composites
   would move materially upward. This is the largest single non-comparable axis here.
4. **Serving path.** the platform vs the author's own TypeSafe-compatible server: same items, 84.4% item agreement, and a
   Noul abstention rate of 40.5% (the platform base) vs 22.4% published (different mixes, but the direction is large). Part of
   the noul gap may be the platform's hosted readout or a different base revision; it was not tuned away.
5. **Speed and cost basis.** Official Speed is measured from a Hetzner host in Germany (adjusted for self-hosting);
   ours is client-observed from this Windows machine. Official Cost is a modeled hosted price; ours is the platform's actual
   billed rate ($0.007/M input). Both happen to favor our run in the composite.

Do not put 43.71 / 25.98 on a JevBench leaderboard. They describe the 231-item public subset only.

## 6. Costs (exact, from the platform usage ledger)

| Item | Input tokens | USD |
|---|---:|---:|
| `workloadpilot/decider-2b` — 231 predictions + 58 latency probes | 229,589 | $0.001607 |
| `workloadpilot/v3-2b` — 231 predictions + 58 latency probes | 275,658 | $0.001930 |
| 3-item wire-shape probe (both models) | 5,670 | $0.000040 |
| **JevBench inference total** | **510,917** | **≈ $0.00358** |

Budget cap was ~$2 → **0.18% used**. Token price $0.007/M input, output free. Earlier training runs on this project
(≈$2.3 of GPU time) are separate work and not counted here. One latency-probe call returned a transient
`DownloadError`; the main 462 predictions had no errors.

## 7. Limitations

1. Public-only, 25.6% of the open split; no sealed items; no rank is possible.
2. No judge tier; tier weights renormalised over easy/standard/hard.
3. Noul thresholds interact with the serving stack: the platform's readout is softer than the author's server. The benchmark's
   official run for decider-2b abstains 22.4%; the platform-served base abstains 40.5% on the public Noul items. Cause
   (serving calibration vs base revision) is not isolatable from outside.
4. Calibration uses their committed v1.3 code path, not the v1.5 typed scorer (not public).
5. Latency is client-side, n≈58, single origin, network included; not comparable to the board's numbers.
6. Score-family n=18 → score CC rests on 18 items and is correspondingly noisy.
7. `workloadpilot/decider-2b` is the platform's hosted base; the exact upstream revision is not shown by the API, so it may
   not be byte-identical to the board's pinned `Mapika/decider-2b b37f7e1 (v10)`.
8. The 370 new v1.5 public decisions are not in the public repo/HF export, despite the method calling them published.
   If they appear, re-run `scripts/run_jevbench.py` on the full 601-item public set.
9. One run, no repetitions; no per-item answer was hand-edited or repaired.

## 8. Files

| Path | Contents |
|---|---|
| `report.md` | this report |
| `scores.json` | every axis, per-type/per-tier breakdown, calibration parts, costs, usage rows, same-items comparison |
| `predictions/decider-2b.jsonl`, `predictions/v3-2b.jsonl` | raw per-item predictions: probabilities, predicted label, correctness, nMAE |
| `predictions/*-chunks.json` | per-chunk timing and answers (all first-try) |
| `predictions/*-latency.json` | serial latency samples and errors |
| `scripts/probe.py` | 3-item wire-shape probe |
| `scripts/run_jevbench.py` | adapter + predictions + first-pass scoring |
| `scripts/finalize_scores.py` | measured-cost attribution, diagnostics, final `scores.json` |
| `reference.json` | published v1.5.4 rows for decider-2b / decider-4b v2 / Jev 1.13.0 |
| `data/v1.5.4.json`, `data/v1.6.1-results.json` | pinned reference artifacts |
| `repo/` | clone of `fstandhartinger/jevbench` @ `609a664` (shallow, then unshallowed to check for a v1.5 scorer/draft) |

Reproduce:

```powershell
$env:PLATFORM_API_KEY = [Environment]::GetEnvironmentVariable('PLATFORM_API_KEY','User')   # never printed
$py = "C:\Users\Braju\AppData\Local\Temp\opencode\m2-venv\Scripts\python.exe"
& $py "C:\MyFile\Study material\kernel decision model\jevbench\scripts\probe.py"
& $py "C:\MyFile\Study material\kernel decision model\jevbench\scripts\run_jevbench.py"
& $py "C:\MyFile\Study material\kernel decision model\jevbench\scripts\finalize_scores.py"
```
