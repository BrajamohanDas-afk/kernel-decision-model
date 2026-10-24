#!/usr/bin/env bash
# Export the canonical lab files into the study folder (structured copy).
set -u
DEST="/mnt/c/MyFile/Study material/kernel decision model"
mkdir -p "$DEST/lab-scripts" "$DEST/tools" "$DEST/results/m0" "$DEST/results/m1-v1" "$DEST/results/m1-v2"

cp /root/workloadpilot/actuator.py /root/workloadpilot/analyze.py /root/workloadpilot/build_dataset.py \
   /root/workloadpilot/critical_app.py /root/workloadpilot/m1_run.sh /root/workloadpilot/neighbor_app.py \
   /root/workloadpilot/rules.py /root/workloadpilot/sampler.py /root/workloadpilot/scenario.sh \
   /root/workloadpilot/smoke_io.sh /root/workloadpilot/t2-smoke.sh /root/workloadpilot/teacher_loop.py \
   "$DEST/lab-scripts/"

cp /root/workloadpilot/wlp_inspect.py /root/workloadpilot/inspect_decisions.py /root/workloadpilot/psi_io_check.py "$DEST/tools/"

cp /root/workloadpilot/out/telemetry.jsonl /root/workloadpilot/out/phases.log /root/workloadpilot/out/critical_latency.log \
   /root/workloadpilot/out/decisions.jsonl /root/workloadpilot/out/decision_train.jsonl \
   /root/workloadpilot/out/decision_heldout.jsonl /root/workloadpilot/out/outcomes.jsonl "$DEST/results/m1-v2/"

echo "=== lab-scripts ==="
ls "$DEST/lab-scripts/"
echo "=== tools ==="
ls "$DEST/tools/"
echo "=== results/m1-v2 ==="
ls "$DEST/results/m1-v2/"
echo EXPORT-DONE
