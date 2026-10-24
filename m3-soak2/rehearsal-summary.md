# M3 Soak v1 — summary

Run: /root/workloadpilot/m3/soak2/rehearsal
Scenario seed 7317 · victim latency · model workloadpilot/v3-2b · scale 0.1 · runner ok in 351.5 s

## Decisions, tokens, gate

| metric | value |
|---|---|
| decisions | 175 over 342.5 s (30.7 /min) |
| model errors / controller errors | 0 / 0 |
| tokens | 115,649 total, median 657 per decision (missing on 0) |
| cost estimate | $0.00081 (at $0.007/M in) |
| gate | applied 11, pass-no-write 118, rejected-cooldown 46 |
| rejection reasons | cooldown x46 |

Actions chosen overall: do_nothing 117, increase_cpu 33, increase_memory 19, restrict_process_count 3, decrease_cpu 2, alert_operator 1

## Per-regime action mix

| regime | windows | duration | decisions | /min | applied | pass | rejected | errors | action mix |
|---|---|---|---|---|---|---|---|---|---|
| idle | 1 | 18.1s | 9 | 29.8 | 0 | 9 | 0 | 0 | do_nothing 9 |
| cpu-moderate | 1 | 35.5s | 18 | 30.4 | 0 | 18 | 0 | 0 | do_nothing 18 |
| cpu-spike | 1 | 17.3s | 9 | 31.2 | 2 | 1 | 6 | 0 | increase_cpu 7, do_nothing 1, restrict_process_count 1 |
| cut-to-idle | 1 | 23.4s | 12 | 30.8 | 0 | 12 | 0 | 0 | do_nothing 12 |
| mem-hold | 1 | 30.0s | 15 | 30.0 | 2 | 12 | 1 | 0 | do_nothing 12, increase_memory 2, decrease_cpu 1 |
| mem-release | 1 | 17.4s | 9 | 31.0 | 0 | 9 | 0 | 0 | do_nothing 9 |
| io | 1 | 23.4s | 12 | 30.8 | 0 | 12 | 0 | 0 | do_nothing 12 |
| io-burst | 1 | 12.0s | 6 | 30.0 | 0 | 6 | 0 | 0 | do_nothing 6 |
| fork | 1 | 17.4s | 9 | 31.0 | 0 | 9 | 0 | 0 | do_nothing 9 |
| mixed | 1 | 30.0s | 15 | 30.0 | 1 | 2 | 12 | 0 | increase_memory 13, do_nothing 2 |
| saturation | 3 | 23.2s | 12 | 31.0 | 2 | 1 | 9 | 0 | increase_cpu 6, increase_memory 4, do_nothing 1, restrict_process_count 1 |
| decay | 2 | 23.5s | 12 | 30.6 | 1 | 0 | 11 | 0 | increase_cpu 12 |
| decay-off | 1 | 12.0s | 6 | 30.0 | 0 | 5 | 1 | 0 | do_nothing 5, increase_cpu 1 |
| tail | 1 | 35.5s | 18 | 30.4 | 1 | 17 | 0 | 0 | do_nothing 17, decrease_cpu 1 |
| rise-fall | 2 | 23.4s | 12 | 30.8 | 2 | 4 | 6 | 0 | increase_cpu 7, do_nothing 4, restrict_process_count 1 |
| after-run | 1 | 0.0s | 1 | - | 0 | 1 | 0 | 0 | alert_operator 1 |

## Applied writes (before -> after)

`GIVE-BACK` = applied during an idle/cut-to-idle/mem-release/decay/tail regime; `LOWER` = the action lowers an allocation.

| ts | regime | action | target | write | flags |
|---|---|---|---|---|---|
| 15:01:02 | cpu-spike | restrict_process_count | wlp-neighbor | wlp-neighbor/pids.max 54->27 | LOWER |
| 15:01:04 | cpu-spike | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 50000->75000; wlp-neighbor/cpu.weight 100->200 | RAISE |
| 15:01:40 | mem-hold | increase_memory | wlp-neighbor | wlp-neighbor/memory.high 750780416->803209216 | RAISE |
| 15:01:59 | mem-hold | decrease_cpu | wlp-neighbor | wlp-neighbor/cpu.max 75000->45000; wlp-neighbor/cpu.weight 200->100 | LOWER |
| 15:03:25 | mixed | increase_memory | wlp-neighbor | wlp-neighbor/memory.high 803209216->829423616 | RAISE |
| 15:03:51 | saturation | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 45000->67500; wlp-neighbor/cpu.weight 100->200 | RAISE |
| 15:04:10 | saturation | restrict_process_count | wlp-neighbor | wlp-neighbor/pids.max 27->31 | LOWER |
| 15:04:34 | decay | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 67500->100000; wlp-neighbor/cpu.weight 200->400 | GIVE-BACK RAISE |
| 15:05:15 | tail | decrease_cpu | wlp-neighbor | wlp-neighbor/cpu.max 100000->60000; wlp-neighbor/cpu.weight 400->200 | GIVE-BACK LOWER |
| 15:05:27 | rise-fall | restrict_process_count | wlp-neighbor | wlp-neighbor/pids.max 31->16 | LOWER |
| 15:05:29 | rise-fall | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 60000->90000; wlp-neighbor/cpu.weight 200->400 | RAISE |

