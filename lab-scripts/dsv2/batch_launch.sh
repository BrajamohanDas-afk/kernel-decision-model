#!/usr/bin/env bash
# Launch batch 1 (60 runs, ~70% rules / 30% exploration) and build the dataset when done.
set -u
cd /root/workloadpilot/dsv2
mkdir -p runs
nohup bash -c "python3 /root/workloadpilot/dsv2/run_batch.py --runs 60 --start-seed 2000 --mode-mix 0.7 --runs-dir /root/workloadpilot/dsv2/runs --time-scale 1.0 && python3 /root/workloadpilot/dsv2/build_all.py --runs-dir /root/workloadpilot/dsv2/runs --out-dir /root/workloadpilot/dsv2/dataset" > /root/workloadpilot/dsv2/batch1.log 2>&1 &
echo "batch-launcher pid=$!"
sleep 8
echo "--- batch1.log so far:"
tail -5 /root/workloadpilot/dsv2/batch1.log
echo "--- run_batch alive:"
ps -ef | grep -c "[r]un_batch.py"
