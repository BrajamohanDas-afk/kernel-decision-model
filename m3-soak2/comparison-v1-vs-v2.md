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

