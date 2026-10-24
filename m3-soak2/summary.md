# M3 Soak v1 — summary

Run: /root/workloadpilot/m3/soak2/run
Scenario seed 7317 · victim latency · model workloadpilot/v3-2b · scale 1.0 · runner ok in 3512.5 s

## Decisions, tokens, gate

| metric | value |
|---|---|
| decisions | 1754 over 3432.9 s (30.7 /min) |
| model errors / controller errors | 0 / 0 |
| tokens | 1,145,877 total, median 646 per decision (missing on 0) |
| cost estimate | $0.00802 (at $0.007/M in) |
| gate | applied 30, pass-no-write 1289, rejected-cooldown 435 |
| rejection reasons | cooldown x435 |

Actions chosen overall: do_nothing 1287, increase_cpu 248, increase_memory 211, decrease_cpu 4, restrict_process_count 2, alert_operator 2

## Per-regime action mix

| regime | windows | duration | decisions | /min | applied | pass | rejected | errors | action mix |
|---|---|---|---|---|---|---|---|---|---|
| idle | 1 | 177.4s | 90 | 30.4 | 0 | 90 | 0 | 0 | do_nothing 90 |
| cpu-moderate | 1 | 353.6s | 179 | 30.4 | 0 | 179 | 0 | 0 | do_nothing 179 |
| cpu-spike | 1 | 175.8s | 90 | 30.7 | 5 | 0 | 85 | 0 | increase_cpu 89, restrict_process_count 1 |
| cut-to-idle | 1 | 235.0s | 120 | 30.6 | 1 | 119 | 0 | 0 | do_nothing 119, decrease_cpu 1 |
| mem-hold | 1 | 293.4s | 150 | 30.7 | 1 | 148 | 1 | 0 | do_nothing 148, increase_memory 2 |
| mem-release | 1 | 175.5s | 90 | 30.8 | 0 | 90 | 0 | 0 | do_nothing 90 |
| io | 1 | 234.0s | 119 | 30.5 | 0 | 119 | 0 | 0 | do_nothing 119 |
| io-burst | 1 | 117.8s | 61 | 31.1 | 0 | 61 | 0 | 0 | do_nothing 61 |
| fork | 1 | 175.5s | 90 | 30.8 | 0 | 90 | 0 | 0 | do_nothing 90 |
| mixed | 1 | 293.2s | 149 | 30.5 | 7 | 1 | 141 | 0 | increase_memory 148, do_nothing 1 |
| saturation | 3 | 234.7s | 120 | 30.7 | 6 | 28 | 86 | 0 | increase_memory 61, increase_cpu 30, do_nothing 28, decrease_cpu 1 |
| decay | 2 | 233.7s | 120 | 30.8 | 3 | 64 | 53 | 0 | do_nothing 64, increase_cpu 56 |
| decay-off | 1 | 117.8s | 60 | 30.6 | 1 | 59 | 0 | 0 | do_nothing 59, decrease_cpu 1 |
| tail | 1 | 351.8s | 180 | 30.7 | 0 | 180 | 0 | 0 | do_nothing 180 |
| rise-fall | 2 | 236.3s | 121 | 30.7 | 6 | 46 | 69 | 0 | increase_cpu 73, do_nothing 45, decrease_cpu 1, restrict_process_count 1, alert_operator 1 |
| warmup | 1 | 0.0s | 6 | - | 0 | 6 | 0 | 0 | do_nothing 6 |
| after-run | 1 | 0.0s | 9 | - | 0 | 9 | 0 | 0 | do_nothing 8, alert_operator 1 |

## Applied writes (before -> after)

`GIVE-BACK` = applied during an idle/cut-to-idle/mem-release/decay/tail regime; `LOWER` = the action lowers an allocation.

