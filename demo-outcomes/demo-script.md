# 2-minute demo script — M3 measured outcome

**Charts to have open:** `charts/01-allocation-envelopes.png`, `charts/02-victim-p95.png`, `charts/03-arm-b-actions.png`.
**One-line setup:** same 23-minute workload ran twice; arm A kept static limits, arm B added the M3 v3-2b controller.

---

### 0:00–0:18 — The problem

Static cgroup limits are set once. Our noisy neighbor gets two cores and 800 MB whether it is idle or saturating the box. That reservation is invisible waste — but cutting it carelessly hurts the latency-critical service next door. Can M3 reclaim live without moving victim latency?

### 0:18–0:40 — What we ran

One 23-minute scenario, 17 phases: moderate burn, a nine-process spike, cut to idle, a 720 MB memory hold and release, IO, a fork burst, mixed load, saturation, decay, and a long idle tail.

Both arms start at two cores, 800 MB high, 900 max. A is static; B adds v3-2b every two seconds behind the safety gate, with a 45-second cooldown.

### 0:40–1:10 — Chart 1: allocation

Gray is static: flat at two cores, 800 MB. Blue gives back to 1.2 cores at the cut-to-idle, then ends at 0.6 in the tail — a 70% tail cut. But memory goes the other way: 850, then 900 MB, and it never comes back. CPU allocation is down 37%; memory allocation is up 7.2%. Three give-backs, all CPU; zero memory give-backs.

### 1:10–1:30 — Chart 2: victim latency

This is the safety check. Overall victim p95 is 0.659 ms static versus 0.667 controlled — eight microseconds, 1.2%. The lines track through spike, memory hold, IO and fork. In mixed and decay, B is 0.2 to 0.3 ms worse. No latency win.

### 1:30–1:50 — Chart 3: what the controller did

694 decisions, 80% do-nothing. Thirteen writes applied, nine changed anything, three were give-backs. It never chose `decrease_memory`. Cost: three-tenths of a cent.

One `increase_cpu` on a 120% quota was capped to 100% — an actuator bug — so the CPU saving is an upper bound.

### 1:50–2:00 — Caveat

This host has 12 cores and 7.8 GB, so there is little contention for the victim to feel. It is a null result on latency and a mixed result on waste; the next tests need a constrained host, a fixed `increase_cpu` cap, and memory give-back in the policy.

---

**Likely questions**

- *Why did memory go up?* The controller raises `memory.high` when the neighbor approaches it, but never lowers it when the hold is released; the policy chose `decrease_memory` zero times.
- *Is the victim regression real?* Overall it is 8 µs, within noise for one run. The mixed/decay gap is consistent in direction but needs repetition.
- *Why is CPU down so much?* Partly genuine give-back at cut-to-idle and decay, partly a mislabeled cut at saturation caused by the one-CPU cap in `increase_cpu`.
