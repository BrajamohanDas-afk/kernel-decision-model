#!/usr/bin/env bash
set -u
cd /root/workloadpilot/dsv2
for d in runs-unseen/run-*; do
  python3 featurize.py --run-dir "$d" > /dev/null || echo "FEATURIZE FAIL $d"
  python3 labeler.py --run-dir "$d" > /dev/null || echo "LABEL FAIL $d"
done
python3 split_by_run.py --runs-dir runs-unseen --out-dir out-unseen --holdout-every 1000
wc -l out-unseen/train.jsonl