| ts | regime | action | target | write | flags |
|---|---|---|---|---|---|
| 15:17:43 | cpu-spike | restrict_process_count | wlp-neighbor | wlp-neighbor/pids.max 54->27 | LOWER |
| 15:17:45 | cpu-spike | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 50000->75000; wlp-neighbor/cpu.weight 100->200 | RAISE |
| 15:18:29 | cpu-spike | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 75000->100000; wlp-neighbor/cpu.weight 200->400 | RAISE |
| 15:19:15 | cpu-spike | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 100000->100000; wlp-neighbor/cpu.weight 400->800 | RAISE |
| 15:19:59 | cpu-spike | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 100000->100000; wlp-neighbor/cpu.weight 800->1600 | RAISE |
| 15:21:18 | cut-to-idle | decrease_cpu | wlp-neighbor | wlp-neighbor/cpu.max 100000->60000; wlp-neighbor/cpu.weight 1600->800 | GIVE-BACK LOWER |
| 15:24:36 | mem-hold | increase_memory | wlp-neighbor | wlp-neighbor/memory.high 750780416->803209216 | RAISE |
| 15:41:13 | mixed | increase_memory | wlp-neighbor | wlp-neighbor/memory.high 803209216->829423616 | RAISE |
| 15:41:58 | mixed | increase_memory | wlp-neighbor | wlp-neighbor/memory.high 829423616->829423616 | RAISE |
| 15:42:43 | mixed | increase_memory | wlp-neighbor | wlp-neighbor/memory.high 829423616->829423616 | RAISE |
| 15:43:30 | mixed | increase_memory | wlp-neighbor | wlp-neighbor/memory.high 829423616->829423616 | RAISE |
| 15:44:15 | mixed | increase_memory | wlp-neighbor | wlp-neighbor/memory.high 829423616->829423616 | RAISE |
| 15:45:00 | mixed | increase_memory | wlp-neighbor | wlp-neighbor/memory.high 829423616->829423616 | RAISE |
| 15:45:45 | mixed | increase_memory | wlp-neighbor | wlp-neighbor/memory.high 829423616->829423616 | RAISE |
| 15:46:05 | saturation | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 60000->90000; wlp-neighbor/cpu.weight 800->1600 | RAISE |
| 15:46:51 | saturation | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 90000->100000; wlp-neighbor/cpu.weight 1600->3200 | RAISE |
| 15:47:03 | saturation | increase_memory | wlp-neighbor | wlp-neighbor/memory.high 829423616->829423616 | RAISE |
| 15:47:48 | saturation | increase_memory | wlp-neighbor | wlp-neighbor/memory.high 829423616->829423616 | RAISE |
| 15:48:33 | saturation | increase_memory | wlp-neighbor | wlp-neighbor/memory.high 829423616->829423616 | RAISE |
| 15:49:34 | saturation | decrease_cpu | wlp-neighbor | wlp-neighbor/cpu.max 100000->60000; wlp-neighbor/cpu.weight 3200->1600 | LOWER |
| 15:50:08 | decay | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 60000->90000; wlp-neighbor/cpu.weight 1600->3200 | GIVE-BACK RAISE |
| 15:50:54 | decay | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 90000->100000; wlp-neighbor/cpu.weight 3200->6400 | GIVE-BACK RAISE |
| 15:51:39 | decay | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 100000->100000; wlp-neighbor/cpu.weight 6400->10000 | GIVE-BACK RAISE |
| 15:54:25 | decay-off | decrease_cpu | wlp-neighbor | wlp-neighbor/cpu.max 100000->60000; wlp-neighbor/cpu.weight 10000->5000 | GIVE-BACK LOWER |
| 16:01:43 | rise-fall | restrict_process_count | wlp-neighbor | wlp-neighbor/pids.max 27->16 | LOWER |
| 16:01:45 | rise-fall | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 60000->90000; wlp-neighbor/cpu.weight 5000->10000 | RAISE |
| 16:02:30 | rise-fall | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 90000->100000; wlp-neighbor/cpu.weight 10000->10000 | RAISE |
| 16:03:18 | rise-fall | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 100000->100000; wlp-neighbor/cpu.weight 10000->10000 | RAISE |
| 16:04:02 | rise-fall | increase_cpu | wlp-neighbor | wlp-neighbor/cpu.max 100000->100000; wlp-neighbor/cpu.weight 10000->10000 | RAISE |
| 16:04:47 | rise-fall | decrease_cpu | wlp-neighbor | wlp-neighbor/cpu.max 100000->60000; wlp-neighbor/cpu.weight 10000->5000 | LOWER |

