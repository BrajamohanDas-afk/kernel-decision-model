"""Model evaluation report v2: per-class recall + macro-F1 headline, confusion matrix,
calibration bands, selective accuracy, mistakes table. Markdown + HTML output.

Usage:
  python eval_report.py                    # legacy pilot paths (tuned.json / tuned_rows.jsonl)
  python eval_report.py --name v2-2b       # results/v2-2b-tuned_rows.jsonl etc.
"""
import argparse
import collections
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def load_rows(path):
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def label_of(row):
    target = row.get("target")
    if isinstance(target, dict) and target:
        return next(iter(target))
    return target if isinstance(target, str) else None


def series(rows):
    out = []
    for row in rows:
        answer = row.get("answer") or {}
        pred = answer.get("choice")
        conf = answer.get("confidence")
        if conf is None and isinstance(answer.get("probabilities"), dict) and answer["probabilities"]:
            conf = max(answer["probabilities"].values())
        out.append((row.get("row"), label_of(row), pred, conf))
    return out


def class_metrics(pairs):
    """pairs: (label, pred). Returns (metrics dict, macro_f1, balanced_acc)."""
    labels = sorted({l for l, _ in pairs if l} | {p for _, p in pairs if p})
    stats = {l: {"tp": 0, "fp": 0, "fn": 0, "support": 0} for l in labels}
    for lab, pred in pairs:
        if lab in stats:
            stats[lab]["support"] += 1
        if lab == pred and lab in stats:
            stats[lab]["tp"] += 1
        elif pred in stats:
            stats[pred]["fp"] += 1
            if lab in stats:
                stats[lab]["fn"] += 1
    metrics = {}
    for l in labels:
        s = stats[l]
        prec = s["tp"] / (s["tp"] + s["fp"]) if (s["tp"] + s["fp"]) else 0.0
        rec = s["tp"] / (s["tp"] + s["fn"]) if (s["tp"] + s["fn"]) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        metrics[l] = {"precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3),
                      "support": s["support"], "predicted": s["tp"] + s["fp"], "correct": s["tp"]}
    macro_f1 = round(sum(m["f1"] for m in metrics.values()) / max(1, len(metrics)), 4)
    balanced = round(sum(m["recall"] for m in metrics.values()) / max(1, len(metrics)), 4)
    return metrics, macro_f1, balanced


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="")
    parser.add_argument("--results-dir", default=str(HERE / "results"))
    args = parser.parse_args()

    results = Path(args.results_dir)
    tag = ("-" + args.name) if args.name else ""
    tuned_rows_path = results / ("tuned_rows.jsonl" if not args.name else "{}-tuned_rows.jsonl".format(args.name))
    tuned_json_path = results / ("tuned.json" if not args.name else "{}-tuned.json".format(args.name))
    base_rows_path = results / ("baseline_rows.jsonl" if not args.name else "{}-baseline_rows.jsonl".format(args.name))
    base_json_path = results / ("baseline.json" if not args.name else "{}-baseline.json".format(args.name))

    tuned = series(load_rows(tuned_rows_path))
    base = series(load_rows(base_rows_path)) if base_rows_path.exists() else None

    pairs = [(lab, pred) for _, lab, pred, _ in tuned if lab]
    correct = sum(1 for lab, pred in pairs if lab == pred)
    accuracy = correct / max(1, len(pairs))
    metrics, macro_f1, balanced = class_metrics(pairs)

    classes = sorted(metrics)
    conf = np.zeros((len(classes), len(classes)), dtype=int)
    for lab, pred in pairs:
        if lab in classes and pred in classes:
            conf[classes.index(lab), classes.index(pred)] += 1

    graphs = results / ("graphs" if not args.name else "graphs-{}".format(args.name))
    graphs.mkdir(exist_ok=True)

    # 1. confusion matrix
    fig, ax = plt.subplots(figsize=(9, 7))
    ax.imshow(conf, cmap="Blues")
    ax.set_xticks(range(len(classes)), classes, rotation=45, ha="right")
    ax.set_yticks(range(len(classes)), classes)
    for i in range(len(classes)):
        for j in range(len(classes)):
            if conf[i, j]:
                ax.text(j, i, str(conf[i, j]), ha="center", va="center")
    ax.set_xlabel("predicted")
    ax.set_ylabel("true label")
    ax.set_title("Confusion matrix{} (n={})".format(" - " + args.name if args.name else "", len(pairs)))
    fig.tight_layout()
    fig.savefig(graphs / "confusion_matrix.png", dpi=140)
    plt.close(fig)

    # 2. calibration
    bins = [0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0001]
    cal_rows = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        sel = [(c, lab == pred) for _, lab, pred, c in tuned if c is not None and lo <= c < hi]
        if sel:
            cal_rows.append((lo, hi, len(sel), round(sum(c for c, _ in sel) / len(sel), 3),
                             round(sum(1 for _, ok in sel if ok) / len(sel), 3)))
    fig, ax = plt.subplots(figsize=(6.5, 6))
    ax.plot([0.5, 1], [0.5, 1], "--", color="gray", label="perfect calibration")
    if cal_rows:
        ax.plot([r[3] for r in cal_rows], [r[4] for r in cal_rows], "o-", color="#2563eb")
        for r in cal_rows:
            ax.annotate("n={}".format(r[2]), (r[3], r[4]), textcoords="offset points", xytext=(7, 6))
    ax.set_xlim(0.5, 1.02)
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("model confidence (bin mean)")
    ax.set_ylabel("actual accuracy")
    ax.set_title("Calibration / reliability{}".format(" - " + args.name if args.name else ""))
    ax.legend()
    fig.tight_layout()
    fig.savefig(graphs / "calibration.png", dpi=140)
    plt.close(fig)

    # 3. selective accuracy
    thresholds = [0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.93, 0.95, 0.97, 0.99]
    selective = []
    for t in thresholds:
        sel = [(lab == pred) for _, lab, pred, c in tuned if c is not None and c >= t]
        if sel:
            selective.append((t, round(len(sel) / len(tuned), 4), round(sum(sel) / len(sel), 4)))
    fig, ax = plt.subplots(figsize=(7.5, 5))
    if selective:
        ax.plot([s[1] for s in selective], [s[2] for s in selective], "o-", color="#059669")
        for s in selective:
            ax.annotate("t={}".format(s[0]), (s[1], s[2]), textcoords="offset points", xytext=(6, -12), fontsize=8)
    ax.set_xlabel("coverage (fraction auto-acted)")
    ax.set_ylabel("accuracy on covered")
    ax.set_ylim(0, 1.05)
    ax.set_title("Selective accuracy{}".format(" - " + args.name if args.name else ""))
    fig.tight_layout()
    fig.savefig(graphs / "selective.png", dpi=140)
    plt.close(fig)

    # 4. per-class recall
    fig, ax = plt.subplots(figsize=(9.5, 4.5))
    recalls = [metrics[c]["recall"] for c in classes]
    ax.bar(classes, recalls, color="#7c3aed")
    for i, c in enumerate(classes):
        ax.text(i, recalls[i] + 0.02, "{}/{}".format(metrics[c]["correct"], metrics[c]["support"]), ha="center", fontsize=9)
    ax.set_ylim(0, 1.15)
    ax.set_ylabel("recall")
    ax.set_title("Per-class recall{}".format(" - " + args.name if args.name else ""))
    plt.xticks(rotation=30, ha="right")
    fig.tight_layout()
    fig.savefig(graphs / "per_class.png", dpi=140)
    plt.close(fig)

    # 5. label vs prediction distribution
    tru = collections.Counter(l for _, l, _, _ in tuned if l)
    prd = collections.Counter(p for _, _, p, _ in tuned if p)
    allc = sorted(set(tru) | set(prd))
    xx = range(len(allc))
    fig, ax = plt.subplots(figsize=(9.5, 4.5))
    ax.bar([i - 0.2 for i in xx], [tru.get(c, 0) for c in allc], width=0.4, label="true labels")
    ax.bar([i + 0.2 for i in xx], [prd.get(c, 0) for c in allc], width=0.4, label="model predictions")
    ax.set_xticks(list(xx), allc, rotation=30, ha="right")
    ax.set_ylabel("rows")
    ax.legend()
    ax.set_title("Label vs prediction distribution (class-collapse check)")
    fig.tight_layout()
    fig.savefig(graphs / "distribution.png", dpi=140)
    plt.close(fig)

    mistakes = [(rid, lab, pred, c) for rid, lab, pred, c in tuned if lab and lab != pred]
    mistakes.sort(key=lambda m: -(m[3] or 0))

    summary = {
        "name": args.name or "pilot",
        "n": len(pairs),
        "accuracy": round(accuracy, 4),
        "macro_f1": macro_f1,
        "balanced_accuracy": balanced,
        "per_class": metrics,
        "true_distribution": dict(tru),
        "pred_distribution": dict(prd),
        "calibration_bands": [{"lo": r[0], "hi": r[1], "n": r[2], "mean_conf": r[3], "accuracy": r[4]} for r in cal_rows],
        "selective": [{"threshold": s[0], "coverage": s[1], "accuracy": s[2]} for s in selective],
        "mistakes": [{"row": r, "label": l, "predicted": p, "confidence": c} for r, l, p, c in mistakes],
    }
    (results / "eval_summary{}.json".format(tag)).write_text(json.dumps(summary, indent=2), encoding="utf-8")

    base_line = ""
    if base is not None:
        bpairs = [(l, p) for _, l, p, _ in base if l]
        bcorrect = sum(1 for l, p in bpairs if l == p)
        bacc = bcorrect / max(1, len(bpairs))
        base_line = "| base model | {:.1%} |".format(bacc)

    md = []
    md.append("# Evaluation report {} \n".format(args.name or "(pilot)"))
    md.append("## Headline\n")
    md.append("| metric | value |")
    md.append("|---|---|")
    if base_line:
        md.append(base_line)
    md.append("| **accuracy** | **{:.1%}** ({}/{}) |".format(accuracy, correct, len(pairs)))
    md.append("| **macro-F1** | **{}** |".format(macro_f1))
    md.append("| balanced accuracy (mean recall) | {} |".format(balanced))
    md.append("")
    md.append("## Per-class metrics\n")
    md.append("| class | support | predicted | precision | recall | F1 |")
    md.append("|---|---|---|---|---|---|")
    for c in classes:
        m = metrics[c]
        md.append("| {} | {} | {} | {} | {} | {} |".format(c, m["support"], m["predicted"], m["precision"], m["recall"], m["f1"]))
    md.append("")
    md.append("## Calibration bands\n")
    md.append("| confidence band | n | mean conf | actual accuracy |")
    md.append("|---|---|---|---|")
    for r in cal_rows:
        md.append("| {:.2f}-{:.2f} | {} | {} | {} |".format(r[0], r[1], r[2], r[3], r[4]))
    md.append("")
    md.append("## Graphs\n")
    for name in ("confusion_matrix", "calibration", "selective", "per_class", "distribution"):
        md.append("![{}]({}/{}.png)\n".format(name, graphs.name, name))
    md.append("## Mistakes (most confidently wrong first, top 30)\n")
    md.append("| row | true | predicted | confidence |")
    md.append("|---|---|---|---|")
    for r, l, p, c in mistakes[:30]:
        md.append("| {} | {} | {} | {} |".format(r, l, p, round(c, 4) if c is not None else "-"))
    (results / "EVAL-REPORT{}.md".format(tag)).write_text("\n".join(md), encoding="utf-8")

    # HTML
    html = []
    html.append("<!DOCTYPE html><html><head><meta charset='utf-8'><title>Evaluation {}</title>".format(args.name or "pilot"))
    html.append("<style>body{font-family:Segoe UI,Arial;margin:32px auto;max-width:1000px;background:#0f1420;color:#e8ecf3}")
    html.append(".card{background:#171e2e;border-radius:12px;padding:18px 22px;margin-bottom:16px}")
    html.append("table{border-collapse:collapse;width:100%}th,td{border:1px solid #2a3550;padding:6px 9px;text-align:left;font-size:14px}")
    html.append("th{background:#1d2740}img{max-width:100%;border-radius:8px;border:1px solid #2a3550;margin:6px 0}")
    html.append(".muted{color:#9aa7bd}.ok{color:#69d98c}.bad{color:#ff7b7b}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}")
    html.append("@media(max-width:800px){.grid{grid-template-columns:1fr}}</style></head><body>")
    html.append("<h1>Evaluation report &middot; {}</h1>".format(args.name or "pilot"))
    html.append("<div class='card'><h2>Headline</h2><p>accuracy <b class='ok'>{:.1%}</b> &middot; macro-F1 <b>{}</b> &middot; balanced accuracy <b>{}</b> &middot; n={} </p></div>".format(
        accuracy, macro_f1, balanced, len(pairs)))
    html.append("<div class='card'><h2>Per-class metrics</h2><table><tr><th>class</th><th>support</th><th>predicted</th><th>precision</th><th>recall</th><th>F1</th></tr>")
    for c in classes:
        m = metrics[c]
        cls = "ok" if m["recall"] > 0 else "bad"
        html.append("<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td class='{}'>{}</td><td>{}</td></tr>".format(
            c, m["support"], m["predicted"], m["precision"], cls, m["recall"], m["f1"]))
    html.append("</table></div>")
    html.append("<div class='card'><h2>Calibration bands</h2><table><tr><th>band</th><th>n</th><th>mean conf</th><th>accuracy</th></tr>")
    for r in cal_rows:
        html.append("<tr><td>{:.2f}-{:.2f}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(r[0], r[1], r[2], r[3], r[4]))
    html.append("</table></div>")
    html.append("<div class='card'><h2>Graphs</h2><div class='grid'>")
    for name in ("confusion_matrix", "calibration", "selective", "per_class", "distribution"):
        html.append("<div><img src='{}/{}.png'></div>".format(graphs.name, name))
    html.append("</div></div>")
    html.append("<div class='card'><h2>Top mistakes</h2><table><tr><th>row</th><th>true</th><th>predicted</th><th>confidence</th></tr>")
    for r, l, p, c in mistakes[:30]:
        html.append("<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(r, l, p, round(c, 4) if c is not None else "-"))
    html.append("</table></div></body></html>")
    (results / "EVAL-REPORT{}.html".format(tag)).write_text("\n".join(html), encoding="utf-8")

    print("== {} ==".format(args.name or "pilot"))
    print("accuracy: {:.4f}   macro-F1: {}   balanced acc: {}   n: {}".format(accuracy, macro_f1, balanced, len(pairs)))
    print("per-class recall:")
    for c in classes:
        m = metrics[c]
        flag = "" if m["recall"] > 0 else "   <-- NEVER CORRECT"
        print("  {:24s} recall={:5.3f}  {}/{}  predicted={}{}".format(c, m["recall"], m["correct"], m["support"], m["predicted"], flag))
    print("report:", results / "EVAL-REPORT{}.html".format(tag))


if __name__ == "__main__":
    main()
