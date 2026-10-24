#!/usr/bin/env bash
# Smoke test: throttle_io via io.max fallback (kernel has no io.weight).
set -u
cd /root/workloadpilot

systemctl stop wlp-io-test2.service 2>/dev/null
systemctl reset-failed wlp-io-test2.service 2>/dev/null
rm -f out/iofile_dummy

systemd-run --unit=wlp-io-test2 --slice=wlp.slice -p IOWeight=10 bash -c "dd if=/dev/zero of=/root/workloadpilot/out/iofile_dummy bs=1M count=300 conv=fsync 2>/dev/null; sleep 30"
sleep 12
echo ACTUATOR:
python3 actuator.py --action throttle_io --target wlp-io-test2
echo IOMAX:
cat /sys/fs/cgroup/wlp.slice/wlp-io-test2.service/io.max 2>&1
systemctl stop wlp-io-test2.service 2>/dev/null
systemctl reset-failed wlp-io-test2.service 2>/dev/null
rm -f out/iofile_dummy
echo SMOKE-DONE