Give-back moments (writes during idle / cut-to-idle / mem-release / decay / tail regimes): 5 of 30 applied writes.
* 15:21:18 [cut-to-idle] decrease_cpu: wlp-neighbor/cpu.max 100000->60000; wlp-neighbor/cpu.weight 1600->800  <- LOWERING
* 15:50:08 [decay] increase_cpu: wlp-neighbor/cpu.max 60000->90000; wlp-neighbor/cpu.weight 1600->3200
* 15:50:54 [decay] increase_cpu: wlp-neighbor/cpu.max 90000->100000; wlp-neighbor/cpu.weight 3200->6400
* 15:51:39 [decay] increase_cpu: wlp-neighbor/cpu.max 100000->100000; wlp-neighbor/cpu.weight 6400->10000
* 15:54:25 [decay-off] decrease_cpu: wlp-neighbor/cpu.max 100000->60000; wlp-neighbor/cpu.weight 10000->5000  <- LOWERING
* The controller DID lower allocations during give-back regimes (2 times).

## Outcome deltas (3 telemetry samples after vs 3 before; directional only)

| ts | regime | action | victim p95 ms | n cpu psi | n mem MB | n mem high MB | n pids | n throttle us/s | sys io psi | sys load1 |
|---|---|---|---|---|---|---|---|---|---|---|
| 15:17:43 | cpu-spike | restrict_process_count | 0.8->0.5 | 72.8->73.9 | 20->41 | 716->716 | 6->11 | 1,627,135->8,237,326 | 0.0->0.0 | 0.84->0.83 |
| 15:17:45 | cpu-spike | increase_cpu | 0.8->0.6 | 73.0->76.0 | 27->42 | 716->716 | 8->11 | 3,932,860->8,164,563 | 0.0->0.0 | 0.84->0.80 |
| 15:18:29 | cpu-spike | increase_cpu | 0.6->0.9 | 90.5->90.4 | 42->42 | 716->716 | 11->11 | 8,946,071->7,813,753 | 0.0->0.0 | 0.47->0.42 |
| 15:19:15 | cpu-spike | increase_cpu | 1.2->1.0 | 88.0->88.0 | 42->42 | 716->716 | 11->11 | 7,747,576->7,815,766 | 0.0->0.0 | 0.39->0.35 |
| 15:19:59 | cpu-spike | increase_cpu | 0.9->0.7 | 88.0->88.0 | 42->42 | 716->716 | 11->11 | 8,990,217->7,925,206 | 0.0->0.0 | 2.06->1.89 |
| 15:21:18 | cut-to-idle | decrease_cpu | 1.0->1.0 | 2.7->1.5 | 7->7 | 716->716 | 2->2 | 0->0 | 0.0->0.0 | 0.64->0.57 |
| 15:24:36 | mem-hold | increase_memory | 0.5->0.5 | 0.5->1.5 | 282->653 | 716->754 | 2->2 | 38,831->0 | 0.0->0.0 | 0.34->0.32 |
| 15:41:13 | mixed | increase_memory | 1.3->1.1 | 1.8->21.2 | 305->756 | 766->785 | 17->7 | 1,146,503->1,427,542 | 0.0->0.0 | 0.41->0.39 |
| 15:41:58 | mixed | increase_memory | 1.1->1.0 | 65.6->65.9 | 755->755 | 791->791 | 7->7 | 1,417,313->1,640,181 | 0.0->0.0 | 0.36->0.76 |
| 15:42:43 | mixed | increase_memory | 1.0->1.0 | 65.2->65.6 | 755->755 | 791->791 | 7->7 | 1,445,465->1,449,926 | 0.0->0.0 | 1.25->1.19 |
| 15:43:30 | mixed | increase_memory | 1.0->1.0 | 66.4->65.6 | 755->755 | 791->791 | 7->7 | 1,450,078->1,432,666 | 0.0->0.0 | 0.65->0.67 |
| 15:44:15 | mixed | increase_memory | 1.0->1.0 | 66.1->66.0 | 755->755 | 791->791 | 7->7 | 1,443,460->1,429,210 | 0.1->0.1 | 1.01->1.17 |
| 15:45:00 | mixed | increase_memory | 1.0->1.0 | 64.3->64.9 | 755->755 | 791->791 | 7->7 | 1,418,859->1,429,561 | 0.2->0.1 | 1.21->1.16 |
| 15:45:45 | mixed | increase_memory | 1.0->1.0 | 66.2->66.2 | 755->755 | 791->791 | 7->7 | 1,652,579->1,445,321 | 0.0->0.0 | 0.75->0.68 |
| 15:46:05 | saturation | increase_cpu | 1.0->1.0 | 65.0->70.4 | 578->46 | 791->791 | 8->12 | 3,204,169->8,976,637 | 0.0->0.0 | 0.73->1.26 |
| 15:46:51 | saturation | increase_cpu | 1.0->1.1 | 89.2->89.5 | 46->46 | 791->791 | 12->12 | 10,177,324->8,755,810 | 0.0->0.0 | 1.36->1.28 |
| 15:47:03 | saturation | increase_memory | 1.1->1.0 | 88.8->78.2 | 220->752 | 791->791 | 11->7 | 7,314,564->1,026,816 | 0.0->0.0 | 1.22->1.20 |
| 15:47:48 | saturation | increase_memory | 1.0->1.0 | 46.6->46.5 | 755->755 | 791->791 | 7->7 | 1,015,595->1,181,919 | 0.1->0.0 | 0.68->0.61 |
| 15:48:33 | saturation | increase_memory | 1.0->1.0 | 46.7->47.1 | 755->755 | 791->791 | 7->7 | 1,016,012->1,016,202 | 0.0->0.0 | 1.21->1.28 |
| 15:49:34 | saturation | decrease_cpu | 1.0->1.0 | 2.3->1.3 | 14->14 | 791->791 | 26->26 | 0->0 | 0.0->0.0 | 0.93->0.97 |
| 15:50:08 | decay | increase_cpu | 1.0->1.0 | 35.7->58.1 | 27->27 | 791->791 | 7->7 | 4,292,353->5,057,637 | 0.0->0.0 | 0.81->1.31 |
| 15:50:54 | decay | increase_cpu | 1.0->1.2 | 80.1->80.0 | 27->27 | 791->791 | 7->7 | 3,997,952->3,891,943 | 0.0->0.0 | 1.60->1.50 |
| 15:51:39 | decay | increase_cpu | 1.1->1.0 | 78.6->78.5 | 27->27 | 791->791 | 7->7 | 3,889,867->4,429,270 | 0.0->0.0 | 0.80->0.78 |
| 15:54:25 | decay-off | decrease_cpu | 1.0->1.0 | 2.6->1.4 | 7->7 | 791->791 | 2->2 | 0->0 | 0.0->0.0 | 0.55->0.51 |
| 16:01:43 | rise-fall | restrict_process_count | 1.1->1.1 | 0.7->22.5 | 13->30 | 791->791 | 4->8 | 1,799,305->5,164,767 | 0.0->0.0 | 0.40->0.36 |
| 16:01:45 | rise-fall | increase_cpu | 1.0->1.1 | 4.9->33.8 | 19->30 | 791->791 | 5->8 | 3,809,452->5,063,623 | 0.0->0.0 | 0.38->0.34 |
| 16:02:30 | rise-fall | increase_cpu | 1.1->1.0 | 82.0->82.0 | 30->30 | 791->791 | 8->8 | 5,056,438->4,916,661 | 0.0->0.0 | 1.31->1.77 |
| 16:03:18 | rise-fall | increase_cpu | 1.0->1.0 | 82.0->81.9 | 30->30 | 791->791 | 8->8 | 4,873,477->5,545,987 | 0.0->0.0 | 1.38->1.24 |
| 16:04:02 | rise-fall | increase_cpu | 1.0->1.0 | 82.5->82.3 | 30->24 | 791->791 | 8->6 | 4,871,671->4,878,502 | 0.0->0.0 | 0.75->0.68 |
| 16:04:47 | rise-fall | decrease_cpu | 0.7->1.0 | 2.5->6.5 | 11->11 | 791->791 | 2->2 | 0->373,430 | 0.0->0.0 | 0.85->0.86 |

