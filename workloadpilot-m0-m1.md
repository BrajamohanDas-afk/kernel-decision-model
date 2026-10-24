# WorkloadPilot — project notes

*Current state, updated Oct 12, 2026. Supersedes the earlier M0/M1-only version of this file.*

---

## 1. What this is

**WorkloadPilot — a user-space decision layer over cgroup v2.** Instead of a human (or fixed thresholds) setting CPU/memory/IO/pid limits, a decision model observes workload telemetry and continuously chooses one of 12 safe, measurable actions. The kernel and cgroups remain the fast, deterministic enforcement layer.

**Core decision:** "Given this workload's current and historical behavior, what resource action should the system take now?"

**Action space (12 options):**
`do_nothing`, `increase_cpu`, `decrease_cpu`, `increase_memory`, `decrease_memory`, `throttle_io`, `restrict_process_count`, `protect_service`, `isolate_workload`, `restart_service`, `kill_process`, `alert_operator`

**Input signals:** CPU usage + throttling, memory pressure and events (OOM), I/O wait, PSI (pressure stall information), process count, latency, error rate, workload type, time of day, historical OOM/restart events.

**Pipeline:**
```
workloads → cgroup v2 → telemetry collector → decision model → safety layer (rules + human approval for destructive actions) → cgroup actuator (cpu.max, memory.high/max, io.max, pids.max) → outcome log → retrain
```

---

## 2. Kernel-ML research verdict (what was established this session)

**"ML replaces the kernel" — dead as stated.** No production OS anywhere runs a learned scheduler; everything shipping (Meta scx_layered on 1M+ machines, Meta ads fleet, Google ghOSt) is hand-written policy on infrastructure *built* for custom policy.

### The 7 blockers, with what exists today and the verdict

| # | Blocker | What exists now | Verdict |
|---|---|---|---|
| 1 | Inference latency (µs vs ms) | Integer/fixed-point tiny nets in eBPF: 0.53 µs/inference BNN (measured), ~3–5 µs MLP (estimated), NN load-balancer sched_ext policy | Tiny quantized nets only; real models in hot paths: **dead** |
| 2 | Predictability / distribution shift | Deterministic integer inference; sched_ext watchdog reverts on error/stall; conformal prediction impractical on OS workloads (exchangeability fails) | System-level safety only; model-quality guarantees: **dead** |
| 3 | Safety / catastrophic mistakes | Verified nets only at ~10⁴ params (α,β-CROWN); shield/Simplex fallback pattern | Only tiny verifiable policy + envelope; bigger: **dead** |
| 4 | Debuggability | Rule extraction to decision trees (VIPER); sched_ext debug dumps, tracepoints, event counters | Only if the deployed artifact is a tree/rules; deep nets: **dead** |
| 5 | Kernel programming reality | Documented workarounds for everything: no FP → int32 fixed-point; 512B stack → tail calls + per-CPU maps; no dynamic alloc → BPF maps | **Keep.** Locked constraints: integer, tiny, bounded |
| 6 | Model lifecycle | Weights in BPF maps, hot-swapped from userspace; sched_ext load/unload at runtime; IBM's Feb 2026 RFC formalizes kernel-proxy + userspace-training split | **Solved** — model was never in the kernel binary |
| 7 | Attack surface | Verifier bounds memory + termination + instruction count; watchdog ejects stalls; poisoning defenses research-grade | **Keep with bounded blast radius**; adversary-proof judgment: **dead** |

### The mended shape (what actually survives)