Give-back moments (writes during idle / cut-to-idle / mem-release / decay / tail regimes): 2 of 11 applied writes.
* 15:04:34 [decay] increase_cpu: wlp-neighbor/cpu.max 67500->100000; wlp-neighbor/cpu.weight 200->400
* 15:05:15 [tail] decrease_cpu: wlp-neighbor/cpu.max 100000->60000; wlp-neighbor/cpu.weight 400->200  <- LOWERING
* The controller DID lower allocations during give-back regimes (1 times).

## Outcome deltas (3 telemetry samples after vs 3 before; directional only)

| ts | regime | action | victim p95 ms | n cpu psi | n mem MB | n mem high MB | n pids | n throttle us/s | sys io psi | sys load1 |
|---|---|---|---|---|---|---|---|---|---|---|
| 15:01:02 | cpu-spike | restrict_process_count | 0.9->0.9 | 67.9->71.4 | 28->42 | 716->716 | 8->11 | 4,611,274->8,309,816 | 0.0->0.0 | 0.43->0.45 |
| 15:01:04 | cpu-spike | increase_cpu | 0.9->0.8 | 67.3->73.8 | 35->42 | 716->716 | 9->11 | 6,928,936->9,315,703 | 0.0->0.0 | 0.45->0.44 |
| 15:01:40 | mem-hold | increase_memory | 0.8->0.6 | 12.2->7.3 | 169->653 | 716->741 | 2->2 | 21,157->0 | 0.0->0.0 | 0.37->0.38 |
| 15:01:59 | mem-hold | decrease_cpu | 0.9->0.9 | 2.3->1.2 | 653->653 | 766->766 | 2->2 | 0->0 | 0.0->0.0 | 0.42->0.38 |
| 15:03:25 | mixed | increase_memory | 1.0->1.0 | 6.7->32.3 | 359->756 | 766->785 | 12->7 | 1,890,887->1,634,226 | 0.0->0.0 | 0.41->0.42 |
| 15:03:51 | saturation | increase_cpu | 0.9->0.8 | 67.2->71.9 | 578->46 | 791->791 | 8->11 | 1,948,393->8,971,099 | 0.1->0.1 | 0.55->0.55 |
| 15:04:10 | saturation | restrict_process_count | 0.9->0.9 | 66.5->47.3 | 382->17 | 791->791 | 10->22 | 901,322->1,313,877 | 0.0->0.0 | 0.69->0.69 |
| 15:04:34 | decay | increase_cpu | 0.9->0.9 | 65.5->64.3 | 16->14 | 791->791 | 4->4 | 1,425,289->815,762 | 0.2->0.2 | 1.16->1.22 |
| 15:05:15 | tail | decrease_cpu | 0.8->0.7 | 2.4->1.3 | 8->8 | 791->791 | 2->2 | 0->0 | 0.0->0.0 | 0.79->0.73 |
| 15:05:27 | rise-fall | restrict_process_count | 0.6->0.8 | 3.6->30.5 | 13->31 | 791->791 | 4->8 | 1,504,089->5,264,387 | 0.0->0.0 | 0.71->0.65 |
| 15:05:29 | rise-fall | increase_cpu | 0.6->0.9 | 9.9->40.8 | 19->31 | 791->791 | 5->8 | 3,283,754->5,161,788 | 0.0->0.0 | 0.70->0.63 |

## Anomalies / observations

* action do_nothing repeated 28 times in a row from 2026-10-18T15:00:06.651Z
* action do_nothing repeated 12 times in a row from 2026-10-18T15:01:17.530Z
* action do_nothing repeated 43 times in a row from 2026-10-18T15:02:01.016Z
* action increase_memory repeated 13 times in a row from 2026-10-18T15:03:25.372Z
* action increase_cpu repeated 14 times in a row from 2026-10-18T15:04:12.648Z
* action do_nothing repeated 18 times in a row from 2026-10-18T15:04:40.127Z
* applied actions without an outcome row: 2

## Caveats

* Outcome deltas use 3 telemetry samples per side: directional evidence, not causal proof.
* Cooldown 45 s suppresses repeated writes, so chosen-action counts exceed applied counts by design.
* Quiet regimes are cpu_burn procs=0 phases (the stressor sleeps); mixed-phase magnitudes are runner-fixed (cpu 2, mem to memory.high, io 4 MB/s).