## Anomalies / observations

* action do_nothing repeated 275 times in a row from 2026-10-18T15:08:41.651Z
* action increase_cpu repeated 89 times in a row from 2026-10-18T15:17:45.151Z
* action do_nothing repeated 20 times in a row from 2026-10-18T15:20:39.147Z
* action do_nothing repeated 100 times in a row from 2026-10-18T15:21:20.516Z
* action do_nothing repeated 508 times in a row from 2026-10-18T15:24:40.419Z
* action increase_memory repeated 149 times in a row from 2026-10-18T15:41:13.624Z
* action increase_cpu repeated 30 times in a row from 2026-10-18T15:46:05.130Z
* action increase_memory repeated 60 times in a row from 2026-10-18T15:47:03.678Z
* action do_nothing repeated 17 times in a row from 2026-10-18T15:49:00.784Z
* action do_nothing repeated 16 times in a row from 2026-10-18T15:49:36.045Z
* action increase_cpu repeated 56 times in a row from 2026-10-18T15:50:08.066Z
* action do_nothing repeated 76 times in a row from 2026-10-18T15:51:56.879Z
* action do_nothing repeated 223 times in a row from 2026-10-18T15:54:27.310Z
* action increase_cpu repeated 73 times in a row from 2026-10-18T16:01:45.406Z
* action do_nothing repeated 20 times in a row from 2026-10-18T16:04:08.613Z
* action do_nothing repeated 24 times in a row from 2026-10-18T16:04:49.930Z
* applied actions without an outcome row: 2

