# WorkloadPilot — portable data-collection kit

*Thanks for helping! This collects Linux resource-management telemetry on your machine — ~2 hours, unattended.*

## What it does

Runs 24 short scripted scenarios (each ~3.5 min). Each scenario starts a small controlled experiment:
an "innocent" app plus a "stressful neighbor" (CPU / memory / disk), while a recorder logs cgroup v2
telemetry every 2 seconds and a simple rules engine logs what resource actions it would take.
Nothing leaves your machine — you send back one archive at the end.

## Requirements (the check script verifies all of this in 10 seconds)

Linux with: cgroup v2 · PSI (`/proc/pressure`) · systemd · python3 ≥ 3.10 · sudo · ≥3 GB RAM · ~1.5 GB disk.
On a VM, 6 GB+ RAM and 4 vCPUs are recommended — the kit auto-scales its memory targets on smaller machines
(scale is printed at the start of every run), so 3-6 GB boxes still work, just more slowly.
**Please don't run this on a production server** — it generates short CPU/memory/disk stress bursts.
A staging box, dev VM, or any machine that tolerates that for ~2 h is perfect.

## How to run — 3 commands

    tar -xzf wlp-lab-bundle-v2.tar.gz
    cd wlp-lab-bundle
    sudo bash check_machine.sh        # 10-second preflight — must say "ALL GOOD"
    sudo bash collect.sh              # ~1.6-2 h; prints progress per run

Want more or fewer runs? `RUNS=40 sudo bash collect.sh` (each run ≈ 3.5 min). On a weak machine (small VM,
slow disk)? `RUNS=12` works — a shorter batch beats a machine that is struggling.

If a single run fails, it is recorded as `failed:*` in `runs/index.jsonl`, the batch waits 60 s to let the
machine settle, and then continues with the next one — partial results are still useful, so let it finish.

**Keep using the machine normally while it collects.** Ordinary background activity improves the data
(it adds realistic noise contexts). Don't idle the machine for our sake — but don't run deliberate
heavy benchmarks during the collection either. Every workload it starts is quota-capped (a few CPU
cores, ~1 GB RAM, modest disk), so it stays polite even mid-run.

## What you get back

`wlp-results-YYYYMMDD-HHMM.tar.gz` in the bundle folder — timestamped, so re-running never overwrites an
earlier archive. Send back the **newest** one.

## Safety / privacy

- Pure-stdlib Python; **no network calls anywhere**
- Everything is generated locally (its own small stress programs); no customer or personal data involved
- Uses transient systemd units named `wlp-*` that clean up after themselves
- Stop anytime with Ctrl-C; re-running continues with fresh runs

## Layout

    check_machine.sh     preflight
    collect.sh           the runner
    lab/                 the scripts (readable Python, feel free to inspect)
    sample_run/          an example of what one finished run folder looks like
