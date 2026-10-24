#!/usr/bin/env bash
# WorkloadPilot M1 actuator smoke test (agent T2). Scratch units only:
# wlp-t2-test (plain) and wlp-t2-mem (quota/high/max/tasks). Real units untouched.
set -u
cd /root/workloadpilot
D1=/sys/fs/cgroup/wlp.slice/wlp-t2-test.service
D2=/sys/fs/cgroup/wlp.slice/wlp-t2-mem.service

cleanup() {
  systemctl stop wlp-t2-test.service 2>/dev/null || true
  systemctl reset-failed wlp-t2-test.service 2>/dev/null || true
  systemctl stop wlp-t2-mem.service 2>/dev/null || true
  systemctl reset-failed wlp-t2-mem.service 2>/dev/null || true
}
cleanup

echo "== compile check"
python3 -m py_compile actuator.py && echo "py_compile OK"

echo "== start scratch units"
systemd-run --unit=wlp-t2-test --slice=wlp.slice -p CPUQuota=20% sleep 300
systemd-run --unit=wlp-t2-mem --slice=wlp.slice -p CPUQuota=90% -p MemoryHigh=120M -p MemoryMax=150M -p TasksMax=20 sleep 300
sleep 1
echo "test active: $(systemctl is-active wlp-t2-test.service)  mem active: $(systemctl is-active wlp-t2-mem.service)"

echo "== initial t2-test"
echo "cpu.max:    $(cat $D1/cpu.max)"
echo "cpu.weight: $(cat $D1/cpu.weight)"
echo "memory.high: $(cat $D1/memory.high)"
echo "pids.max:   $(cat $D1/pids.max)"
echo "pids.current: $(cat $D1/pids.current)"
echo "io.weight:  $(cat $D1/io.weight 2>&1)"

echo "== initial t2-mem"
echo "cpu.max:    $(cat $D2/cpu.max)"
echo "cpu.weight: $(cat $D2/cpu.weight)"
echo "memory.high: $(cat $D2/memory.high)"
echo "memory.max: $(cat $D2/memory.max)"
echo "pids.max:   $(cat $D2/pids.max)"

echo "== 1) increase_cpu wlp-t2-test"
python3 actuator.py --action increase_cpu --target wlp-t2-test
echo "cpu.max now:    $(cat $D1/cpu.max)"
echo "cpu.weight now: $(cat $D1/cpu.weight)"

echo "== 2) decrease_cpu wlp-t2-test"
python3 actuator.py --action decrease_cpu --target wlp-t2-test
echo "cpu.max now:    $(cat $D1/cpu.max)"
echo "cpu.weight now: $(cat $D1/cpu.weight)"

echo "== 3a) kill_process, no --approve"
python3 actuator.py --action kill_process --target wlp-t2-test
echo "== 3b) kill_process, --approve"
python3 actuator.py --action kill_process --target wlp-t2-test --approve
echo "== 3c) restart_service, --approve"
python3 actuator.py --action restart_service --target wlp-t2-test --approve
echo "== 3d) isolate_workload, no --approve / --approve"
python3 actuator.py --action isolate_workload --target wlp-t2-test
python3 actuator.py --action isolate_workload --target wlp-t2-test --approve

echo "== 4) increase_memory wlp-t2-test (no MemoryHigh set)"
python3 actuator.py --action increase_memory --target wlp-t2-test
echo "memory.high now: $(cat $D1/memory.high)"
echo "== 4b) decrease_memory wlp-t2-test (no high limit set)"
python3 actuator.py --action decrease_memory --target wlp-t2-test

echo "== 5) stdin json mode (increase_cpu)"
printf '%s' '{"action": "increase_cpu", "target": "wlp-t2-test"}' | python3 actuator.py
echo "cpu.max now:    $(cat $D1/cpu.max)"
echo "cpu.weight now: $(cat $D1/cpu.weight)"

echo "== 6) memory paths on wlp-t2-mem (high=120M, max=150M)"
python3 actuator.py --action increase_memory --target wlp-t2-mem
echo "memory.high now: $(cat $D2/memory.high)"
python3 actuator.py --action decrease_memory --target wlp-t2-mem
echo "memory.high now: $(cat $D2/memory.high)"

echo "== 7) cpu cap-at-period path on wlp-t2-mem (quota 90% -> 100%)"
python3 actuator.py --action increase_cpu --target wlp-t2-mem
echo "cpu.max now:    $(cat $D2/cpu.max)"
echo "cpu.weight now: $(cat $D2/cpu.weight)"

echo "== 8) cpu quota floor clamp (manual 6000, decrease -> floor 5000)"
printf '%s' '6000 100000' > $D2/cpu.max
python3 actuator.py --action decrease_cpu --target wlp-t2-mem
echo "cpu.max now:    $(cat $D2/cpu.max)"

echo "== 9) restrict_process_count on wlp-t2-mem (pids.max=20 -> floor 16)"
python3 actuator.py --action restrict_process_count --target wlp-t2-mem
echo "pids.max now:   $(cat $D2/pids.max)"
echo "== 9b) restrict_process_count on wlp-t2-test (pids.max=max)"
python3 actuator.py --action restrict_process_count --target wlp-t2-test
echo "pids.max now:   $(cat $D1/pids.max)"

echo "== 10) throttle_io (io.weight expected missing in this lab)"
python3 actuator.py --action throttle_io --target wlp-t2-test
python3 actuator.py --action throttle_io --target wlp-t2-mem

echo "== 11) do_nothing / alert_operator"
python3 actuator.py --action do_nothing --target wlp-t2-test
python3 actuator.py --action alert_operator --target both

echo "== 12) bad inputs, no crash"
python3 actuator.py --action increase_cpu --target wlp-neighbor
python3 actuator.py --action increase_cpu --target wlp-critical
python3 actuator.py --action increase_cpu --target ../../
python3 actuator.py --action fly_to_moon --target wlp-t2-test
python3 actuator.py --action increase_cpu
printf '%s' '{"action": "decrease_cpu", "target": "wlp-t2-test", "approve": true}' | python3 actuator.py
printf '%s' 'not json' | python3 actuator.py

echo "== 13) protect_service with no real units running (read-only refusal)"
python3 actuator.py --action protect_service --target both

echo "== cleanup"
cleanup
systemctl is-active wlp-t2-test.service || echo "(t2-test stopped)"
systemctl is-active wlp-t2-mem.service || echo "(t2-mem stopped)"
ls /sys/fs/cgroup/wlp.slice 2>&1 || true
echo "SMOKE DONE"