## Caveats

* Outcome deltas use 3 telemetry samples per side: directional evidence, not causal proof.
* Cooldown 45 s suppresses repeated writes, so chosen-action counts exceed applied counts by design.
* Quiet regimes are cpu_burn procs=0 phases (the stressor sleeps); mixed-phase magnitudes are runner-fixed (cpu 2, mem to memory.high, io 4 MB/s).


## Head-to-head: soak v1 (v2-2b) vs soak v2 (v3-2b)

Same hand-made scenario (seed 7317, 19 phases, 3512 s), same box recipe, same cooldown 45 s; only the serving model differs.

### Totals

| metric | v1 (v2-2b) | v2 (v3-2b) |
|---|---|---|
| decisions (per min) | 1755 (30.0) | 1754 (30.7) |
| model errors / controller errors | 0 / 0 | 0 / 0 |
| tokens (median/decision) | 1,148,451 (648.0) | 1,145,877 (646.0) |
| cost estimate | $0.00804 | $0.00802 |
| gate | applied 36, pass-no-write 1229, rejected-cooldown 490 | applied 30, pass-no-write 1289, rejected-cooldown 435 |
| applied writes | 36 | 30 |
| no-op applied writes (all pairs before==after) | 10 | 9 |

### Action classes chosen / applied

| action | v1 chosen | v1 applied | v2 chosen | v2 applied |
|---|---|---|---|---|
| do_nothing | 1227 | 0 | 1287 | 0 |
| increase_cpu | 300 | 15 | 248 | 13 |
| decrease_cpu | 0 | 0 | 4 | 4 |
| increase_memory | 208 | 10 | 211 | 11 |
| throttle_io | 1 | 1 | 0 | 0 |
| restrict_process_count | 17 | 10 | 2 | 2 |
| alert_operator | 2 | 0 | 2 | 0 |

Actions seen only under v3-2b: decrease_cpu.
Actions seen only under v2-2b: throttle_io.

* `decrease_memory`: v2-2b chose it 0 times (applied 0) — v3-2b chose it 0 times (applied 0).
* `decrease_cpu`: v2-2b chose it 0 times (applied 0) — v3-2b chose it 4 times (applied 4).
* `protect_service`: v2-2b chose it 0 times (applied 0) — v3-2b chose it 0 times (applied 0).
* `throttle_io`: v2-2b chose it 1 times (applied 1) — v3-2b chose it 0 times (applied 0).

