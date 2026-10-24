@echo off
title WorkloadPilot - dataset v2 progress
echo === WorkloadPilot dataset-v2 progress ===
echo.
echo Completed runs (target = 60):
wsl -d wlp-lab -- bash -c "wc -l /root/workloadpilot/dsv2/runs/index.jsonl"
echo.
echo Currently running:
wsl -d wlp-lab -- bash -c "tail -1 /root/workloadpilot/dsv2/batch1.log"
echo.
echo Last 3 finished runs:
wsl -d wlp-lab -- bash -c "tail -3 /root/workloadpilot/dsv2/runs/index.jsonl"
echo.
echo (Refreshing copies in results\dataset-v2 ...)
wsl -d wlp-lab -- bash /root/workloadpilot/export_to_folder.sh >nul 2>&1
echo Done. Press any key to close.
pause >nul
