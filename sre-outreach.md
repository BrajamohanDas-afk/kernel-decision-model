# WorkloadPilot — SRE conversation kit

*Everything you need to have 5–10 useful conversations about whether this should exist. You send the messages; I've prepared the words, the numbers, and the questions.*

---

## The 30-second pitch

Every Linux box runs with guessed cgroup limits. Too generous → noisy neighbors and wasted capacity. Too tight → throttled services and surprise OOMs. Nobody closes the loop.

**WorkloadPilot** watches cgroup v2 telemetry (PSI, throttling, memory pressure, IO) every 2 seconds and picks one of 12 resource actions from a small hosted decision model — behind a safety gate that clamps, rate-limits, and whitelists everything it can do. Every decision and its outcome is logged.

*Verified in a 1-hour unscripted stress soak:* 1,754 live decisions, zero model errors, and it **gave CPU back when load dropped** — the thing static configs never do.

---

## What we can show (numbers to carry)

- **1-hour soak:** 1,754 decisions @ 30/min, 0 errors; restored `cpu.max` 100%→60% + halved CPU weight at load drops (baseline controller never lowered anything)
- **Model quality on our decision exam** (2,640 held-out rows, 12 classes): 88.4% accuracy · macro-F1 0.66 · **calibration ECE 0.047** (public decision models typically 0.1–0.3)
- **Safety:** 12-action whitelist · parameter clamps · 45 s per-action cooldown · only its own `wlp-*` cgroups · dry-run mode · zero unsafe writes in production-style runs
- **Cost per decision:** ~$0.000005 (pennies per thousand decisions)

## Say the honest limitations up front

- Today the model learns from a **rules teacher** — its value is distillation, calibration, portability, and gate-ability, not yet beating hand-tuned rules
- Tested only in synthetic scenarios (WSL), no production deployment yet
- The 12-action vocabulary is opinionated; every environment would need adaptation

---

## Who to talk to (where the pain lives)

- **Platform / SRE engineers** at startups running bare-metal or VM fleets (not managed-K8s-only shops)
- People running **latency-sensitive services on shared boxes**: databases, game servers, CI runners, media processing
- **Communities:** r/sre, r/linux, r/kubernetes (#sig-node / #sig-autoscaling), Hacker News (Show HN), lobste.rs, Rands Leadership Slack, local SRE meetups, homelab communities (early adopters who tolerate rough edges)
- **Adjacent builders:** the AgentCgroup authors (eBPF cgroup control for AI agents), sched_ext community, systemd folks

## DM / email template

> Hi <name> — I built a small decision layer over cgroup v2: it watches PSI / throttling / memory pressure every 2 s and issues one of 12 resource actions through a safety gate, logging every decision and its outcome. In a 1-hour unscripted soak it made 1,750 decisions with zero errors — and actually returned CPU when load dropped.
>
> I'm trying to figure out whether this is a real pain for platform teams or a solution looking for a problem. Would you trade 20 minutes of war stories about how you set resource limits? Three questions, no deck. Happy to share the soak charts either way.
>
> — <you>

Keep the first message **short**. The charts do the selling; the questions do the learning.

## Discovery questions (ask these, in this order)

1. How do you set cgroup limits today — defaults, hand-tuning, autoscalers? What was the last incident caused by a wrong limit?
2. When a service goes quiet, does anything give its allocation back? What does that waste cost you per month?
3. Would you trust an automated action only above a calibrated-confidence threshold? What threshold?
4. What would a safe trial look like for you — dry-run, shadow mode, one cgroup, one host?
5. Who would own such a layer — platform, SRE, kernel, or the app teams?
6. What telemetry do you already centralize (PSI? cgroup events?)? Where would decisions need to live?
7. Would you want it as a daemon, a sidecar, a Kubernetes operator, or a library?
8. What outcome would make you keep it after a week?

## What NOT to say

- Don't claim it beats their current setup — nobody believes that in a first message
- Don't lead with "AI" — lead with the problem and the measured numbers
- Don't promise production readiness — ask for war stories first

## Prepare before sending (optional but strong)

- A **2-minute screen recording**: the soak charts + the live decision log scrolling
- A one-page diagram: `telemetry → decision model → safety gate → cgroup actuator → outcome log`
- One slide of the honest limitations (above) — it buys credibility