### Per-regime action mix (decisions · applied · top actions)

| regime | v1 (v2-2b) | v2 (v3-2b) |
|---|---|---|
| idle | 90 · 0 · do_nothing 90 | 90 · 0 · do_nothing 90 |
| cpu-moderate | 180 · 5 · do_nothing 98, increase_cpu 80, restrict_process_count 2 | 179 · 0 · do_nothing 179 |
| cpu-spike | 90 · 5 · increase_cpu 87, restrict_process_count 2, do_nothing 1 | 90 · 5 · increase_cpu 89, restrict_process_count 1 |
| cut-to-idle | 120 · 0 · do_nothing 120 | 120 · 1 · do_nothing 119, decrease_cpu 1 |
| mem-hold | 150 · 0 · do_nothing 150 | 150 · 1 · do_nothing 148, increase_memory 2 |
| mem-release | 90 · 0 · do_nothing 90 | 90 · 0 · do_nothing 90 |
| io | 120 · 0 · do_nothing 120 | 119 · 0 · do_nothing 119 |
| io-burst | 60 · 0 · do_nothing 60 | 61 · 0 · do_nothing 61 |
| fork | 90 · 1 · do_nothing 87, restrict_process_count 3 | 90 · 0 · do_nothing 90 |
| mixed | 150 · 8 · increase_memory 149, restrict_process_count 1 | 149 · 7 · increase_memory 148, do_nothing 1 |
| saturation | 120 · 7 · increase_memory 59, do_nothing 55, restrict_process_count 5, throttle_io 1 | 120 · 6 · increase_memory 61, increase_cpu 30, do_nothing 28, decrease_cpu 1 |
| decay | 120 · 5 · increase_cpu 59, do_nothing 58, restrict_process_count 3 | 120 · 3 · do_nothing 64, increase_cpu 56 |
| decay-off | 60 · 0 · do_nothing 60 | 60 · 1 · do_nothing 59, decrease_cpu 1 |
| tail | 180 · 0 · do_nothing 180 | 180 · 0 · do_nothing 180 |
| rise-fall | 119 · 5 · increase_cpu 74, do_nothing 44, restrict_process_count 1 | 121 · 6 · increase_cpu 73, do_nothing 45, decrease_cpu 1, restrict_process_count 1, alert_operator 1 |
| warmup | 5 · 0 · do_nothing 5 | 6 · 0 · do_nothing 6 |
| after-run | 11 · 0 · do_nothing 9, alert_operator 2 | 9 · 0 · do_nothing 8, alert_operator 1 |

### Give-back moments (idle / cut-to-idle / mem-release / decay / decay-off / tail)

**v1 (v2-2b)**: 5 applied writes land in give-back regimes, 2 of them lowering.
* 09:40:06 [decay] restrict_process_count: wlp-neighbor/pids.max 21->16 <- LOWER
* 09:40:12 [decay] increase_cpu: wlp-neighbor/cpu.max 100000->100000; wlp-neighbor/cpu.weight 10000->10000 <- RAISE
* 09:40:58 [decay] increase_cpu: wlp-neighbor/cpu.max 100000->100000; wlp-neighbor/cpu.weight 10000->10000 <- RAISE
* 09:41:44 [decay] increase_cpu: wlp-neighbor/cpu.max 100000->100000; wlp-neighbor/cpu.weight 10000->10000 <- RAISE
* 09:42:12 [decay] restrict_process_count: wlp-neighbor/pids.max 16->16 <- LOWER

**v2 (v3-2b)**: 5 applied writes land in give-back regimes, 2 of them lowering.
* 15:21:18 [cut-to-idle] decrease_cpu: wlp-neighbor/cpu.max 100000->60000; wlp-neighbor/cpu.weight 1600->800 <- LOWER
* 15:50:08 [decay] increase_cpu: wlp-neighbor/cpu.max 60000->90000; wlp-neighbor/cpu.weight 1600->3200 <- RAISE
* 15:50:54 [decay] increase_cpu: wlp-neighbor/cpu.max 90000->100000; wlp-neighbor/cpu.weight 3200->6400 <- RAISE
* 15:51:39 [decay] increase_cpu: wlp-neighbor/cpu.max 100000->100000; wlp-neighbor/cpu.weight 6400->10000 <- RAISE
* 15:54:25 [decay-off] decrease_cpu: wlp-neighbor/cpu.max 100000->60000; wlp-neighbor/cpu.weight 10000->5000 <- LOWER