Three tiers, in order of proven maturity:
1. **Slow loop (this project's home):** full-size decision model in userspace, seconds-to-minutes decisions. No kernel problem exists here at all.
2. **Fast loop (future, optional):** tiny distilled student (fixed-point MLP or decision tree) as a sandboxed, ejectable BPF program; trained offline, weights hot-swappable; auto-ejects to classical policy on failure. Needs kernel 6.12+ (sched_ext).
3. **Policy authorship:** LLMs write kernel policies offline (sched-agent pattern), never on the critical path.

### Key sources
- sched_ext (mainline 6.12, ejection guarantee): https://docs.kernel.org/scheduler/sched-ext.html
- IBM in-kernel ML library RFC, Feb 2026: https://lwn.net/Articles/1057568
- In-kernel quantized NN: https://arxiv.org/abs/2605.10070 , https://github.com/usernameisveryok/sage-ebpf-ml
- Verified NN controllers: https://github.com/Verified-Intelligence/alpha-beta-CROWN ; shields: https://cacm.acm.org/research/shields-for-safe-reinforcement-learning
- AI-for-OS survey: https://arxiv.org/abs/2407.14567

---

## 3. Why the platform is the decision-model platform

- The core decision maps 1:1 to an the platform `choice` question: one state (telemetry JSON), 12 named options, one probability per option.
- Probabilities → the safety gate: auto-act above a confidence threshold, fall back to rules / alert operator below it. the platform's **selective accuracy** metric is exactly "if we auto-decide X% of ticks, how accurate is that."
- Data engine is self-contained: run scenarios in the lab, log a rules teacher's decisions + outcomes; no external datasets needed.
- Cost: `decider-2b` at $0.007/M tokens for serving; fine-tunes are a few dollars of GPU. The $100 credit is plenty.
- Distill recipe: rules teacher labels the states; the model learns to generalize beyond the rule table.

---

## 4. Lab environment

Requirements: Linux with cgroup v2, PSI, cpu/io/memory/pids controllers, root, ability to run disposable stress workloads, and full control to break things.

**This machine:** Windows 11 Home (→ **no Hyper-V**), 12 cores, 15.7 GB RAM, 67.6 GB free disk, Docker Desktop installed (daemon off), ssh client present, no cloud CLIs or OCI config.

**Verified probe (current WSL Ubuntu-24.04, for reference):** cgroup v2 mounted, PSI live, controllers available (cpuset cpu io memory hugetlb pids rdma), subtree control cpu+memory+pids (need `+io`), systemd running, Python 3.12.3, kernel 6.6 (no sched_ext — fine, not needed for v0).

**Lab options (decision pending):**
| Option | Pros | Cons | Needs |
|---|---|---|---|
| **A. Cloud VM (Oracle Always Free)** | Truly off-laptop; 4-core/24GB ARM; realistic kernel; provider-level snapshots | 15 min of console setup; ARM image differences | Oracle account; SSH public key added to instance |
| **B. Dedicated WSL distro** | Zero setup (~10 min), fully isolated from daily WSL, I control everything | Runs on user's hardware; WSL kernel quirks | Nothing |
| **C. VirtualBox VM** | True local VM, own kernel | ~1h setup, 3GB download, 4GB RAM + 30GB disk while running | Install VirtualBox + ISO |

**DECIDED (Oct 15): the lab is `wlp-lab`** — a dedicated, disposable WSL2 Ubuntu 24.04 sandbox on the Windows PC. Isolated distro (delete anytime with `wsl --unregister wlp-lab`), default user root, systemd on, Windows interop disabled, C: still mounted for file staging. Verified: cgroup v2 (cpuset/cpu/io/memory/hugetlb/pids/rdma), PSI live, Python 3.12.3, 12 CPUs, 7.8 GB RAM visible. Access from PowerShell: `wsl -d wlp-lab -- bash -c '...'`. Two quirks: `$`-variables and backslash escapes can be eaten in the wsl argument path → keep nontrivial content in files and copy them with `wlp-copy.py` (staging dir: `C:\Users\Braju\AppData\Local\Temp\opencode\wlp-staging`).

**Oracle (parked):** `my-server` (E2.1.Micro, Mumbai) went wedged at the SSH-banner level after the PSI-enable reboot; abandoned — 1 GB is too small anyway. If cloud is ever wanted: target the free **A1 ARM** (4 cores / 24 GB), or revive the micro via a console force-reboot.

---

## 5. Milestone 0 — Measurement rig

**Goal:** prove we can observe decision-relevant states. The log produced here *defines the state schema* that goes to the platform.
**Deliverable:** one JSONL where each stress phase visibly moves the signals.
**Target environment:** the chosen lab VM (§4).

Steps:
1. Project dir `~/workloadpilot` (native FS, not `/mnt/c`-style mounts).
2. Enable io delegation (root): `echo "+io" > /sys/fs/cgroup/cgroup.subtree_control`
3. Scenario — two cgroups via `systemd-run` (or containers later):
   - **critical service** — light, latency-sensitive loop recording its own per-iteration delay
   - **noisy neighbor** — phases: CPU hog → memory hog → I/O flood, with real limits (`CPUQuota`, `MemoryMax`, `IOWeight`)
4. Sampler (Python), every 2 s, per cgroup:
   - `cpu.stat` (usage_usec, throttled_usec), `cpu.max`, `cpu.weight`
   - `memory.current`, `memory.high`, `memory.max`, `memory.events` (oom/oom_kill), key `memory.stat` rows
   - `io.stat`, `io.max`/`io.weight`
   - `pids.current`
   - all `/proc/pressure/{cpu,memory,io}` lines
   → one JSON row per tick, appended to JSONL
5. Run 5–10 min; inspect which signals separate *idle / busy / throttled / pressured*.

**STATUS (Oct 15): BUILT + RAN.** Lab files: `/root/workloadpilot/{scenario.sh, critical_app.py, neighbor_app.py, sampler.py, analyze.py}` — built by 3 parallel agents, staging copies in `wlp-staging\`. Full 6.7-min scenario executed: 5 phases, **214 telemetry rows** (2 s interval), **19,523 latency samples**.

**Result — signals confirmed:**

| Phase | Key evidence |
|---|---|
| baseline | quiet; neighbor absent; PSI ≈ 0 |
| cpu_load | neighbor **throttled 215.8 s** (nr_throttled 861); system cpu PSI avg10 **66 %**; critical-app latency unchanged (p95 0.68 ms) |
| mem_load | neighbor memory.current **199.7 MB** (High 200 / Max 250); `memory.events.high` **+613** |
| io_load | neighbor **wbytes +242 MB** at ~2.8 MB/s; io PSI max 0.55 |
| recovery | all signals return to baseline |

**Interpretation:** on the big lab (12 CPUs) the *innocent app does not slow down*, but the **cgroup/PSI-level signals of the bad neighbor are loud and clean** — exactly the inputs the decision model needs. The analyzer's default thresholds were tuned for the tiny Oracle box ("critical p95 must be 1.5×") — for M1 use throttling / memory.events / PSI as primary signals and latency only when resources are genuinely tight.

**Open calibration items:** (1) during the memory phase the neighbor's `io_stat.wbytes` jumped ~201 MB in one step with no real file writes — suspected WSL io-accounting artifact under reclaim; don't trust wbytes for non-I/O phases, re-check in M1. (2) Baseline "WEAK" verdict was io-PSI noise (0.56 vs 0.5 threshold). (3) Analyzer ignores per-cgroup PSI in its mem/io verdicts — consider adding.

**Success =** phases distinguishable in the log, and a shortlist of features that move (draft `state` JSON for the platform). → **ACHIEVED** (see results).
**Dependencies:** none beyond the lab. Zero-cost, no ML.

---

## 6. Milestone 1 — Rules teacher + labeled rows

**Goal:** a deterministic heuristic policy that acts on M0 states and logs labeled rows. It is both (a) the baseline the learned model must beat, and (b) the label source (teacher) for training.

Steps:
1. Rule table v0 — state conditions → 1 of 12 actions, e.g.:
   - CPU throttling rising + critical-service latency up → `increase_cpu`
   - `memory.current` approaching `memory.high` → `increase_memory`; at `memory.max` → `alert_operator`
   - neighbor `io.stat` dominating → `throttle_io`
   - `pids.current` spike → `restrict_process_count`
   - idle for N minutes → `decrease_cpu` / `decrease_memory`
   - abnormal/unknown → `alert_operator`
2. Apply actions via cgroup v2 writes (or systemd-run properties), behind a safety envelope:
   - auto-allowlist only for safe actions
   - `restart_service`, `kill_process` → operator approval, never automatic
3. Log per tick: state snapshot → chosen action → measured effect 30–60 s later (pressure / throttling / latency / OOM deltas).
4. Produce train/heldout rows in the platform format: `choice` question "action" with the 12 options; hard label = teacher action (soft labels later).

**STATUS (Oct 15): BUILT + RUN.** Files: `/root/workloadpilot/{rules.py, actuator.py, build_dataset.py}` (built by 3 parallel agents) + `teacher_loop.py` (glue, orchestrator). Two full runs executed with the teacher live (~7 min each, 202 decisions each). v2 applied actions: increase_cpu ×2 (quota 50k→75k→100k), increase_memory ×1 (high 200M→250M), throttle_io ×2 via **io.max fallback** (the WSL kernel exposes no `io.weight` — see findings). Dataset produced: **decision_train.jsonl (162 rows) + decision_heldout.jsonl (40 rows)** + outcomes.jsonl (per decision: deltas 90 s later — throttling, memory events, wbytes, PSI endpoints). Backups: `wlp-staging\results\m1-v1\` and `m1-v2\`.

**Findings worth keeping:** (1) kernel has no `io.weight` → actuator throttles via `io.max` wbps cap. **Device bug found & fixed:** the v2 cap targeted `8:32` — which is the **SWAP device** (the "busiest wbytes" heuristic guessed wrong) — instead of `8:48` = root fs where the writer lives, so the cap never touched the writes. The actuator now caps the **root-filesystem device** (`os.stat("/")` → major:minor), with the busiest-device heuristic only as fallback. (2) Shortly after the cap, the neighbor's io PSI spiked 0.5 → **15.4** — the wait-time cost of throttling is exactly the trade-off data the decision model should learn. (3) Aggregate wbytes stayed ~2.8 MB/s after the cap (wrong device + WSL virtual storage only partially honors io.max; same family as the M0 wbytes quirk) — on real hardware `io.max` is kernel-enforced. Trust PSI over wbytes on this kernel. (4) 60 s cooldown works: repeated same-action decisions are logged as cooldown refusals, not re-applied. (5) This kernel's devices: `8:32`=swap (`sdc`), `8:48`=root fs (`sdd`).

**Success =** a few hundred labeled rows from several scenario runs + a replay check showing actions that measurably reduced pressure (or correctly did nothing). → **ACHIEVED** (202 labeled decisions/run; dataset built).

---

## 7. Status and open decisions

**Done:** idea + boundary (kernel = enforcement, model = userspace); kernel-ML deep research with per-blocker verdicts (§2); the platform fit established (§3); lab built (`wlp-lab`, §4); **M0 built and run — signals confirmed (§5)**; **M1 built and run — rules teacher + actuator + the platform-format dataset (§6)**; agent-bridge context `workloadpilot` holds 4 artifacts + memory keys.

**Open:**
1. **Project purpose (a research proof / b real tool / c product story)** — doesn't block M2; shapes M3 polish.
2. Optional: merge v1+v2 datasets before training (more rows), or keep v2 only (cleaner).

**M2 status (Oct 16):** dataset-v2 done (60 runs, 4,888/1,640 rows, run-level splits). Trained: v1 pilot (77.5%→90%, small exam); **v2-2b: 70.4% → 87.5%** on the hard run-level exam. One run mislabeled `v2-4b` was actually another 2b (base-model arg missing — fixed + guarded); it doubles as a noise measurement: run-to-run variance ≈ 0.7 pts.

**the platform team/the platform feedback (Oct 16, incorporated):** (1) the 27-min GPU wait was a platform bug (fixed; starts ~30s now). (2) v2-2b is decently calibrated: ≥0.9 confidence → 94% correct; 0.6–0.8 band ~85% (slightly cautious). (3) Zero-example classes score ~0 — expected with hard labels → use **soft targets** (0.9 on label, 0.1 spread). (4) Stronger weights: **inverse class frequency capped 10×** so rare classes actually get predicted.

**Recipe v3 (in `train_v2.py`, verified offline):** `--weight-mode inverse --class-weight-cap 10 --soften` (+ `--train-readout` for pplx). Weights now: do_nothing 1.0 · increase_cpu 6.16 · increase_memory 5.86 · everything rare 10.0.

**Plan B — DONE (Oct 16→17):** All three models on the hard run-level exam: **v2-2b 87.5%** (ECE 0.113) · **v2-4b-r2 87.6%** (ECE **0.0812**, recipe v3) · **v3-pplx+readout 87.3%** (ECE 0.143). **Dead heat within run noise → model size/model choice is irrelevant at this data scale; `decider-2b` is the economics pick (3× cheaper to serve).** Mid-run probes (new, first live use) show the same four classes — `decrease_cpu`, `decrease_memory`, `protect_service`, `throttle_io` — at ~0 recall from epoch 1 in EVERY model → **proven data-bound; weights/soft-targets cannot fix 44–73 examples. Next: batch 2 with targeted scenarios** (limit-hitting mem_grow, throttle-heavy io, pid-spike, idle-after-load — ≈ +3k rows, ~2h). Reports: `m2-pilot\results\EVAL-REPORT-{v2-2b,v2-4b-r2,v3-pplx}.html`. the platform team package: drafted.

**Portable friend-bundle READY (Oct 17):** `bundle\wlp-lab-bundle.tar.gz` (121 KB) — inside: `check_machine.sh` (8-point preflight), `collect.sh` (24 runs, ~2 h, auto-packs `wlp-results.tar.gz`), README, paste-ready message for the friend, sample run. **Tested end-to-end in the lab**: extracted the real tar → check passed 8/8 → 1 quick run produced valid telemetry/decisions → results tarball created → 0 leftover units. Friend's runs feed dataset v3+ alongside batch 2.

**Tracks A+B launched (Oct 17):** two parallel agents building: (A) batch-2 targeted scenarios — dead-class triggers extracted from rules.py (`MEMORY_RELEASE_RATIO = 0.50` memory.high ≥90% drop → decrease_memory; cpu pressure released → decrease_cpu; `fast_writes_throttle_io` → throttle_io; `protect_service_when_critical_pressured` → protect_service) → targeted recipes in scenario_gen.py (backward-compatible) → 3-run pilot gate (each dead class ≥6 hits across pilots, ≥2/3 runs) → ready-to-fire ~35-run batch into `dsv2/runs-batch2/` (seeds 3000+, pilot dir excluded from datasets); (B) M3 closed-loop controller in `/root/workloadpilot/m3/` — telemetry → the platform model (default v2-2b) → safety gate (12-action whitelist, param clamps, cooldown, wlp-* units only) → actuator → m3_decisions/m3_outcomes logs; verification = feature parity vs featurize.py + gate self-check + 1 dry-run API call. Dataset build script staged at `/root/workloadpilot/dsv2/build_dsv3.sh` (dsv3 = 60 batch-1 runs + batch-2 runs, run-level split, combined). Next: M3 live test (short), batch-2 launch (user GO), dsv3 → retrain (money + model choice gate).

**Serving-meter finding (Oct 17):** `client.predict()` = batch server-side *evaluation* (async job; billed as decide tokens — visible in the usage API) but it does NOT feed the project page's live meters. Live serving = `system_one` (POST /v1/systemone, per-request, returns `usage.input_tokens`; feeds DECISIONS / TOKENS IN / MEDIAN LATENCY). `demo_serve.py` rewritten to the live path; 5 live decisions sent Oct 17 (v2-2b, do_nothing ×5). **M3 must call `system_one` per telemetry row** (org rate limit 60/min; 1 per 2 s = 30/min OK). Spend from usage API (14 d, project workloadpilot): train $12.45 (v1 $0.33, v2-2b $1.47, v2-4b-r2 $1.61, v3-pplx $9.04) + decisions/evals ≈ $0.154 → ≈ $87.4 of $100 left.

**M3 built + hardened (Oct 17):** `/root/workloadpilot/m3/`: `live_controller.py` (row → featurize reuse → `system_one` live decision → gate → actuator when `--live` → m3_decisions.jsonl + 3-sample m3_outcomes.jsonl), `gate.py` (12-action allow-list, human-approval trio blocked, wlp-* only, cooldown, clamped writes; dry-run default ON), `check_feature_parity.py` (91+92 rows byte-identical across two runs), `check_gate.py` (86 assertions), `live_test.sh` (staged key read+deleted), README. Built on `predict` first (same wrong-door bug as the demo) → switched to `system_one`; verified live: memory-pressured row → increase_memory (p=0.816) gate-pass against a running wlp-neighbor; quiet row → do_nothing (p=0.999); smoke logs `usage_in_tokens`. **KEY INCIDENT:** M3 agent printed the API key once in its session (transited model-provider servers) → user rotating: the platform UI → API keys → new + revoke old; then `setx PLATFORM_API_KEY "..."` locally (scripts read the User env var; nothing else changes). Next: M3 live test (--live, 1 scenario, with Track A idle) → serving meters fill; then batch 2 (user GO).

**Batch-2 targets VERIFIED (Oct 17):** rules.py triggers extracted; decrease_memory / throttle_io / protect_service made reachable via minimal backward-compatible schema adds (`mem_pulse` phase type; per-phase `io_cap_mbps` re-raise + `victim_cpu_quota_pct`; stressor `mem_grow` "pulse" pattern) — pilots (runs-targeted-pilot, seeds 2100-2105): decrease_memory 35 rows 6/6 runs, throttle_io 57 rows 5/6, protect_service 138 rows 6/6 (caveat: these rows are labeler-"harmful" → training weight 0.2). Default-mode generation byte-identical (regression OK, rules selftest OK). **decrease_cpu proven structurally UNREACHABLE at 2 s cadence:** the rule needs unit psi avg10 ≥30→≤2 between consecutive rows; 10 s-EMA decay permits only ≥0.819×/step → impossible (0 of 1347 chances in batch-1 data). Only fix = rule-contract change (windowed lookback: "busy within last ~30 s, quiet now") + full relabel; PENDING USER DECISION. Batch-2 command prepared (35 runs = 25 targeted + 10 default, seeds 3000-3034, ≈2 h 15 m) in `dsv2/wlp-run-batch2.sh` — awaiting GO. M3 live test fired Oct 17 (default-mode scenario seed 3100, --live, v2-2b, cooldown 45).

**M3 live test PASS (Oct 17, seed 3100, default recipe, full scale):** runner controller disabled (`--controller-mode none` supported); M3 `--live` was the sole cgroup writer; 137 decisions / 138 telemetry rows (1:1); gate: 84 pass-no-write (82 do_nothing, 2 alert_operator), **5 applied**, 48 rejected (all cooldown — 47× repeated increase_memory), 0 model errors, 5/5 outcome windows; **90,064 live tokens** (~$0.0006); pacing 30.2 decisions/min (fits the 2 s cadence, no backlog). Applied writes independently observed by the sampler: memory.high 903→953→903→953→974 MiB (last capped at memory.max exactly as the gate predicted); pids.max 109→54. Cleanup clean (no wlp-* units left). Observations: v2-2b was memory-biased for this recipe (50× increase_memory, cooldown absorbed it; one increase/decrease oscillation); no cpu/io actions (seed-3100 recipe is memory-heavy + fork_light). Artifacts: `m3/live/` + `m3/live_analyze.py`.

**M3 Test Tour v1 launched (Oct 17):** 5 full-scale default-mode live runs — 4 physics families (cpu / io / memory / mixed+fork; seeds from 4000-4199) + a v2-4b-r2 A/B repeat of the most-active family; per-run artifacts in `m3/tour/`, analysis via `m3/tour_analyze.py`, user-facing copies to `m3-tour\` (summary.md/json + decisions/outcomes). Still awaiting user: GO fix/skip (decrease_cpu rule + batch 2); key rotation.

**M3 Soak v1 armed (Oct 17):** fresh box `wlp-soak` (clone of lab after the tour's ready-marker — tour's 5 runs already done: 4 families + 4b A/B); 55-60 min hand-made free-form load timeline (idle→cpu spikes→cut→mem-limit→io bursts→forks→saturation→staged decay; no seed recipes); rehearsal at 0.1× then full soak with M3 `--live` (v2-2b, cooldown 45); soak toolset staged at `m3/soak-prep/`; analysis + user-facing package → `m3-soak\` (summary.md/json + decisions/outcomes + optional charts).

**M3 Test Tour v1 RESULTS (Oct 17):** 5 runs (4029-cpu, 4035-io, 4010-mem, 4011-mixed, 4011-mixed-4b), 649 decisions, 411,795 tokens ≈ $0.0032, 0 model errors, pacing 30.2/min all runs, clean units after each. Action mix: do_nothing 482, increase_memory 146, alert_operator 10, restrict_process_count 9, decrease_memory 1, throttle_io 1 (6/12 exercised; increase_cpu/protect_service/isolate/restart/kill never chosen — non-pressuring draws + WSL io limits). **A/B verdict: v2-2b vs v2-4b-r2 = 138/139 (99%) identical actions on the same scenario → serving default stays v2-2b** (big model buys nothing live on this distribution). Findings: (1) cpu seed 4029 drew 300% quota → zero pressure → zero writes (correct; quota ≤100% needed for real CPU pressure); (2) increase_memory churn: 146 asks / 141 cooldown-blocked → future feature idea: "seconds since last applied action" in the feature set; (3) no-op "applied" write when already at memory.max (memory.high == memory.max) → mark applied_noop (M3 polish item); (4) gate cleanly rejected an unperformable throttle_io (WSL cgroup lacks io.weight/io.stat). Files: `m3-tour\` (summary.md 230 lines + summary.json + 5× per-run decisions/outcomes JSONL).

**M3 Soak v1 RESULTS (Oct 17):** fresh box `wlp-soak` — `wsl --clone` unsupported (WSL 2.6.3) → export/import (1.92 GB tar); verify OK (cgroup v2 + PSI + systemd, 12 CPU / 7.8 GB). WSL gotcha: a distro shuts down when the last `wsl.exe` client disconnects — keep an attached client for nohup'd long runs. 58.5 min hand-made arc (19 phases). Rehearsal 0.1× clean (175 dec). **Soak: 1755 decisions @ 30/min, 0 errors, 1,148,451 tokens ≈ $0.008; gate 1229 pass-no-write / 36 applied / 490 cooldown; controller never died; clean stop.** Behavior: cpu regimes → increase_cpu (15 applied, cpu.max 50k→75k→100k cap + weight ladder 100→10000); fork → restrict; saturation → increase_memory + restrict + 1 throttle_io (io.max wbps=1 MiB/s fallback — WSL lacks io.weight); quiet/cut/release/tail → 420× do_nothing with **zero give-back writes**. **GIVE-BACK GAP PROVEN LIVE:** never chose decrease_cpu/decrease_memory; kept asking raises after ceilings (no-op applies); only real gives = pids.max trims (→16). Anomalies: 4 applied actions lost outcome rows (single pending slot overwritten by rapid applies — M3 polish backlog); long streaks (do_nothing ×540). Deliverables `m3-soak\`: summary.md/json, m3_decisions.jsonl (1755), m3_outcomes.jsonl (32), rehearsal-summary.md, charts/actions.png + signals.png. Box left idle at `wlp-soak`.

**Friend bundle incident (Oct 17):** his VM (Arch, ~3.9 GB RAM, nested VM): seed=1 rules OK every time (217 s); **seed=2 explore = the hang** (run_batch `status=failed:timeout`: 1024 s / 2425 s attempts), guest kernel soft-lockups (systemd-coredump stuck 1865 s, swapper stuck 476 s), VM needed a hard close once; ballooning durations = timeouts/retries + host degradation, not real work. He completed one 3-run attempt → `wlp-results.tar.gz` (192 KB, contains the 2 failed runs' logs) — must be copied aside before any rerun (collect.sh overwrites it). **Repro launched in `wlp-soak`:** as-shipped bundle, seed=2 explore solo, `timeout 1500`. Suspects: explore-mode random actuator writes → stressor crash → coredump storm + memory thrash on a small-RAM VM; plus untested seed range (ours used 2000+, bundle starts at seed 1). Fix list for bundle v2: coredump dampening (`ulimit -c 0`), timestamped result archives, default start-seed 2000+ (or root-cause fix), possibly rules-only default mode, check_machine CPU/RAM warnings.

**Repro result (Oct 17):** seed-2 explore in `wlp-soak` = **CLEAN** (status ok, 109 rows, 219 s) → his failure is his resource envelope (3.9 GB Arch VM + slow virtual disk + spike-pattern 905 MB memory target; kernel soft-locks + a coredump writing while under pressure), NOT a scenario/code bug. **Bundle v2 building now:** `ulimit -c 0`; RAM-scaled memory draws (`--mem-scale` = clamp(RAM/8000, 0.4, 1.0); his box ≈ 0.49); 60 s settle pause after failed runs; timestamped result archives (`wlp-results-YYYYMMDD-HHMM.tar.gz`, never overwrite); `--start-seed 2000`; check_machine CPU-count + RAM guidance; v2 tested in `wlp-soak` incl. byte-identical default-scale regression. Deliverable: `bundle\wlp-lab-bundle-v2.tar.gz`. Friend asked: send `wlp-results.tar.gz` (copy aside first) + bump VM to 6 GB+/4 vCPU if easy.

**Bundle v2 GREEN LIGHT (Oct 17):** QA all green — v1≡v2 byte-identical scenarios at scale 1.0; scaling floors/ratios + `--mem-scale 0` rejected; smoke 2 runs ok (2000 rules 194.3 s/97 rows; 2001 explore 280.9 s/140 rows) + timestamped archive created; pause test = exactly 60 s after `failed:exit-1` (same branch covers `failed:timeout`); hash parity 19/19 files; simulated friend box (scale 0.49) run = ok, 194.4 s. Ship `bundle\wlp-lab-bundle-v2.tar.gz` + updated SEND-THIS-MESSAGE.txt; friend returns newest `wlp-results-YYYYMMDD-HHMM.tar.gz` (+ old v1 archive for diagnosis if available).

**GO FIX received (Oct 17) — chain running:** (1) fix cycle (Track A agent, bg): windowed decrease_cpu rule (`CPU_RELEASE_LOOKBACK_S` ≈ 30 s) in rules.py + history reset for replay + selftest/fuzz update + relabel all 60 runs (expected delta: quiet→decrease_cpu only) + one live targeted pilot (seed 2106) proving live firing + replay parity; (2) coordinator launches batch 2 (35 runs, ~2h15, seeds 3000-3034) via attached-client background shell; (3) dsv3 build (featurize+labeler fresh, new rules); (4) the platform retrain decider-2b (~$1-2, live-watch — confirm with user before firing); (5) exam vs v2-2b → then M3 swaps to the new model. Friend kit stays v2 (labels are computed offline at build time; no resend needed).

**FIX COMPLETE + BATCH 2 LAUNCHED (Oct 17):** rules.py windowed release (`CPU_RELEASE_LOOKBACK_S = 35 s`, one fire per busy episode (window consumed), `reset_release_history()` for multi-run replay; controller gets +1 reset line). Replay delta over 60 runs: exactly do_nothing→decrease_cpu ×21; relabel applied 20 rule rows (+1 exploration row intentionally kept) → `decrease_cpu` 82 total = 62 exploration + 20 rules (was 62/0). **Labeler insight: the labeler COPIES decisions.jsonl actions (does not re-run rules) → friend runs will need the replay/relabel step at build time.** Live pilot (seed 2106 + release pad): LIVE decrease_cpu ×2 applied (neighbor cpu.max 100k→60k, weight 25→12; critical 400→200), replay parity 0/141 mismatches, clean stop. Recipe gap found + fixed: v3 targeted ended pinned (0 fires) → scenario_gen patched to append a release pad (io_write 1 MB/s, victim quota 100%, 43-55 s via fit) — verified on seed 3000 (280 s, 6 phases). **Batch 2 RUNNING (~2.5 h): 25 targeted (seeds 3000-3024, padded) + 10 default (3025-3034) → `runs-batch2`, attached-client shell.** Next: dsv3 build → retrain (confirm + live-watch).

**Batch-2 status + infra hiccup (Oct 17):** 12/35 runs done (seeds 3000-3011), **all `ok`**, durations 260-299 s — and **`decrease_cpu` appears in every completed run's decisions.jsonl** (the release pad + fixed rule are working in production). The first launcher died mid-seed-3012 when the harness background shell was clobbered (same agent-server infra blip that killed the tour's run E earlier; no run failure). Rebuilt the launcher as idempotent `dsv2/batch2_resume.sh` (finds the first seed without an OK index row, deletes that seed's partial dir, runs targeted 3012→3024 then default 3025→3034) + `b2_launch.sh` (setsid+nohup detached, attached watcher for notification). Resume launched; remaining ≈ 23 runs ≈ 1 h 45 m. Re-run `bash batch2_resume.sh` any time to recover from a future interruption.

**BATCH 2 COMPLETE + dsv3 BUILT + UPLOADED (Oct 18):** 35/35 runs `ok` (seeds 3000-3034, zero failures; the detached launcher survived the server restart). dsv3 = batch-1 (relabeled with fixed rules) + batch-2 → `dsv2/dsv3/`: **train 8,230 rows / heldout 2,640**. Teacher output for the four ex-dead classes, old 60-run data → dsv3_train: **decrease_cpu 0 → 95**, **decrease_memory 17 → 152**, **throttle_io 30 → 437**, **protect_service 0 → 488** (watch protect for over-prediction; class weights dampen). Other train counts: do_nothing 5280, increase_memory 1013, increase_cpu 616, restrict 77, alert 72. Copied to `results\dsv3\` (13.6 + 4.4 MB); uploaded to the platform as `dsv3_train` / `dsv3_heldout` via `m2-pilot\upload_dsv3.py`. **Retrain staged:** `train_v2.py --base decider-2b --model-name v3-2b --train results\dsv3\dsv3_train.jsonl --heldout results\dsv3\dsv3_heldout.jsonl --ds-train dsv3_train --ds-held dsv3_heldout --weight-mode inverse --class-weight-cap 10 --soften --train-readout` + live dashboard http://localhost:8765 (m2-pilot\dashboard.py, default live dir). **Awaiting user GO (money + live watch)**; model name v3-2b suggested.

**v3-2b TRAINED + SWAPPED + friend data folded (Oct 18):** training arc: 2 failed attempts (`--train-readout` is pplx-only → 422; Windows file-lock race on status.json → `flush()` now retries 50×50 ms + dashboard `read_retry`; crashed runs auto-closed by SDK heartbeat, billing stopped) then success. **Exam (dsv3_heldout, 2640): acc 88.37%, macro-F1 0.663 (old ≈0.40–0.42), balanced 0.639, ECE 0.0475 (best; v2-2b 0.113); ALL FOUR ex-dead classes alive: decrease_cpu 0.268 (11/41, predicted 12), decrease_memory 0.475, throttle_io 0.610, protect_service 0.752; alert 0.821; increase_cpu/memory 0.91–0.93; do_nothing 0.955. Straggler: restrict_process_count 0.031.** Report `m2-pilot\results\EVAL-REPORT-v3-2b.html`. **M3 swap:** controller default `--model v3-2b` (+README). 3 live A/Bs vs v2-2b: memory/fork equal; mixed (4011) v3 loses pids trims (restrict regression); io (4035) both correctly no-op (default physics lacks io pressure). Keep v3-2b; **dsv4 list: restrict boost + release-window features + io-pressure scenario variant.** Artifacts `m3/live-v3/`, `live-v3-mixed/`, `live-v3-io/`; compare scripts `m3/m3_compare{,2,_io}.py`. **Friend delivery:** `wlp-results-20261018-1938.tar.gz` → 24/24 runs ok (durations identical to ours; paired cross-hardware data), extracted to `results\friend-20261018\`, folded to `dsv2/runs-friend/`, relabeled with the fixed teacher (+1 rules decrease_cpu), featurized/labeled → ready for dsv4 (~2,300 rows).

**M3 Soak v2 = DONE (Oct 18, v3-2b vs v2-2b, same 58.5-min arc):** box `wlp-soak2` (export/import → v3-2b default). 1754 decisions @ 30.7/min, 1,145,877 tokens ≈ $0.008, 0 model errors, gate 1289 pass / 30 applied / 435 cooldown, 28 outcome rows, 19/19 phases, clean stop. **GIVE-BACK ACHIEVED: `decrease_cpu` 4 chosen / 4 applied (v1: 0) — real lowerings at cut-to-idle (cpu.max 100k→60k, weight 1600→800) and decay-off (100k→60k, 10000→5000).** Trade-offs: restrict_process_count 17/10 → 2/2 (known regression), throttle_io 1→0 (environment: io PSI absorbed by host writeback — not comparable), increase_cpu 300/15 → 248/13, do_nothing 1227→1287 (more conservative). decrease_memory/protect_service 0 in both (arc lacks their trigger states). 2 applied actions lost outcome rows. Usage API verified: 15:00 bucket 1,143,189 + 16:00 118,337 = 1.26M session tokens ($0.0088). Files `m3-soak2\`: summary.md, comparison-v1-vs-v2.md, charts, decisions/outcomes JSONL. Next: dsv4 list (restrict boost + release-window features + io-pressure variant).

**Jev benchmark (Oct 18):** read the TypeSafe blog (System One models + Jev, Sep 15 2026 — typed probabilistic decisions, parallel sampling, 70–500 ms, $0.042/MTok, RLCD-calibrated, "can't hallucinate"/type-safe, early access). the platform's catalog contains jev-family bases (`jev-27b` AutoTrust, `jev-9b`, `jevk5-9b/4b`, `jevfire-27b`, `jev-omni-12b`, `simple-jev-27b`, plus `clef-27b` Cloudflare, `reflex-27b`, decider-2b/4b, pplx-decider). **Measured zero-shot on dsv3_heldout: `jev-27b` = 37.46% acc, macro-F1 0.147, ECE 0.359 — collapsed (5 classes never predicted; over-predicts increase_cpu 845/226 support, throttle_io 949/123).** vs decider-2b base 67.73% (ECE 0.117) vs our fine-tune v3-2b 88.37% / 0.663 / 0.0475. Caveat: catalog jev-27b is AutoTrust's JEV-27B under `autotrust-bare-v1`, NOT TypeSafe's hosted Jev (early access); zero-shot vs fine-tuned is asymmetric. Offers: catalog sweep ≈ $0.40; fine-tune jev-27b on dsv3 ≈ $6 for fair base-vs-base. Artifacts: `results\EVAL-REPORT-jev-27b.html`, `results/jev-27b-tuned.{json,_rows.jsonl}`.

**Decision-model market context (Oct 18 research):** the category is exploding — Jev launched Sep 15 2026, ~**1.05 B requests by Oct 11**; 20+ alternatives by Oct 17 (OpenAI Decisions API, Cloudflare Clef 27B/9B @ $0.038, Liquid AI d1, AWS Strands Decider, Mapika decider = OUR base family). Public benchmark **JevBench** (github.com/fstandhartinger/jevbench) + **BenchLM** leaderboard (~70 entries, dimensions: Intelligence / Calibration / Speed / Cost, chance-corrected): **decider-4b v2 #7 @ 71.29**, TypeSafe Jev 1.13 #3 @ 72.14, **decider-2b (our base) #30 @ 45.11**, LLM baselines 6–40 (GPT-6 Luna 40.5, DeepSeek V4.1 Flash 6.7). **Cgroup-AI prior art:** AgentCgroup (arXiv Feb 2026, eunomia.dev blog — eBPF cgroup v2 controller for AI-agent resource bursts) — the OS-layer problem is real and being attacked; our framing (user-space calibrated decision model + safety gate over cgroup telemetry) is an open niche. JevBench's dimensions are the eval checklist for decision models: chance-corrected correctness, calibration, speed (p50/p95), cost per 1k decisions.

**"Do all 3" started (Oct 18):** (1) **JevBench agent** — clone fstandhartinger/jevbench, open split, adapter to the platform rows, run `decider-2b` + `v3-2b` via `client.predict`, score with benchmark definitions, compare vs BenchLM references (decider-2b 45.11; decider-4b v2 71.29; Jev 72.14), deliverables `jevbench\`. (2) **Demo agent** — static-limits arm vs v3-2b-controller arm on identical shortened (~20-25 min) pressure arc; metrics: allocation integrals (cpu/mem × time, incl. idle tail), victim p95, give-backs, actions; charts + `demo-script.md` (2-min walkthrough) in `demo-outcomes\`. (3) **SRE outreach kit** written: `sre-outreach.md` — 30-s pitch, numbers, honest limits, who/where to contact, DM template, 8 discovery questions, what not to say.

**JevBench RESULTS (Oct 18):** ran the public **231 items** (only that many are actually published; 370 v1.5 drafts + 720 sealed unavailable) — 0 skips, 0 failures, **$0.0036 total**. Same items, argmax: **the platform-served `decider-2b` 0.762 vs published author-server 0.710** (item agreement 84.4%) → our serving path is NOT worse. Composite caveats: the platform's Noul readout is much softer (40.5% abstentions vs 22.4% published → the 0.2/0.8 threshold rule penalizes it heavily) + release mismatch (refs = v1.5.4; repo artifacts stop at v1.4.2.2; live manifest now v1.6.1). Indicative composites: base **43.71** (board ref 45.10, #30), **`v3-2b` fine-tune 25.98 — choice holds (~63) but Noul confidence regresses (−6.1 → −28.8)**: the 88.4% in-domain score does NOT transfer to general decision tasks — the specialist trade-off, quantified. **Candidate the platform team platform item:** Noul answers over the platform are markedly more abstention-heavy than the author-server on identical items (40.5% vs 22.4%) — possible serving-side confidence/logit-scaling difference, worth a look. Files: `jevbench\` (report.md, scores.json, predictions/, pinned v1.5.4 data).

**the platform team replied (Oct 23) — 3 things:** (1) **our rare-class read confirmed** ("it's the data not the recipe, targeted scenario batches are the move") → validates the batch-2/dsv4 direction; (2) **rows_url correction:** a fresh link can be obtained anytime by re-reading the evaluation (`project.evaluations()`) — the "permanent data loss" claim in `platform-feedback-private.md` was wrong and has been fixed; (3) **continuous learning unlocked for our org** (invited): create via `client.projects.create(name, base_model="mapika/decider-2b", description=...)`, call by name, teach via `client.corrections.create(res, {"action": {"correct": False, "answer": "..."}})`, versions via `project.versions()/promote()/set_auto_promote()`, preview `<name>:preview`, 1.5× base price, up to 5 models. **DONE:** fresh Windows venv `AppData\Local\Temp\opencode\platform-venv` with **platform 0.9.0** (the old m2-venv is corrupted — broken pip/pydantic); created **`workloadpilot-live`** (base `mapika/decider-2b`, auto_promote OFF, versions 0, learning 'waiting'); first decision OK (`do_nothing` 0.635, 555 tok); corrections create+read-back verified (`req_tz1Di9TuwYjI1XZKkQda`). **SDK 0.9.0 restructure:** `client.projects` = continuous models; custom-project APIs now `client.custom_models` + top-level `datasets`/`runs`/`evaluations` — old upload/eval scripts need a touch-up when next used. **Design: shadow learning** — v3-2b keeps serving; `workloadpilot-live` learns in parallel from the same states; teacher-disagreement corrections gated by confidence ≥0.6 + 5 s rate cap + never-automatic exclusion; promote/swap only when it beats v3-2b. M3 agent wiring + testing it now.

**Shadow live run + model cleanup + rename fix (Oct 23):** live shadow run on seed-3100 (`--model v3-2b --shadow workloadpilot-live`, 275.3 s): **137 shadow rows, 0 errors; 79 agree / 52 low-confidence / 5 corrections sent / 1 cooldown.** Continuous model: `waiting → learning 0.7 → training 1.0` → **first version training now** (built from only 137 decisions + 5 corrections; expect weak). **Model cleanup per user:** deleted `workloadpilot-v1`, `workloadpilot-v2-2b`, `workloadpilot-v2-4b-r2`, `workloadpilot-v3-pplx` (the middle two needed archive→delete); remaining: **`workloadpilot-v3-2b`** (serving) + **`workloadpilot-live`** (learning). Rollback note: v2-2b is gone per instruction; fallback = retrain (~$1–2). **Naming fix (SDK 0.9.0, deadline 2026-11-30):** `model_ref()` now emits canonical `workloadpilot-v3-2b`; continuous and legacy refs pass through; verified live (`do_nothing`, 555 tokens); README updated. **Accelerator available:** replay `dsv3_train` (8,230 rows) through `workloadpilot-live` as decisions+corrections ≈ **6 cents ≈ 15 min** → massive head start for v2.

**Continuous model SEEDED + v2 (Oct 23):** replayed dsv3_train **rules-mode only** (5,808 rows; 2,422 explore rows skipped to avoid teaching random actions) as decisions+corrections: **0 errors, 7.5 min, 3.71M tokens, $0.039**; self-agreement 74.4% (4,321 correct / 1,487 corrected). **v2 trained** (from 5,438 decisions): the platform-internal **92.5%** (v1/base 70.2%), loss 0.18, kept, no regressions, preview; v3 at ~12%. **OUR exam (dsv3_heldout, `exclude_from_training=True`): v2 = 84.66%** vs v3-2b 88.37% → **v3-2b still wins by 3.7 pts**; per-class: v2 wins `decrease_memory` (0.627 vs 0.475); ≈equal `protect_service` (0.745/0.752) + `throttle_io` (0.650/0.610); v3 wins `decrease_cpu` (0.268 vs 0), `restrict_process_count` (0.031 vs 0), `alert_operator` (0.821 vs 0.071), `increase_cpu` (0.925 vs 0.788). **Decision: do NOT promote v2; production stays v3-2b; continuous model keeps shadow-learning (v3+).** This validates continuous learning: base 67.7% → 84.7% from one seed (exam cost $0.018, excluded from learning).

**Repo published (Oct 24):** pushed to **https://github.com/BrajamohanDas-afk/kernel-decision-model** — initial commit, **226 files / 6.24 MB**, branch `main`. `.gitignore` excludes raw data (`*.jsonl`, `*.log`), the `jevbench/repo/` third-party clone, the bundle staging dir, and the friend's raw runs; README rewritten for the public repo (architecture, results table, repo map, credits). Git identity + gh credential helper confirmed.

**v3-2b FINE-TUNE AUDIT (Oct 23):** independent test of the served model vs base, report `results\FINE-TUNE-AUDIT-2026-10-23.md` + raw `m2-pilot\results\audit\`. **Dashboard 0.055/100% is NOT validation:** 0.055 is the last-batch loss (last-500 mean 0.307, first-500 0.547) and 1.0 is model metadata (full-train 92.48%, 1.2k sample 93.92%). No val loss logged; probe acc 85.15% @1029 -> 86.06% @2058 -> 85.76% @3087 (peak mid-run). **Heldout 2,640: 88.41% vs base 67.73%** (+20.7; macro-F1 0.666 vs 0.266; ECE 0.046 vs 0.120). **Fresh unseen seeds 4000-4003 (506 rows): 95.45% vs 71.34%** (+24.1; ECE 0.021). **Friend hardware (2,491): 83.10% vs 70.90%** (+12.2) but rare-class transfer drops (throttle 61%->17%, protect 75%->0%). Train-vs-heldout gap 4.1 pts (full train) = mild overfit, not memorization; early stop at ~2058 would likely help. Rare classes still weak: restrict 3.1%, decrease_cpu 29.3%, decrease_memory 47.5%, throttle 61%, protect 75.2%. **Structural feature gap:** decrease_cpu labels depend on 35 s PSI history, decrease_memory on the previous row, alert on memory.max/OOM events - none are in the 29 features. Serving latency p50 366 ms / p95 542 ms. Edge cases: 15/23 tuned, 11/23 base; all null/garbage/distractor/inertia cases safe; no forbidden actions. Continuous `workloadpilot-live` v1 = 36.3% reported acc, preview only, not serving. **Verdict: successful in-domain fine-tune, not yet production-proven.**

**Continuous v2 probe (Oct 24):** `workloadpilot-live` v2 appeared (5,438 decisions, reported 92.5% [88.7-95.2], loss 0.1802, preview only; v1 was 36.3%). Independent same-row probe via `system_one`: 100 random dsv3 heldout rows **v2 90.0% vs v3-2b 91.0%**; 148 rare-oversampled **77.0% vs 79.1%**; 36 friend rows **72.2% vs 66.7%**; agreement 88.5%. Per-class: v2 wins decrease_memory/throttle, loses increase_cpu/decrease_cpu/alert (small n). **No clear winner - keep v3-2b serving; promote v2 only after a >=500-row same-row A/B.** Raw: `m2-pilot\results\audit\continuous_v2_probe.json`.

**Cost so far:** $0. the platform credit untouched.

**Project files:** this folder — see `README.md` for the structure (`lab-scripts\`, `tools\`, `results\`).
