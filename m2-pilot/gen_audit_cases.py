"""Generate synthetic edge cases + a realistic serving sample for the v3-2b audit.

Runs inside wlp-lab (imports the real teacher and featurizer). Outputs the platform-format
feature rows plus the teacher's expected action for each crafted case.
"""
import datetime
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, "/root/workloadpilot")
sys.path.insert(0, "/root/workloadpilot/dsv2")

import featurize  # noqa: E402
import rules  # noqa: E402

OUT = Path("/root/workloadpilot/dsv2/out-audit")
OUT.mkdir(exist_ok=True)
T0 = 1761200000.0
MB = 1024.0 * 1024.0


def iso(t):
    return datetime.datetime.fromtimestamp(t, tz=datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def psi(avg10):
    return {"avg10": avg10, "avg60": avg10 * 0.8, "avg300": avg10 * 0.5, "total": 0}


def unit(throttled, psi_cpu, mem_cur, mem_high, mem_max, events_high, wbytes, psi_io, pids, mem_some, mem_full):
    return {
        "cpu_max": "100000 100000",
        "cpu_weight": "100",
        "cpu_stat": {"usage_usec": 0, "throttled_usec": throttled},
        "memory_current_mb": mem_cur,
        "memory_high_mb": mem_high,
        "memory_max_mb": mem_max,
        "memory_events": {"low": 0, "high": events_high, "max": 0, "oom": 0, "oom_kill": 0},
        "io_stat": {"rbytes": 0, "wbytes": wbytes},
        "pids_current": pids,
        "psi_cpu_some": psi(psi_cpu),
        "psi_memory_some": psi(mem_some),
        "psi_memory_full": psi(mem_full),
        "psi_io_some": psi(psi_io),
    }


def telemetry(spec, t0):
    """Six 2s rows ending at t0; counters ramp so featurize's 10s windows see the rates."""
    rows = []
    for step in range(5):
        t = t0 - 8.0 + step * 2.0
        frac = step / 4.0
        neigh = unit(
            spec["n_throttle"] * 1_000_000 * step * 2.0,
            spec["n_psi_cpu"], spec["n_mem"], spec["n_mem_high"], spec["n_mem_max"],
            spec["n_events"] * step * 2.0, spec["n_io"] * MB * step * 2.0,
            spec["n_psi_io"], spec["n_pids"] - spec["n_pids_delta"] * (4 - step),
            spec["n_mem_some"], spec["n_mem_full"],
        )
        crit = unit(
            spec["c_throttle"] * 1_000_000 * step * 2.0,
            spec["c_psi_cpu"], spec["c_mem"], spec["c_mem_high"], spec["c_mem_max"],
            0.0, 0.0, 0.0,
            spec["c_pids"], spec["c_mem_some"], spec["c_mem_full"],
        )
        system = {
            "psi_cpu_some": psi(spec["sys_cpu"]),
            "psi_memory_some": psi(spec["sys_mem"]),
            "psi_io_some": psi(spec["sys_io"]),
            "loadavg": [spec["load1"], spec["load1"], spec["load1"]],
            "mem_available_mb": 4000.0,
        }
        rows.append({
            "ts": iso(t),
            "uptime_s": t - T0,
            "system": system,
            "cgroups": {"wlp-critical": crit, "wlp-neighbor": neigh},
        })
    return rows


def victim(t0, p95_ms):
    samples = [0.2, 0.3, 0.5, 1.0, 0.9]
    return [{"ts": iso(t0 - 8.0 + i * 2.0), "latency_us": p95_ms * 1000.0 * f}
            for i, f in enumerate(samples)]


BASE = dict(n_throttle=0.0, n_psi_cpu=0.0, n_mem=25.0, n_mem_high=800.0, n_mem_max=950.0,
            n_events=0.0, n_io=0.0,
            n_psi_io=0.0, n_pids=6, n_pids_delta=0, n_mem_some=0.0, n_mem_full=0.0,
            c_throttle=0.0, c_psi_cpu=0.0, c_mem=8.0, c_mem_high=120.0, c_mem_max=150.0,
            c_pids=2, c_mem_some=0.0, c_mem_full=0.0,
            sys_cpu=0.0, sys_mem=0.0, sys_io=0.0, load1=0.2, p95=0.8)


def spec(**patch):
    out = dict(BASE)
    out.update(patch)
    return out


CASES = [
    ("quiet_idle", spec(), "do_nothing", "nothing crosses a threshold"),
    ("quiet_after_increase_cpu", dict(spec(), prev_action="increase_cpu"), "do_nothing",
     "action-inertia check: quiet state after a raise must still be do_nothing"),
    ("quiet_after_throttle_io", dict(spec(), prev_action="throttle_io"), "do_nothing",
     "action-inertia check: quiet state after an io throttle"),
    ("quiet_after_alert", dict(spec(), prev_action="alert_operator"), "do_nothing",
     "action-inertia check: quiet state after an alert"),
    ("neighbor_cpu_pinned_sys_pressure", spec(n_throttle=2.5, n_psi_cpu=60, sys_cpu=55),
     "increase_cpu", "neighbor throttled 2.5s/s while system cpu.pressure 55"),
    ("increase_cpu_in_distribution",
     spec(n_throttle=2.5, n_psi_cpu=60, sys_cpu=55, prev_action="increase_cpu"),
     "increase_cpu", "same pressure with the slopes/prev_action seen in real increase_cpu rows"),
    ("critical_throttled_alone", spec(c_throttle=2.0, c_psi_cpu=20, sys_cpu=30),
     "increase_cpu", "critical throttled 2.0s/s, system pressure 30"),
    ("protect_critical_under_noisy_neighbor",
     spec(c_throttle=0.8, c_psi_cpu=9, n_throttle=3.5, n_psi_cpu=75, sys_cpu=55),
     "protect_service", "critical pressured while neighbor consumes hard"),
    ("both_pinned_is_alert", spec(c_throttle=3.0, n_throttle=3.0, sys_cpu=60),
     "alert_operator", "both units pinned at quota; isolation needs a human"),
    ("neighbor_memory_near_high", spec(n_mem=890, n_mem_high=950), "increase_memory", "890/950 MB of memory.high"),
    ("neighbor_memory_events_growth",
     spec(n_mem=850, n_mem_high=950, n_events=5.0, n_mem_some=8.0), "increase_memory",
     "memory.events.high grows at 850/950"),
    ("neighbor_io_pressure", spec(n_io=4.0, n_psi_io=85.0), "throttle_io", "4 MB/s with unit io.pressure 85"),
    ("throttle_io_in_distribution",
     spec(n_io=4.0, n_psi_io=85.0, prev_action="throttle_io", n_mem=9.4, n_mem_high=1517.0),
     "throttle_io", "same io load with the memory/quota/prev_action seen in real throttle_io rows"),
    ("neighbor_pids_spike", spec(n_pids=6, n_pids_delta=2), "restrict_process_count", "pids +2 per sample"),
    ("cpu_released_decrease", spec(n_psi_cpu=1.0, n_throttle=0.05, sys_cpu=0.5),
     "decrease_cpu", "previous row had neighbor cpu.pressure >=30, now quiet"),
    ("memory_released_decrease", spec(n_mem=300, n_mem_high=950), "decrease_memory",
     "previous row 97% of high, now 32%"),
    ("hard_memory_alert_unlearnable", spec(n_mem=940, n_mem_high=950, n_mem_max=950, n_mem_some=35, n_mem_full=20),
     "alert_operator", "near memory.max; features carry no max/oom event, so this is a known blind spot"),
    ("null_units_cold_start", spec(), "do_nothing",
     "system block present, both unit blocks null"),
    ("victim_latency_distractor", spec(p95=45.0), "do_nothing", "victim is slow but cgroups are quiet; teacher ignores victim"),
    ("high_load_without_psi", spec(load1=64.0), "do_nothing", "loadavg is not a teacher signal"),
    ("psi_without_throttle", spec(n_psi_cpu=35.0, sys_cpu=5.0), "do_nothing",
     "mid cpu.pressure but quota not binding"),
    ("io_without_unit_pressure", spec(n_io=3.0, n_psi_io=0.02, sys_io=0.5), "do_nothing",
     "fast writes but unit io.pressure below 0.1; seen in friend runs"),
    ("garbage_tolerated", dict(BASE, n_pids=float("nan"), n_io=float("inf")), "do_nothing",
     "non-finite features must not change the choice"),
]


def build():
    edge, meta = [], []
    for name, spec_, expected, why in CASES:
        rules.reset_release_history()
        t0 = T0 + 1000.0
        tele = telemetry(spec_, t0)
        # previous row override for release cases
        prev_row = dict(tele[-2])
        if name == "cpu_released_decrease":
            prev_row = json.loads(json.dumps(prev_row))
            prev_row["cgroups"]["wlp-neighbor"]["psi_cpu_some"] = psi(60.0)
            busy_prev = json.loads(json.dumps(tele[-3]))
            busy_prev["cgroups"]["wlp-neighbor"]["psi_cpu_some"] = psi(60.0)
            busy_cur = json.loads(json.dumps(tele[-2]))
            busy_cur["cgroups"]["wlp-neighbor"]["psi_cpu_some"] = psi(60.0)
            rules.decide(busy_prev, busy_cur)
        if name == "memory_released_decrease":
            prev_row = json.loads(json.dumps(prev_row))
            prev_row["cgroups"]["wlp-neighbor"]["memory_current_mb"] = 930.0
        cur_row = tele[-1]
        teacher = rules.decide(prev_row, cur_row)["action"]
        if teacher != expected:
            print("MISMATCH", name, "teacher=", teacher, "expected=", expected,
                  rules.decide(prev_row, cur_row))
        prev_action = spec_.get("prev_action", "do_nothing")
        feature_row = featurize.build_row(
            {"ts": iso(t0), "action": "do_nothing"},
            {"ts": iso(t0 - 2.0), "action": prev_action},
            featurize.time_index(tele), featurize.time_index(victim(t0, spec_["p95"])),
            "latency", seed=999, quiet=False,
        )
        state = {key: feature_row.get(key) for key in featurize.FEATURE_KEYS}
        if name == "garbage_tolerated":
            state["n_pids"] = float("nan")
            state["n_io_wbytes_mb_per_s_10s"] = float("inf")
        if name == "null_units_cold_start":
            for key in list(state):
                if key.startswith("n_") or key.startswith("c_"):
                    state[key] = None
        if name == "increase_cpu_in_distribution":
            state.update({"n_cpu_psi_slope": 28.0, "sys_psi_cpu_slope": 25.0,
                          "n_cpu_max_cores": 1.0, "n_mem_high_mb": 685.0,
                          "n_mem_headroom_mb": 666.0, "sys_load1": 1.24})
        if name == "throttle_io_in_distribution":
            state.update({"n_cpu_psi_slope": -1.1, "sys_psi_cpu_slope": -1.5,
                          "n_cpu_max_cores": 0.5, "n_mem_headroom_mb": 1507.6,
                          "sys_load1": 1.0})
        edge.append({"id": name, "state": state})
        meta.append({"id": name, "expected": expected, "rationale": why})
    (OUT / "edge_cases.jsonl").write_text(
        "\n".join(json.dumps(row) for row in edge) + "\n", encoding="utf-8")
    (OUT / "edge_cases_meta.jsonl").write_text(
        "\n".join(json.dumps(row) for row in meta) + "\n", encoding="utf-8")

    rng = random.Random(20261023)
    heldout = [json.loads(line) for line in open("/root/workloadpilot/dsv2/dsv3/dsv3_heldout.jsonl", encoding="utf-8")]
    friend = [json.loads(line) for line in open("/root/workloadpilot/dsv2/out-friend/train.jsonl", encoding="utf-8")]
    realistic = []
    for label in sorted({row["labels"]["action"] for row in heldout}):
        for row in rng.sample([r for r in heldout if r["labels"]["action"] == label], 2):
            realistic.append({"id": "heldout-" + row["id"], "state": row["state"],
                              "expected": label})
    for label in sorted({row["labels"]["action"] for row in friend}):
        pool = [r for r in friend if r["labels"]["action"] == label]
        if pool:
            row = rng.choice(pool)
            realistic.append({"id": "friend-" + row["id"], "state": row["state"],
                              "expected": label})
    (OUT / "realistic_rows.jsonl").write_text(
        "\n".join(json.dumps(row) for row in realistic) + "\n", encoding="utf-8")
    print("edge", len(edge), "realistic", len(realistic))


if __name__ == "__main__":
    build()
