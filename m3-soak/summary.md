# M3 Soak v1 — summary

Run: /root/workloadpilot/m3/soak/run
Scenario seed 7317 · victim latency · model workloadpilot/v2-2b · scale 1.0 · runner ok in 3512.6 s

## Decisions, tokens, gate

| metric | value |
|---|---|
| decisions | 1755 over 3510.3 s (30.0 /min) |
| model errors / controller errors | 0 / 0 |
| tokens | 1,148,451 total, median 648 per decision (missing on 0) |
| cost estimate | $0.00804 (at $0.007/M in) |
| gate | applied 36, pass-no-write 1229, rejected-cooldown 490 |
| rejection reasons | cooldown x490 |

Actions chosen overall: do_nothing 1227, increase_cpu 300, increase_memory 208, restrict_process_count 17, alert_operator 2, throttle_io 1

## Per-regime action mix

| regime | windows | duration | decisions | /min | applied | pass | rejected | errors | action mix |
|---|---|---|---|---|---|---|---|---|---|
| idle | 1 | 180.0s | 90 | 30.0 | 0 | 90 | 0 | 0 | do_nothing 90 |
| cpu-moderate | 1 | 360.0s | 180 | 30.0 | 5 | 98 | 77 | 0 | do_nothing 98, increase_cpu 80, restrict_process_count 2 |
| cpu-spike | 1 | 180.0s | 90 | 30.0 | 5 | 1 | 84 | 0 | increase_cpu 87, restrict_process_count 2, do_nothing 1 |
| cut-to-idle | 1 | 240.0s | 120 | 30.0 | 0 | 120 | 0 | 0 | do_nothing 120 |
| mem-hold | 1 | 300.0s | 150 | 30.0 | 0 | 150 | 0 | 0 | do_nothing 150 |
| mem-release | 1 | 180.0s | 90 | 30.0 | 0 | 90 | 0 | 0 | do_nothing 90 |
| io | 1 | 240.0s | 120 | 30.0 | 0 | 120 | 0 | 0 | do_nothing 120 |
| io-burst | 1 | 120.0s | 60 | 30.0 | 0 | 60 | 0 | 0 | do_nothing 60 |
| fork | 1 | 180.0s | 90 | 30.0 | 1 | 87 | 2 | 0 | do_nothing 87, restrict_process_count 3 |
| mixed | 1 | 300.0s | 150 | 30.0 | 8 | 0 | 142 | 0 | increase_memory 149, restrict_process_count 1 |
| saturation | 3 | 240.0s | 120 | 30.0 | 7 | 55 | 58 | 0 | increase_memory 59, do_nothing 55, restrict_process_count 5, throttle_io 1 |
| decay | 2 | 240.0s | 120 | 30.0 | 5 | 58 | 57 | 0 | increase_cpu 59, do_nothing 58, restrict_process_count 3 |
| decay-off | 1 | 120.0s | 60 | 30.0 | 0 | 60 | 0 | 0 | do_nothing 60 |
| tail | 1 | 360.0s | 180 | 30.0 | 0 | 180 | 0 | 0 | do_nothing 180 |
| rise-fall | 2 | 240.0s | 119 | 29.8 | 5 | 44 | 70 | 0 | increase_cpu 74, do_nothing 44, restrict_process_count 1 |
| warmup | 1 | 0.0s | 5 | - | 0 | 5 | 0 | 0 | do_nothing 5 |
| after-run | 1 | 0.0s | 11 | - | 0 | 11 | 0 | 0 | do_nothing 9, alert_operator 2 |

## Applied writes (before -> after)

`GIVE-BACK` = applied during an idle/cut-to-idle/mem-release/decay/tail regime; `LOWER` = the action lowers an allocation.

