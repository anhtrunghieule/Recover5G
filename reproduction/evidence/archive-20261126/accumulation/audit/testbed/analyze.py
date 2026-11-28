#!/usr/bin/env python3
"""Turn campaign JSONL into CSVs + summary.json under ../results/real/ (schema in results/real/SCHEMA.md)."""
import csv
import json
import os
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r5g.runner import DELTA, RESULTS  # noqa: E402

D = DELTA["open5gs"]
COLS = ["id", "campaign", "proc", "nf", "boundary", "mode", "downtime", "t_offset", "k", "seed", "netem_ms",
        "fault_fired", "fault_at_s", "restart_ready_s", "gnb_tool_crash", "victim_last_line", "ever_violated", "viol_at_delta",
        "viol_end", "first_poll_s", "t_conv", "late_convergence", "R_detects", "crash_oracle", "crash_detects", "liveness_ok",
        "liveness_detects", "next_use", "viol_after_next_use", "lazy_repair", "error", "wall_s", "logs"]


def load(name):
    p = os.path.join(RESULTS, f"{name}.jsonl")
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p) if l.strip()]


def row(r, campaign):
    va, ve = r.get("viol_at_delta") or [], r.get("viol_end") or []
    an = r.get("viol_after_next_use")
    out = {k: r.get(k) for k in COLS if k in r}
    out.update({
        "campaign": campaign,
        "victim_last_line": (r.get("victim_last_lines") or [""])[-1][:160] if r.get("victim_last_lines") else "",
        "viol_at_delta": ";".join(sorted(set(va))), "viol_end": ";".join(sorted(set(ve))),
        "first_poll_s": r["series"][0]["t"] if r.get("series") else None,
        "late_convergence": bool(va) and not ve,
        "R_detects": bool(va) and bool(ve),
        "crash_oracle": ";".join(r.get("crash_oracle") or []),
        "crash_detects": bool(r.get("crash_oracle")),
        "liveness_detects": r.get("liveness_ok") is False,
        "next_use": json.dumps(r.get("next_use")) if r.get("next_use") else "",
        "viol_after_next_use": ";".join(sorted(set(an or []))) if an is not None else "",
        "lazy_repair": bool(ve) and an is not None and not an,
        "error": (r.get("error") or "")[:200],
    })
    return out


def key(r):
    """Dedup key (paper): (violated conjunct set at end, crashed NF, boundary type)."""
    return (r["viol_end"], r.get("nf"), r.get("boundary") or r.get("mode"))


def main():
    summary = {"delta_core_s": D}
    for camp in ["downtime", "boundary", "podkill"]:
        recs = load(camp)
        if not recs:
            continue
        rows = [row(r, camp) for r in recs]
        with open(os.path.join(RESULTS, f"{camp}.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        ok = [r for r in rows if not r["error"]]
        fired = [r for r in ok if r.get("fault_fired")]
        viol = [r for r in fired if r["R_detects"]]
        uniq = sorted({key(r) for r in viol})
        first_idx = next((i + 1 for i, r in enumerate(ok) if r["R_detects"]), None)
        conv = [r["t_conv"] for r in fired if r["ever_violated"] and not r["R_detects"] and r["t_conv"] is not None]
        conv_by = [r["t_conv"] for r in fired if not r["R_detects"] and r["t_conv"] is not None]
        restart = {}
        for r in fired:
            if r.get("restart_ready_s") is not None:
                restart.setdefault(r["nf"], []).append(r["restart_ready_s"])
        summary[camp] = {
            "schedules": len(rows), "harness_errors": len(rows) - len(ok), "fault_fired": len(fired),
            "R_violations_persistent": len(viol), "unique_violation_keys": [list(u) for u in uniq],
            "n_unique": len(uniq), "schedules_to_first_violation": first_idx,
            "crash_oracle_detects": sum(1 for r in fired if r["crash_detects"]),
            "liveness_oracle_detects": sum(1 for r in fired if r["liveness_detects"]),
            "R_and_not_crash": sum(1 for r in viol if not r["crash_detects"]),
            "R_and_not_liveness": sum(1 for r in viol if not r["liveness_detects"]),
            "late_convergence_after_delta": sum(1 for r in fired if r["late_convergence"]),
            "lazy_repair": sum(1 for r in fired if r["lazy_repair"]),
            "transient_then_converged": len(conv),
            "t_conv_s": {"n": len(conv), "median": st.median(conv) if conv else None, "max": max(conv) if conv else None},
            "converged_by_s_all_nonpersistent": {"n": len(conv_by), "median": st.median(conv_by) if conv_by else None,
                                                 "max": max(conv_by) if conv_by else None},
            "restart_ready_s_by_nf": {k: {"n": len(v), "median": round(st.median(v), 2), "max": round(max(v), 2)}
                                      for k, v in restart.items()},
            "wall_s_median": st.median([r["wall_s"] for r in ok if r.get("wall_s")]) if ok else None,
        }
    with open(os.path.join(RESULTS, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
