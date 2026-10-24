# M3 Soak v1 — summary

Run: /root/workloadpilot/m3/soak/rehearsal
Scenario seed 7317 · victim latency · model workloadpilot/v2-2b · scale 0.1 · runner ok in 351.4 s

## Decisions, tokens, gate

| metric | value |
|---|---|
| decisions | 175 over 348.2 s (30.2 /min) |
| model errors / controller errors | 0 / 0 |
| tokens | 115,650 total, median 656 per decision (missing on 0) |
| cost estimate | $0.00081 (at $0.007/M in) |
| gate | applied 12, pass-no-write 100, rejected-cooldown 63 |
| rejection reasons | cooldown x63 |

Actions chosen overall: do_nothing 99, increase_cpu 46, increase_memory 20, restrict_process_count 8, throttle_io 1, alert_operator 1

## Per-regime action mix

| regime | windows | duration | decisions | /min | applied | pass | rejected | errors | action mix |
|---|---|---|---|---|---|---|---|---|---|
| idle | 1 | 18.0s | 9 | 30.0 | 0 | 9 | 0 | 0 | do_nothing 9 |
| cpu-moderate | 1 | 36.0s | 18 | 30.0 | 2 | 0 | 16 | 0 | increase_cpu 17, restrict_process_count 1 |
| cpu-spike | 1 | 18.0s | 9 | 30.0 | 1 | 0 | 8 | 0 | increase_cpu 9 |
| cut-to-idle | 1 | 24.0s | 12 | 30.0 | 0 | 12 | 0 | 0 | do_nothing 12 |
| mem-hold | 1 | 30.0s | 15 | 30.0 | 0 | 15 | 0 | 0 | do_nothing 15 |
| mem-release | 1 | 18.0s | 9 | 30.0 | 0 | 9 | 0 | 0 | do_nothing 9 |
| io | 1 | 24.0s | 12 | 30.0 | 0 | 12 | 0 | 0 | do_nothing 12 |
| io-burst | 1 | 12.0s | 6 | 30.0 | 0 | 6 | 0 | 0 | do_nothing 6 |
| fork | 1 | 18.0s | 9 | 30.0 | 1 | 6 | 2 | 0 | do_nothing 6, restrict_process_count 3 |
| mixed | 1 | 30.0s | 15 | 30.0 | 1 | 0 | 14 | 0 | increase_memory 14, restrict_process_count 1 |
| saturation | 3 | 24.0s | 12 | 30.0 | 3 | 2 | 7 | 0 | increase_memory 6, increase_cpu 3, do_nothing 2, throttle_io 1 |
| decay | 2 | 24.0s | 12 | 30.0 | 2 | 0 | 10 | 0 | increase_cpu 11, restrict_process_count 1 |
| decay-off | 1 | 12.0s | 6 | 30.0 | 0 | 5 | 1 | 0 | do_nothing 5, increase_cpu 1 |
| tail | 1 | 36.0s | 18 | 30.0 | 0 | 18 | 0 | 0 | do_nothing 18 |
| rise-fall | 2 | 24.0s | 12 | 30.0 | 2 | 5 | 5 | 0 | do_nothing 5, increase_cpu 5, restrict_process_count 2 |
| after-run | 1 | 0.0s | 1 | - | 0 | 1 | 0 | 0 | alert_operator 1 |

## Applied writes (before -> after)

`GIVE-BACK` = applied during an idle/cut-to-idle/mem-release/decay/tail regime; `LOWER` = the action lowers an allocation.

| ts | regime | action | target | write | flags |
|---|---|---|---|---|---|
| 08:49:21 | cpu-moderate | restrict_process_count | wlp-neighbor | wlp-neighbor/pids.max 54->27 | LOWER |
| 08:49:23 | cpu-moderate | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 50000->75000; wlp-neighbor/cpu.weight 100->200 | RAISE |
| 08:50:09 | cpu-spike | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 75000->100000; wlp-neighbor/cpu.weight 200->400 | RAISE |
| 08:52:03 | fork | restrict_process_count | wlp-neighbor | wlp-neighbor/pids.max 27->31 | LOWER |
| 08:52:23 | mixed | increase_memory | wlp-neighbor | wlp-neighbor/memory.high 750780416->803209216 | RAISE |
| 08:52:51 | saturation | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 100000->100000; wlp-neighbor/cpu.weight 400->800 | RAISE |
| 08:53:09 | saturation | increase_memory | wlp-neighbor | wlp-neighbor/memory.high 803209216->829423616 | RAISE |
| 08:53:11 | saturation | throttle_io | wlp-neighbor | wlp-neighbor/io.max None->1048576 | LOWER |
| 08:53:15 | decay | restrict_process_count | wlp-neighbor | wlp-neighbor/pids.max 31->16 | GIVE-BACK LOWER |
| 08:53:37 | decay | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 100000->100000; wlp-neighbor/cpu.weight 800->1600 | GIVE-BACK RAISE |
| 08:54:29 | rise-fall | restrict_process_count | wlp-neighbor | wlp-neighbor/pids.max 16->16 | LOWER |
| 08:54:35 | rise-fall | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 100000->100000; wlp-neighbor/cpu.weight 1600->3200 | RAISE |