| ts | regime | action | target | write | flags |
|---|---|---|---|---|---|
| 09:01:05 | cpu-moderate | restrict_process_count | wlp-neighbor | wlp-neighbor/pids.max 54->27 | LOWER |
| 09:01:11 | cpu-moderate | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 50000->75000; wlp-neighbor/cpu.weight 100->200 | RAISE |
| 09:01:57 | cpu-moderate | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 75000->100000; wlp-neighbor/cpu.weight 200->400 | RAISE |
| 09:02:43 | cpu-moderate | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 100000->100000; wlp-neighbor/cpu.weight 400->800 | RAISE |
| 09:03:29 | cpu-moderate | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 100000->100000; wlp-neighbor/cpu.weight 800->1600 | RAISE |
| 09:07:05 | cpu-spike | restrict_process_count | wlp-neighbor | wlp-neighbor/pids.max 27->16 | LOWER |
| 09:07:11 | cpu-spike | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 100000->100000; wlp-neighbor/cpu.weight 1600->3200 | RAISE |
| 09:07:55 | cpu-spike | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 100000->100000; wlp-neighbor/cpu.weight 3200->6400 | RAISE |
| 09:08:41 | cpu-spike | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 100000->100000; wlp-neighbor/cpu.weight 6400->10000 | RAISE |
| 09:09:27 | cpu-spike | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 100000->100000; wlp-neighbor/cpu.weight 10000->10000 | RAISE |
| 09:28:05 | fork | restrict_process_count | wlp-neighbor | wlp-neighbor/pids.max 16->20 | LOWER |
| 09:31:06 | mixed | restrict_process_count | wlp-neighbor | wlp-neighbor/pids.max 20->16 | LOWER |
| 09:31:08 | mixed | increase_memory | wlp-neighbor | wlp-neighbor/memory.high 750780416->803209216 | RAISE |
| 09:31:54 | mixed | increase_memory | wlp-neighbor | wlp-neighbor/memory.high 803209216->829423616 | RAISE |
| 09:32:40 | mixed | increase_memory | wlp-neighbor | wlp-neighbor/memory.high 829423616->829423616 | RAISE |
| 09:33:26 | mixed | increase_memory | wlp-neighbor | wlp-neighbor/memory.high 829423616->829423616 | RAISE |
| 09:34:12 | mixed | increase_memory | wlp-neighbor | wlp-neighbor/memory.high 829423616->829423616 | RAISE |
| 09:34:58 | mixed | increase_memory | wlp-neighbor | wlp-neighbor/memory.high 829423616->829423616 | RAISE |
| 09:35:44 | mixed | increase_memory | wlp-neighbor | wlp-neighbor/memory.high 829423616->829423616 | RAISE |
| 09:36:06 | saturation | throttle_io | wlp-neighbor | wlp-neighbor/io.max None->1048576 | LOWER |
| 09:36:10 | saturation | restrict_process_count | wlp-neighbor | wlp-neighbor/pids.max 16->17 | LOWER |
| 09:37:06 | saturation | restrict_process_count | wlp-neighbor | wlp-neighbor/pids.max 17->16 | LOWER |
| 09:37:08 | saturation | increase_memory | wlp-neighbor | wlp-neighbor/memory.high 829423616->829423616 | RAISE |
| 09:37:52 | saturation | increase_memory | wlp-neighbor | wlp-neighbor/memory.high 829423616->829423616 | RAISE |
| 09:38:38 | saturation | increase_memory | wlp-neighbor | wlp-neighbor/memory.high 829423616->829423616 | RAISE |
| 09:39:06 | saturation | restrict_process_count | wlp-neighbor | wlp-neighbor/pids.max 16->21 | LOWER |
| 09:40:06 | decay | restrict_process_count | wlp-neighbor | wlp-neighbor/pids.max 21->16 | GIVE-BACK LOWER |
| 09:40:12 | decay | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 100000->100000; wlp-neighbor/cpu.weight 10000->10000 | GIVE-BACK RAISE |
| 09:40:58 | decay | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 100000->100000; wlp-neighbor/cpu.weight 10000->10000 | GIVE-BACK RAISE |
| 09:41:44 | decay | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 100000->100000; wlp-neighbor/cpu.weight 10000->10000 | GIVE-BACK RAISE |
| 09:42:12 | decay | restrict_process_count | wlp-neighbor | wlp-neighbor/pids.max 16->16 | GIVE-BACK LOWER |
| 09:52:06 | rise-fall | restrict_process_count | wlp-neighbor | wlp-neighbor/pids.max 16->16 | LOWER |
| 09:52:08 | rise-fall | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 100000->100000; wlp-neighbor/cpu.weight 10000->10000 | RAISE |
| 09:52:54 | rise-fall | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 100000->100000; wlp-neighbor/cpu.weight 10000->10000 | RAISE |
| 09:53:41 | rise-fall | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 100000->100000; wlp-neighbor/cpu.weight 10000->10000 | RAISE |
| 09:54:27 | rise-fall | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 100000->100000; wlp-neighbor/cpu.weight 10000->10000 | RAISE |

