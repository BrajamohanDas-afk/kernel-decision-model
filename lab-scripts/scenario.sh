#!/usr/bin/env bash
# WorkloadPilot Milestone 0 scenario driver: baseline (60s) -> cpu_load (90s)
# -> mem_load (90s) -> io_load (90s) -> recovery (60s), plus a 10s warm-up.
set -u

BASE=/root/workloadpilot
OUT=$BASE/out
PHASES=$OUT/phases.log
CRITICAL_UNIT=wlp-critical
NEIGHBOR_UNIT=wlp-neighbor
WARMUP_SECONDS=10
BASELINE_SECONDS=60
LOAD_SECONDS=90
RECOVERY_SECONDS=60

mkdir -p "$OUT"

stop_units() {
  systemctl stop "${CRITICAL_UNIT}.service" "${NEIGHBOR_UNIT}.service" 2>/dev/null || true
  systemctl reset-failed "${CRITICAL_UNIT}.service" "${NEIGHBOR_UNIT}.service" 2>/dev/null || true
}

mark_phase() {
  local phase="$1"
  local ts=""
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf '%s %s\n' "$ts" "$phase" >> "$PHASES"
  echo "phase ${phase} ${ts}"
}

wait_seconds() {
  echo "waiting $1s"
  sleep "$1"
}

start_critical() {
  if ! systemd-run --unit="$CRITICAL_UNIT" --slice=wlp.slice -p CPUQuota=50% -p MemoryMax=150M -p MemoryHigh=120M --property=WorkingDirectory="$BASE" python3 "$BASE/critical_app.py"; then
    echo "ERROR: could not start ${CRITICAL_UNIT}" >&2
    exit 1
  fi
  echo "started ${CRITICAL_UNIT}"
}

start_neighbor() {
  local chain="python3 neighbor_app.py --phase cpu --duration $LOAD_SECONDS; python3 neighbor_app.py --phase mem --duration $LOAD_SECONDS; python3 neighbor_app.py --phase io --duration $LOAD_SECONDS"
  if ! systemd-run --unit="$NEIGHBOR_UNIT" --slice=wlp.slice -p CPUQuota=50% -p MemoryMax=250M -p MemoryHigh=200M -p IOWeight=10 --property=WorkingDirectory="$BASE" bash -c "$chain"; then
    echo "ERROR: could not start ${NEIGHBOR_UNIT}" >&2
    exit 1
  fi
  echo "started ${NEIGHBOR_UNIT}"
}

# Re-runnable: clear leftovers from an interrupted previous run.
stop_units
trap stop_units EXIT

echo "scenario start $(date -u +%Y-%m-%dT%H:%M:%SZ)"
start_critical
wait_seconds "$WARMUP_SECONDS"

mark_phase baseline
wait_seconds "$BASELINE_SECONDS"

mark_phase cpu_load
start_neighbor
wait_seconds "$LOAD_SECONDS"

mark_phase mem_load
wait_seconds "$LOAD_SECONDS"

mark_phase io_load
wait_seconds "$LOAD_SECONDS"

mark_phase recovery
systemctl stop "${NEIGHBOR_UNIT}.service" 2>/dev/null || true
echo "stopped ${NEIGHBOR_UNIT}"
wait_seconds "$RECOVERY_SECONDS"

systemctl stop "${CRITICAL_UNIT}.service" 2>/dev/null || true
echo "stopped ${CRITICAL_UNIT}"
echo "SCENARIO DONE"