Give-back moments (writes during idle / cut-to-idle / mem-release / decay / tail regimes): 2 of 12 applied writes.
* 08:53:15 [decay] restrict_process_count: wlp-neighbor/pids.max 31->16  <- LOWERING
* 08:53:37 [decay] increase_cpu: wlp-neighbor/cpu.max 100000->100000; wlp-neighbor/cpu.weight 800->1600
* The controller DID lower allocations during give-back regimes (1 times).

## Outcome deltas (3 telemetry samples after vs 3 before; directional only)

| ts | regime | action | victim p95 ms | n cpu psi | n mem MB | n mem high MB | n pids | n throttle us/s | sys io psi | sys load1 |
|---|---|---|---|---|---|---|---|---|---|---|
| 08:49:21 | cpu-moderate | restrict_process_count | 0.8->0.7 | 0.0->17.1 | 9->15 | 716->716 | 2->4 | 167,332->1,417,876 | 0.2->0.1 | 1.62->1.50 |
| 08:49:23 | cpu-moderate | increase_cpu | 0.7->0.7 | 3.3->26.2 | 11->15 | 716->716 | 3->4 | 692,595->1,310,500 | 0.2->0.1 | 1.58->1.44 |
| 08:50:09 | cpu-spike | increase_cpu | 0.6->0.6 | 77.6->83.3 | 43->34 | 716->716 | 11->9 | 8,302,098->7,310,033 | 0.0->0.0 | 1.17->1.95 |
| 08:52:03 | fork | restrict_process_count | 1.0->0.7 | 0.0->0.0 | 11->14 | 716->716 | 8->28 | 0->0 | 0.2->0.1 | 0.52->0.47 |
| 08:52:23 | mixed | increase_memory | 0.7->0.6 | 2.2->17.6 | 248->724 | 716->754 | 18->7 | 810,587->1,267,735 | 0.0->0.7 | 0.45->0.71 |
| 08:52:51 | saturation | increase_cpu | 0.6->0.6 | 44.5->54.3 | 556->36 | 766->766 | 8->10 | 1,157,804->8,900,302 | 0.1->0.3 | 1.27->1.23 |
| 08:53:09 | saturation | increase_memory | 0.7->0.6 | 55.3->41.4 | 755->200 | 766->785 | 7->24 | 1,063,228->24,014 | 0.1->0.1 | 1.26->1.25 |
| 08:53:11 | saturation | throttle_io | 0.7->0.7 | 52.1->36.9 | 570->18 | 772->791 | 13->24 | 728,093->1,197,195 | 0.1->0.0 | 1.28->1.23 |
| 08:53:15 | decay | restrict_process_count | 0.6->0.6 | 41.4->39.0 | 200->24 | 785->791 | 24->13 | 24,014->3,878,111 | 0.1->0.0 | 1.25->1.15 |
| 08:53:37 | decay | increase_cpu | 0.7->0.8 | 54.4->47.0 | 16->12 | 791->791 | 4->3 | 989,803->379,510 | 0.0->0.0 | 1.01->0.93 |
| 08:54:29 | rise-fall | restrict_process_count | 0.6->0.6 | 2.9->27.2 | 13->31 | 791->791 | 4->8 | 1,330,226->5,040,159 | 0.0->0.0 | 0.62->0.84 |
| 08:54:35 | rise-fall | increase_cpu | 0.6->0.8 | 27.2->51.3 | 31->31 | 791->791 | 8->8 | 5,040,159->4,979,718 | 0.0->0.0 | 0.84->1.14 |

## Anomalies / observations

* action increase_cpu repeated 26 times in a row from 2026-10-17T08:49:23.147Z
* action do_nothing repeated 54 times in a row from 2026-10-17T08:50:15.170Z
* action increase_memory repeated 14 times in a row from 2026-10-17T08:52:23.247Z
* action increase_cpu repeated 12 times in a row from 2026-10-17T08:53:17.275Z
* action do_nothing repeated 24 times in a row from 2026-10-17T08:53:41.286Z
* applied actions without an outcome row: 3

## Caveats

* Outcome deltas use 3 telemetry samples per side: directional evidence, not causal proof.
* Cooldown 45 s suppresses repeated writes, so chosen-action counts exceed applied counts by design.
* Quiet regimes are cpu_burn procs=0 phases (the stressor sleeps); mixed-phase magnitudes are runner-fixed (cpu 2, mem to memory.high, io 4 MB/s).