Give-back moments (writes during idle / cut-to-idle / mem-release / decay / tail regimes): 5 of 36 applied writes.
* 09:40:06 [decay] restrict_process_count: wlp-neighbor/pids.max 21->16  <- LOWERING
* 09:40:12 [decay] increase_cpu: wlp-neighbor/cpu.max 100000->100000; wlp-neighbor/cpu.weight 10000->10000
* 09:40:58 [decay] increase_cpu: wlp-neighbor/cpu.max 100000->100000; wlp-neighbor/cpu.weight 10000->10000
* 09:41:44 [decay] increase_cpu: wlp-neighbor/cpu.max 100000->100000; wlp-neighbor/cpu.weight 10000->10000
* 09:42:12 [decay] restrict_process_count: wlp-neighbor/pids.max 16->16  <- LOWERING
* The controller DID lower allocations during give-back regimes (2 times).

## Outcome deltas (3 telemetry samples after vs 3 before; directional only)

| ts | regime | action | victim p95 ms | n cpu psi | n mem MB | n mem high MB | n pids | n throttle us/s | sys io psi | sys load1 |
|---|---|---|---|---|---|---|---|---|---|---|
| 09:01:05 | cpu-moderate | restrict_process_count | 0.6->0.7 | 0.0->10.5 | 9->15 | 716->716 | 2->4 | 0->1,506,129 | 0.0->0.0 | 0.22->0.20 |
| 09:01:11 | cpu-moderate | increase_cpu | 0.7->0.6 | 10.5->36.4 | 15->15 | 716->716 | 4->4 | 1,506,129->1,344,511 | 0.0->0.0 | 0.20->0.18 |
| 09:01:57 | cpu-moderate | increase_cpu | 0.9->0.7 | 61.4->60.7 | 15->15 | 716->716 | 4->4 | 1,227,483->1,070,021 | 0.0->0.0 | 0.69->0.81 |
| 09:02:43 | cpu-moderate | increase_cpu | 0.5->0.5 | 49.5->49.4 | 15->15 | 716->716 | 4->4 | 1,005,110->997,291 | 0.0->0.0 | 1.40->1.32 |
| 09:03:29 | cpu-moderate | increase_cpu | 0.6->0.6 | 49.5->49.0 | 15->15 | 716->716 | 4->4 | 995,578->983,857 | 0.0->0.0 | 0.68->0.61 |
| 09:07:05 | cpu-spike | restrict_process_count | 0.5->0.7 | 49.6->55.5 | 22->43 | 716->716 | 6->11 | 1,194,250->8,042,510 | 0.0->0.0 | 1.49->1.36 |
| 09:07:11 | cpu-spike | increase_cpu | 0.7->0.6 | 55.5->69.1 | 43->42 | 716->716 | 11->11 | 8,042,510->8,030,230 | 0.0->0.0 | 1.36->1.25 |
| 09:07:55 | cpu-spike | increase_cpu | 0.8->0.7 | 87.6->87.6 | 42->42 | 716->716 | 11->11 | 7,962,213->7,986,852 | 0.0->0.0 | 0.90->1.57 |
| 09:08:41 | cpu-spike | increase_cpu | 0.6->0.7 | 88.1->88.0 | 42->42 | 716->716 | 11->11 | 8,064,217->8,004,372 | 0.0->0.0 | 1.94->1.76 |
| 09:09:27 | cpu-spike | increase_cpu | 1.0->0.7 | 88.1->88.1 | 42->42 | 716->716 | 11->11 | 7,927,014->7,983,982 | 0.0->0.0 | 1.00->0.90 |
| 09:28:05 | fork | restrict_process_count | 0.7->0.6 | 0.0->0.0 | 10->12 | 716->716 | 6->18 | 0->0 | 72.0->55.1 | 1.19->1.18 |
| 09:31:06 | mixed | restrict_process_count | 0.5->0.8 | 0.0->8.7 | 91->624 | 716->741 | 16->7 | 206,762->1,502,979 | 0.0->4.8 | 0.39->0.65 |
| 09:31:08 | mixed | increase_memory | 0.8->0.8 | 1.6->13.4 | 267->723 | 716->754 | 13->7 | 844,729->1,199,501 | 0.9->8.1 | 0.45->0.77 |
| 09:31:54 | mixed | increase_memory | 0.5->0.4 | 32.7->32.9 | 725->725 | 766->785 | 7->7 | 1,009,237->1,025,346 | 28.8->28.9 | 1.98->2.06 |
| 09:32:40 | mixed | increase_memory | 0.5->0.7 | 33.4->33.4 | 725->725 | 791->791 | 7->7 | 1,023,261->993,521 | 27.8->26.3 | 1.75->1.68 |
| 09:33:26 | mixed | increase_memory | 0.6->0.5 | 33.0->33.1 | 725->725 | 791->791 | 7->7 | 997,423->1,012,534 | 27.6->28.5 | 2.15->2.24 |
| 09:34:12 | mixed | increase_memory | 0.5->0.4 | 33.1->33.2 | 725->725 | 791->791 | 7->7 | 1,031,192->1,030,639 | 28.9->28.5 | 2.44->2.30 |
| 09:34:58 | mixed | increase_memory | 0.9->0.6 | 33.0->32.9 | 725->725 | 791->791 | 7->7 | 976,106->1,002,255 | 28.7->28.9 | 1.82->1.88 |
| 09:35:44 | mixed | increase_memory | 0.5->0.5 | 33.1->33.2 | 725->725 | 791->791 | 7->7 | 1,018,512->1,019,801 | 28.7->28.9 | 2.59->2.62 |
| 09:36:06 | saturation | throttle_io | 0.6->0.6 | 33.2->44.9 | 556->47 | 791->791 | 8->12 | 1,431,919->9,021,950 | 28.5->20.5 | 2.82->2.70 |
| 09:36:10 | saturation | restrict_process_count | 0.6->0.5 | 39.1->58.9 | 216->46 | 791->791 | 11->12 | 6,770,681->9,055,386 | 24.1->13.8 | 2.75->2.54 |
| 09:37:06 | saturation | restrict_process_count | 0.9->0.7 | 89.0->77.2 | 74->606 | 791->791 | 11->7 | 8,504,626->1,211,691 | 0.1->5.6 | 1.18->1.30 |
| 09:37:08 | saturation | increase_memory | 0.9->0.7 | 87.1->69.9 | 251->755 | 791->791 | 10->7 | 6,087,261->999,398 | 0.8->9.3 | 1.21->1.39 |
| 09:37:52 | saturation | increase_memory | 0.5->0.5 | 33.8->33.4 | 755->755 | 791->791 | 7->7 | 1,010,998->1,016,534 | 29.5->29.7 | 2.19->2.27 |
| 09:38:38 | saturation | increase_memory | 0.6->0.8 | 33.0->32.9 | 755->755 | 791->791 | 7->7 | 1,012,927->973,500 | 30.0->30.0 | 2.10->2.07 |
| 09:39:06 | saturation | restrict_process_count | 0.5->0.8 | 33.0->25.5 | 569->12 | 791->791 | 9->19 | 978,344->0 | 30.0->25.4 | 1.86->1.76 |
| 09:40:06 | decay | restrict_process_count | 0.7->0.7 | 0.1->18.3 | 16->27 | 791->791 | 17->7 | 122,518->4,046,558 | 0.1->0.1 | 0.89->0.84 |
| 09:40:12 | decay | increase_cpu | 0.7->1.2 | 18.3->45.3 | 27->27 | 791->791 | 7->7 | 4,046,558->3,971,740 | 0.1->0.0 | 0.84->0.75 |
| 09:40:58 | decay | increase_cpu | 0.7->0.5 | 78.7->78.5 | 26->26 | 791->791 | 7->7 | 3,981,383->4,012,654 | 0.0->0.0 | 0.38->0.34 |
| 09:41:44 | decay | increase_cpu | 0.5->0.4 | 78.8->78.7 | 26->26 | 791->791 | 7->7 | 4,043,944->4,031,533 | 0.0->0.0 | 2.11->2.10 |
| 09:42:12 | decay | restrict_process_count | 0.5->0.5 | 69.7->60.3 | 16->15 | 791->791 | 4->4 | 1,009,615->1,013,804 | 0.0->0.0 | 1.65->1.69 |
| 09:52:06 | rise-fall | restrict_process_count | 0.9->0.8 | 0.0->14.5 | 13->31 | 791->791 | 4->8 | 377,988->4,930,283 | 0.0->0.0 | 0.07->0.06 |
| 09:52:08 | rise-fall | increase_cpu | 0.9->0.7 | 1.8->24.6 | 19->31 | 791->791 | 5->8 | 2,015,493->4,956,900 | 0.0->0.0 | 0.07->0.06 |
| 09:52:54 | rise-fall | increase_cpu | 0.4->0.2 | 81.4->82.0 | 31->31 | 791->791 | 8->8 | 5,028,444->5,043,975 | 0.0->0.0 | 0.09->0.07 |
| 09:53:41 | rise-fall | increase_cpu | 0.2->0.6 | 82.8->82.6 | 30->30 | 791->791 | 8->8 | 5,052,379->4,906,000 | 0.2->0.1 | 0.30->0.32 |
| 09:54:27 | rise-fall | increase_cpu | 0.3->0.2 | 82.6->82.5 | 30->30 | 791->791 | 8->8 | 5,003,440->5,020,022 | 0.0->0.0 | 1.85->1.67 |

