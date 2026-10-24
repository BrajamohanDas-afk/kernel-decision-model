#!/usr/bin/env bash
# Resume batch 1 after an interruption: finish seeds 2035..2059, then build the dataset.
set -u
cd /root/workloadpilot/dsv2
rm -rf runs/run-2035-rules
nohup bash -c "python3 /root/workloadpilot/dsv2/run_batch.py --runs 25 --start-seed 2035 --mode-mix 0.7 --runs-dir /root/workloadpilot/dsv2/runs --time-scale 1.0 && python3 /root/workloadpilot/dsv2/build_all.py --runs-dir /root/workloadpilot/dsv2/runs --out-dir /root/workloadpilot/dsv2/dataset" >> /root/workloadpilot/dsv2/batch1.log 2>&1 &
echo "resume-launcher pid=$!"
sleep 8
echo "--- batch1.log tail:"
tail -3 /root/workloadpilot/dsv2/batch1.log
echo "--- run_batch alive:"
ps -ef | grep -c "[r]un_batch"
