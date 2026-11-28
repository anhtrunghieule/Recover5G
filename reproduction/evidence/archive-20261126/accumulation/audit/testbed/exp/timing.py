#!/usr/bin/env python3
"""Revision 2026-11-25: how much of the boundary campaign depends on the emulated delay?

The same 54 log-triggered boundary schedules (18 boundaries x {amf, smf, upf}, two UEs, seed 0) are run under
different delay conditions. Nothing else changes between conditions.

  g0     no netem at all (natural bridge timing)
  g10    10 ms egress delay on every NF
  g150   150 ms egress delay on every NF (the paper's adversarial setting)
  v150   150 ms egress delay on the crashed NF only; every other NF at natural timing

Each record is the normal runner record (verdicts at both checkpoints, next use, liveness, pcap) plus the
trigger line and the victim's last log lines, from which exp/timing_eval.py derives how late the kill landed.

  . ../env.sh; R5G_INST=3 python3 exp/timing.py --cond g0
"""
import argparse, json, os, random, sys, traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import campaign  # noqa
from r5g import runner, testbed  # noqa

OUT = runner.RESULTS
COND = {"g0": dict(netem_ms=0), "g10": dict(netem_ms=10), "g150": dict(netem_ms=150), "v150": dict(netem_ms=0)}


def specs(cond):
    out = []
    for proc, bs in campaign.BOUNDARY_SETS.items():
        for b in bs:
            for nf in ("amf", "smf", "upf"):
                s = dict(id=f"T-{cond}-{proc}-{b}-{nf}", cond=cond, k=2, proc=proc, nf=nf, boundary=b, mode="crash",
                         downtime=0.0, seed=0, window=72.0, poll=3.0, stagger=0.3, **COND[cond])
                if cond == "v150":
                    s["netem_per_nf"] = {nf: 150}
                out.append(s)
    random.Random(20261125).shuffle(out)      # same order in every condition
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cond", required=True, choices=list(COND))
    ap.add_argument("--part", type=int, default=0); ap.add_argument("--parts", type=int, default=1)
    ap.add_argument("--image", default="r5g/open5gs:e85748e")
    a = ap.parse_args()
    S = [s for i, s in enumerate(specs(a.cond)) if i % a.parts == a.part]
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"timing_{a.cond}.jsonl")
    done = set()
    if os.path.exists(path):
        for line in open(path):
            try:
                d = json.loads(line)
                if not d.get("error"):
                    done.add(d["id"])
            except Exception:
                pass
    testbed.up(image=a.image)
    for s in S:
        if s["id"] in done:
            continue
        try:
            rec = runner.run(s, OUT)
        except Exception as e:
            rec = dict(s, error=f"{type(e).__name__}: {e}", tb=traceback.format_exc()[-800:])
        rec["stack"] = int(os.environ.get("R5G_INST", "0"))
        runner.write_jsonl(path, rec)
        sn = rec.get("snap") or {}
        print(s["id"], "fired", rec.get("fault_fired"), "33.8:", (sn.get("33.8") or {}).get("viol"),
              "67.6:", (sn.get("67.6") or {}).get("viol"), "live", rec.get("liveness_ok"),
              "gnb_crash", rec.get("gnb_tool_crash"), "err", rec.get("error", "")[:100], flush=True)