## Anomalies / observations

* action do_nothing repeated 95 times in a row from 2026-10-17T08:57:54.925Z
* action increase_cpu repeated 80 times in a row from 2026-10-17T09:01:11.040Z
* action do_nothing repeated 97 times in a row from 2026-10-17T09:03:51.122Z
* action increase_cpu repeated 87 times in a row from 2026-10-17T09:07:11.234Z
* action do_nothing repeated 540 times in a row from 2026-10-17T09:10:05.341Z
* action do_nothing repeated 85 times in a row from 2026-10-17T09:28:15.987Z
* action increase_memory repeated 149 times in a row from 2026-10-17T09:31:08.075Z
* action do_nothing repeated 27 times in a row from 2026-10-17T09:36:12.239Z
* action increase_memory repeated 59 times in a row from 2026-10-17T09:37:08.273Z
* action do_nothing repeated 25 times in a row from 2026-10-17T09:39:16.338Z
* action increase_cpu repeated 59 times in a row from 2026-10-17T09:40:12.366Z
* action do_nothing repeated 296 times in a row from 2026-10-17T09:42:14.442Z
* action increase_cpu repeated 74 times in a row from 2026-10-17T09:52:08.810Z
* action do_nothing repeated 44 times in a row from 2026-10-17T09:54:37.118Z
* applied actions without an outcome row: 4

## Caveats

* Outcome deltas use 3 telemetry samples per side: directional evidence, not causal proof.
* Cooldown 45 s suppresses repeated writes, so chosen-action counts exceed applied counts by design.
* Quiet regimes are cpu_burn procs=0 phases (the stressor sleeps); mixed-phase magnitudes are runner-fixed (cpu 2, mem to memory.high, io 4 MB/s).

