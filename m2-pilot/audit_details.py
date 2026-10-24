"""Detailed metrics for the audit report: confusion, calibration, confident errors."""
import json
from pathlib import Path

A = Path(r"C:\MyFile\Study material\kernel decision model\m2-pilot\results\audit")
DATA = Path(r"C:\MyFile\Study material\kernel decision model\results\dsv3")
ACTIONS = ["do_nothing", "increase_cpu", "decrease_cpu", "increase_memory", "decrease_memory",
           "throttle_io", "restrict_process_count", "protect_service", "isolate_workload",
           "restart_service", "kill_process", "alert_operator"]


def load_rows(name):
    return [json.loads(line) for line in (A / (name + "_rows.jsonl")).read_text(encoding="utf-8").splitlines()]


def labels(path):
    return {r["id"]: r["labels"]["action"] for r in
            (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())}


def detail(rows, label_map):
    confuse = {}
    bands = {f"{i/10:.1f}-{(i+1)/10:.1f}": {"n": 0, "conf": 0.0, "ok": 0} for i in range(10)}
    pred_count = {a: 0 for a in ACTIONS}
    wrong_conf = []
    for r in rows:
        true = label_map[r["row"]]
        pred = r["answer"]["choice"]
        conf = r["answer"]["probabilities"][pred]
        pred_count[pred] += 1
        if true != pred:
            confuse[(true, pred)] = confuse.get((true, pred), 0) + 1
            if conf >= 0.9:
                wrong_conf.append({"row": r["row"], "true": true, "pred": pred, "conf": conf})
        band = min(9, int(conf * 10))
        key = f"{band/10:.1f}-{(band+1)/10:.1f}"
        bands[key]["n"] += 1
        bands[key]["conf"] += conf
        bands[key]["ok"] += true == pred
    top_conf = sorted(confuse.items(), key=lambda kv: -kv[1])[:12]
    return {
        "n": len(rows),
        "confusion_top": [{"true": t, "pred": p, "n": n} for (t, p), n in top_conf],
        "calibration": {k: {"n": v["n"], "mean_conf": v["conf"] / v["n"] if v["n"] else 0,
                            "acc": v["ok"] / v["n"] if v["n"] else 0} for k, v in bands.items() if v["n"]},
        "predicted": pred_count,
        "confident_wrong": len(wrong_conf),
        "confident_wrong_examples": wrong_conf[:10],
    }


heldout_labels = labels(DATA / "dsv3_heldout.jsonl")
train_labels = labels(DATA / "dsv3_train.jsonl")
unseen_labels = {r["id"]: r["labels"]["action"] for r in
                 (json.loads(line) for line in (A / "unseen_rows.jsonl").read_text(encoding="utf-8").splitlines())}
friend_labels = {r["id"]: r["labels"]["action"] for r in
                 (json.loads(line) for line in Path(r"C:\MyFile\Study material\kernel decision model\m2-pilot\results\external_friend_rows.jsonl").read_text(encoding="utf-8").splitlines())}

out = {
    "heldout_tuned": detail(load_rows("heldout_tuned"), heldout_labels),
    "heldout_base": detail(load_rows("heldout_base"), heldout_labels),
    "unseen_tuned": detail(load_rows("unseen_tuned"), unseen_labels),
    "friend_tuned": detail(load_rows("friend_tuned"), friend_labels),
    "train_full_tuned": detail(load_rows("train_full_tuned"), train_labels),
}
summary = json.loads((A / "audit_summary.json").read_text(encoding="utf-8"))
for name in ("heldout", "train_sample", "friend", "unseen"):
    if name in summary:
        out[name + "_summary"] = summary[name]
out["overfit_gap"] = summary.get("overfit_gap_train_minus_heldout")
(A / "detailed_metrics.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
print(json.dumps({
    "heldout_confident_wrong": out["heldout_tuned"]["confident_wrong"],
    "unseen_confident_wrong": out["unseen_tuned"]["confident_wrong"],
    "friend_confident_wrong": out["friend_tuned"]["confident_wrong"],
    "train_full_acc": out["train_full_tuned"]["n"],
}, indent=2))
print("top heldout confusions:", out["heldout_tuned"]["confusion_top"][:6])
