#!/usr/bin/env bash
# WorkloadPilot data-collection kit — one command. Usage: sudo bash collect.sh [extra args]
set -e
cd "$(dirname "$0")"
if [ "$(id -u)" != "0" ]; then
  echo "please run with sudo:  sudo bash collect.sh"
  exit 1
fi
ulimit -c 0   # never write core dumps: a wedged guest must not fill its disk with them
RUNS="${RUNS:-24}"
BASE="$(pwd)"
MEM_MB="$(awk '/MemTotal/{printf "%d", $2/1024}' /proc/meminfo)"
if [ -n "${WLP_MEM_SCALE:-}" ]; then
  SCALE="$WLP_MEM_SCALE"
else
  SCALE="$(awk -v ram="$MEM_MB" 'BEGIN { s = ram / 8000.0; if (s < 0.40) s = 0.40; if (s > 1.00) s = 1.00; printf "%.2f", s }')"
fi
echo "== WorkloadPilot data collection =="
echo "runs: $RUNS (each ~3.5 min; change with:  RUNS=40 sudo bash collect.sh)"
echo "RAM: ${MEM_MB} MB -> memory scale ${SCALE} (targets unchanged at 8 GB+; override with WLP_MEM_SCALE)"
mkdir -p "$BASE/runs"
python3 "$BASE/lab/dsv2/run_batch.py" --runs "$RUNS" --start-seed 2000 --mode-mix 0.7 --mem-scale "$SCALE" \
  --runs-dir "$BASE/runs" "$@"
echo
echo "== collection finished — packing results =="
ARCHIVE="$BASE/wlp-results-$(date +%Y%m%d-%H%M).tar.gz"
tar -czf "$ARCHIVE" runs
ls -la "$ARCHIVE"
echo
echo "DONE. Please send back the newest file:  $(basename "$ARCHIVE")"
