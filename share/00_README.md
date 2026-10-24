# Share folder — the platform team package (Oct 17)

Everything here is ready to **attach to the update message** for the platform team. All images were generated from the same held-out evaluation data (1,640 rows, 15 held-out runs) — nothing is mocked up.

## Attach these three (the story in three images)

| File | What it shows |
|---|---|
| `01_overview_metrics.png` | The headline: accuracy / macro-F1 / balanced accuracy for all three models + calibration error (ECE) |
| `02_per_class_recall_heatmap.png` | The killer visual — per-class recall per model, with the **four dead columns** on the right (`decrease_memory`, `decrease_cpu`, `throttle_io`, `protect_service`) |
| `03_confusion_side_by_side.png` | All three confusion matrices side by side |

## Attach if he wants full detail (or screenshot pages)

| File | What it is |
|---|---|
| `EVAL-REPORT-v2-2b.html` | Full report: `decider-2b` 87.5%, ECE 0.113 |
| `EVAL-REPORT-v2-4b-r2.html` | Full report: `decider-4b` 87.6%, ECE 0.081 (recipe v3) |
| `EVAL-REPORT-v3-pplx.html` | Full report: `pplx-27b` + readout 87.3%, ECE 0.143 |

Open the HTMLs in a browser (double-click). Each contains the confusion matrix, calibration bands, per-class table, and the top mistakes.

## Per-model graph copies (deeper review)

`v2-2b_*.png`, `v2-4b-r2_*.png`, `v3-pplx_*.png` — calibration curve, per-class bars, selective accuracy, distribution check, confusion matrix — one set per model.

## Source of truth

Raw results: `..\m2-pilot\results\` (eval summaries, per-row data, metrics JSONs). Main notes: `..\workloadpilot-m0-m1.md`.