Lowering actions applied anywhere: v1 11 (restrict_process_count, throttle_io), v2 6 (decrease_cpu, restrict_process_count).

### Anomalies

* v1: action do_nothing repeated 95 times in a row from 2026-10-17T08:57:54.925Z | action increase_cpu repeated 80 times in a row from 2026-10-17T09:01:11.040Z | action do_nothing repeated 97 times in a row from 2026-10-17T09:03:51.122Z | action increase_cpu repeated 87 times in a row from 2026-10-17T09:07:11.234Z | action do_nothing repeated 540 times in a row from 2026-10-17T09:10:05.341Z | action do_nothing repeated 85 times in a row from 2026-10-17T09:28:15.987Z | action increase_memory repeated 149 times in a row from 2026-10-17T09:31:08.075Z | action do_nothing repeated 27 times in a row from 2026-10-17T09:36:12.239Z | action increase_memory repeated 59 times in a row from 2026-10-17T09:37:08.273Z | action do_nothing repeated 25 times in a row from 2026-10-17T09:39:16.338Z | action increase_cpu repeated 59 times in a row from 2026-10-17T09:40:12.366Z | action do_nothing repeated 296 times in a row from 2026-10-17T09:42:14.442Z | action increase_cpu repeated 74 times in a row from 2026-10-17T09:52:08.810Z | action do_nothing repeated 44 times in a row from 2026-10-17T09:54:37.118Z | applied actions without an outcome row: 4
* v2: action do_nothing repeated 275 times in a row from 2026-10-18T15:08:41.651Z | action increase_cpu repeated 89 times in a row from 2026-10-18T15:17:45.151Z | action do_nothing repeated 20 times in a row from 2026-10-18T15:20:39.147Z | action do_nothing repeated 100 times in a row from 2026-10-18T15:21:20.516Z | action do_nothing repeated 508 times in a row from 2026-10-18T15:24:40.419Z | action increase_memory repeated 149 times in a row from 2026-10-18T15:41:13.624Z | action increase_cpu repeated 30 times in a row from 2026-10-18T15:46:05.130Z | action increase_memory repeated 60 times in a row from 2026-10-18T15:47:03.678Z | action do_nothing repeated 17 times in a row from 2026-10-18T15:49:00.784Z | action do_nothing repeated 16 times in a row from 2026-10-18T15:49:36.045Z | action increase_cpu repeated 56 times in a row from 2026-10-18T15:50:08.066Z | action do_nothing repeated 76 times in a row from 2026-10-18T15:51:56.879Z | action do_nothing repeated 223 times in a row from 2026-10-18T15:54:27.310Z | action increase_cpu repeated 73 times in a row from 2026-10-18T16:01:45.406Z | action do_nothing repeated 20 times in a row from 2026-10-18T16:04:08.613Z | action do_nothing repeated 24 times in a row from 2026-10-18T16:04:49.930Z | applied actions without an outcome row: 2


### Environment notes (comparison caveats)

* IO stressors wrote the same volume in both runs (v1 4.70 GB, v2 4.80 GB; io phase 7.0 vs 7.2 MB/s, burst 12.0 vs 12.3 MB/s), but system io PSI differed sharply (mean 27 vs 0.1 during io, 63 vs 1.4 during io-burst): host writeback absorbed the fsyncs in v2, so io-pressure reactions are not directly comparable. Neither model wrote anything during the io phases in either run.
* v2 wall clock ran ~3.7% slow vs monotonic (host-sleep slew): phase durations in the tables above are ~2% shorter than nominal. Monotonic run time was 3512.5 s vs v1 3512.6 s, so the scenarios are equivalent.
* Same scenario file (sha256-identical), same cooldown 45 s, same neighbor limits; only the serving model differs.
