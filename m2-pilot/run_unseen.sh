#!/usr/bin/env bash
# Fresh unseen-seed test set for the v3-2b audit: 2 default + 2 targeted runs, rules-only labels.
set -u
cd /root/workloadpilot/dsv2
mkdir -p runs-unseen
python3 run_batch.py --runs 2 --start-seed 4000 --mode-mix 1.0 --scenario-mode default \
  --runs-dir /root/workloadpilot/dsv2/runs-unseen > unseen-default.log 2>&1
python3 run_batch.py --runs 2 --start-seed 4002 --mode-mix 1.0 --scenario-mode targeted \
  --runs-dir /root/workloadpilot/dsv2/runs-unseen > unseen-targeted.log 2>&1
echo UNSEEN-DONE
