#!/usr/bin/env python3
"""Campaign 2: re-run the 11 campaign-1 AMF schedules whose UERANSIM gNB aborted (gnb_tool_crash), with the
patched gNB image r5g/ueransim:4f45e18-p2 (survives SCTP loss, releases UE contexts locally, redoes NG Setup).
Specs are identical to campaign 1 except the v2 harness (72 s window, identity oracle, pcap).
  UERANSIM_IMAGE=r5g/ueransim:4f45e18-p2 R5G_INST=4 python3 c2/amf_rerun.py --reps 1
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import campaign  # noqa
p = argparse.ArgumentParser(); p.add_argument("--reps", type=int, default=1); p.add_argument("--tag", default="p2")
a = p.parse_args()
B = [("pdu", "pdu.smf_sess_added"), ("reg", "reg.udm_done"), ("pdu", "pdu.amf_sess_added"), ("reg", "reg.amf_ue_added"),
     ("rel", "rel.amf_sess_removed"), ("pdu", "pdu.ip_allocated"), ("reg", "reg.complete"), ("rel", "rel.upf_sess_removed")]
P = [("P-4", "pdu", 1.237, 4), ("P-10", "rel", 1.61, 10), ("P-11", "reg", 1.439, 11)]
specs = []
for r in range(a.reps):
    for proc, b in B:
        specs.append(dict(id=f"AMF{a.tag}-B-{proc}-{b}-amf-k2-s0-r{r}", k=2, proc=proc, nf="amf", boundary=b, mode="crash",
                          downtime=0.0, seed=0, netem_ms=150, window=72.0, poll=3.0, stagger=0.3))
    for pid, proc, off, seed in P:
        specs.append(dict(id=f"AMF{a.tag}-{pid}-r{r}", k=2, proc=proc, nf="amf", boundary=None, t_offset=off, mode="crash",
                          downtime=0.0, seed=seed, netem_ms=150, window=72.0, poll=3.0))
a.budget = 0
campaign._run_all(f"amf_rerun_{a.tag}", specs, a)
