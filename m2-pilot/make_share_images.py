"""Build the share/ folder for the platform team package: comparison images + per-model graphs + reports."""
import json
import shutil
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
R = HERE / "results"
SHARE = HERE.parent / "share"
SHARE.mkdir(exist_ok=True)

MODELS = ["v2-2b", "v2-4b-r2", "v3-pplx"]
LABELS = ["do_nothing", "increase_cpu", "increase_memory", "restrict_process_count", "alert_operator",
          "decrease_memory", "decrease_cpu", "throttle_io", "protect_service"]

summaries = {}
pairsets = {}
for m in MODELS:
    summaries[m] = json.loads((R / "eval_summary-{}.json".format(m)).read_text(encoding="utf-8"))
    pairs = []
    for line in (R / "{}-tuned_rows.jsonl".format(m)).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        target = row.get("target")
        label = next(iter(target)) if isinstance(target, dict) and target else target
        answer = row.get("answer") or {}
        if label:
            pairs.append((label, answer.get("choice")))
    pairsets[m] = pairs

# 1. overview bars + ECE
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.5, 4.4))
x = np.arange(len(MODELS))
w = 0.28
acc = [summaries[m]["accuracy"] for m in MODELS]
mf1 = [summaries[m]["macro_f1"] for m in MODELS]
ba = [summaries[m]["balanced_accuracy"] for m in MODELS]
ece = [json.loads((R / "{}-tuned.json".format(m)).read_text(encoding="utf-8"))["overall"].get("ece", 0) for m in MODELS]
ax1.bar(x - w, acc, w, label="accuracy")
ax1.bar(x, mf1, w, label="macro-F1")
ax1.bar(x + w, ba, w, label="balanced acc")
for i, v in enumerate(acc):
    ax1.text(i - w, v + 0.012, "{:.3f}".format(v), ha="center", fontsize=8.5)
for i, v in enumerate(mf1):
    ax1.text(i, v + 0.012, "{:.3f}".format(v), ha="center", fontsize=8.5)
for i, v in enumerate(ba):
    ax1.text(i + w, v + 0.012, "{:.3f}".format(v), ha="center", fontsize=8.5)
ax1.set_xticks(x, MODELS)
ax1.set_ylim(0, 1.02)
ax1.legend(fontsize=9, loc="lower right")
ax1.set_title("Held-out metrics (n=1640 rows, 15 held-out runs)")
ax2.bar(MODELS, ece, color="#e0784c")
for i, v in enumerate(ece):
    ax2.text(i, v + 0.004, "{:.3f}".format(v), ha="center", fontsize=9)
ax2.set_title("Calibration error ECE (lower = better)")
fig.tight_layout()
fig.savefig(SHARE / "01_overview_metrics.png", dpi=150)
plt.close(fig)

# 2. per-class recall heatmap
mat = np.zeros((len(MODELS), len(LABELS)))
for i, m in enumerate(MODELS):
    for j, c in enumerate(LABELS):
        mat[i, j] = summaries[m]["per_class"].get(c, {}).get("recall", 0.0)
fig, ax = plt.subplots(figsize=(10.5, 3.7))
ax.imshow(mat, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")
ax.set_xticks(range(len(LABELS)), LABELS, rotation=32, ha="right", fontsize=9)
ax.set_yticks(range(len(MODELS)), MODELS, fontsize=9.5)
for i in range(len(MODELS)):
    for j in range(len(LABELS)):
        color = "black" if mat[i, j] < 0.75 else "white"
        ax.text(j, i, "{:.2f}".format(mat[i, j]), ha="center", va="center", fontsize=9, color=color)
ax.set_title("Per-class recall by model - note the four dead columns on the right", fontsize=11)
fig.tight_layout()
fig.savefig(SHARE / "02_per_class_recall_heatmap.png", dpi=150)
plt.close(fig)

# 3. confusion matrices side by side
fig, axes = plt.subplots(1, 3, figsize=(16, 5))
for ax, m in zip(axes, MODELS):
    cm = np.zeros((len(LABELS), len(LABELS)), dtype=int)
    for label, pred in pairsets[m]:
        if label in LABELS and pred in LABELS:
            cm[LABELS.index(label), LABELS.index(pred)] += 1
    ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(LABELS)), LABELS, rotation=90, fontsize=6.5)
    ax.set_yticks(range(len(LABELS)), LABELS, fontsize=6.5)
    for i in range(len(LABELS)):
        for j in range(len(LABELS)):
            if cm[i, j] > 0:
                ax.text(j, i, str(cm[i, j]), ha="center", va="center", fontsize=6)
    ax.set_title(m, fontsize=10)
fig.suptitle("Confusion matrices - held-out runs (n=1640 each)", fontsize=11)
fig.tight_layout()
fig.savefig(SHARE / "03_confusion_side_by_side.png", dpi=150)
plt.close(fig)

# copy per-model graphs + HTML reports
for m in MODELS:
    for g in ("confusion_matrix", "calibration", "selective", "per_class", "distribution"):
        src = R / "graphs-{}".format(m) / "{}.png".format(g)
        if src.exists():
            shutil.copy(src, SHARE / "{}_{}.png".format(m, g))
    report = R / "EVAL-REPORT-{}.html".format(m)
    if report.exists():
        shutil.copy(report, SHARE / report.name)

print("share folder:", SHARE)
for f in sorted(SHARE.iterdir()):
    print("  ", f.name)
