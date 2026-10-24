#!/usr/bin/env bash
# WorkloadPilot M1 run v2: sampler + teacher loop live during the scenario, then dataset build.
set -u
cd /root/workloadpilot

rm -f out/telemetry.jsonl out/phases.log out/critical_latency.log out/decisions.jsonl \
      out/decision_train.jsonl out/decision_heldout.jsonl out/outcomes.jsonl

nohup python3 /root/workloadpilot/sampler.py --out /root/workloadpilot/out/telemetry.jsonl --interval 2 >/tmp/sampler.log 2>&1 &
nohup python3 /root/workloadpilot/teacher_loop.py --cooldown 60 >/tmp/teacher.log 2>&1 &
sleep 3

bash /root/workloadpilot/scenario.sh
echo SCENARIO-END
sleep 3
pkill -x python3
sleep 1

echo TEACHER-TAIL:
tail -3 /tmp/teacher.log
echo COUNTS:
wc -l out/telemetry.jsonl out/decisions.jsonl out/critical_latency.log
echo BUILD:
python3 /root/workloadpilot/build_dataset.py --dir /root/workloadpilot/out
