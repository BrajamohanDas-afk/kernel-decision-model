#!/usr/bin/env bash
# WorkloadPilot data-collection kit — 10-second preflight.
set -u
PASS=0
FAIL=0
chk() { if [ "$1" = "1" ]; then echo "  OK   $2"; PASS=$((PASS + 1)); else echo "  FAIL $2"; FAIL=$((FAIL + 1)); fi; }

echo "== checking this machine =="
chk "$([ -f /sys/fs/cgroup/cgroup.controllers ] && echo 1 || echo 0)" "cgroup v2 mounted"
chk "$([ -f /proc/pressure/cpu ] && echo 1 || echo 0)" "PSI available (/proc/pressure)"
chk "$(command -v systemctl >/dev/null 2>&1 && echo 1 || echo 0)" "systemd (systemctl)"
chk "$(command -v systemd-run >/dev/null 2>&1 && echo 1 || echo 0)" "systemd-run"

PY="$(command -v python3 || true)"
if [ -n "$PY" ]; then
  PYOK="$($PY -c 'import sys; print(1 if sys.version_info >= (3, 10) else 0)')"
else
  PYOK=0
fi
chk "$PYOK" "python3 >= 3.10"

chk "$([ "$(id -u)" = "0" ] && echo 1 || echo 0)" "running as root (use sudo)"

CPUS="$(nproc 2>/dev/null || echo unknown)"
echo "  info CPU count: $CPUS (4 vCPUs recommended if this is a VM)"

MEM_MB="$(awk '/MemTotal/{printf "%d", $2/1024}' /proc/meminfo)"
chk "$([ "$MEM_MB" -ge 3000 ] && echo 1 || echo 0)" "at least 3 GB RAM (found ${MEM_MB} MB; 6 GB+ recommended — memory targets auto-scale below that)"

FREE_MB="$(df -Pm . | awk 'NR==2{print $4}')"
chk "$([ "$FREE_MB" -ge 1500 ] && echo 1 || echo 0)" "at least 1.5 GB free disk (found ${FREE_MB} MB)"

echo
echo "passed: $PASS    failed: $FAIL"
if [ "$FAIL" = "0" ]; then
  echo "ALL GOOD — run:  sudo bash collect.sh"
else
  echo "Some checks failed — this machine can't run the kit."
fi
