#!/usr/bin/env python3
"""Campaign 2 A4' audit (R2 round-1 Q1): crash the SMF at three positions around the AMF's ReleaseSMContext
(UE deregistration, k=1) and record the AMF-side code path and the final R verdict.

Positions (trigger = AMF log 'Deregistration request', then SIGKILL + immediate restart of the SMF):
  pre    netem AMF 2000 ms: the release leaves the AMF ~2 s later and reaches the *restarted* SMF incarnation
  flight netem AMF 150, SCP 150 ms, kill at +0.05 s: request on the wire / at the SCP while the SMF is down
  recv   netem AMF 150, SCP 150, SMF 600 ms, kill at +0.45 s: old SMF has received the request, its PFCP deletion
         and 204 are still queued in its egress (lost with the crash)
The effective position is verified offline in the pcap (pcap_ids.py).
  R5G_INST=5 python3 c2/a4audit.py --reps 3
"""
import argparse, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import campaign  # noqa
from r5g import runner, testbed  # noqa

POS = {
    "pre": dict(netem_after_pre={"amf": 2000}, trigger_delay=0.0),
    "flight": dict(netem_after_pre={"amf": 150, "scp": 150}, trigger_delay=0.05),
    "recv": dict(netem_after_pre={"amf": 150, "scp": 150, "smf": 600}, trigger_delay=0.45),
}
p = argparse.ArgumentParser(); p.add_argument("--reps", type=int, default=3); p.add_argument("--pos", default="pre,flight,recv")
p.add_argument("--k", type=int, default=1)
a = p.parse_args()
specs = []
for r in range(a.reps):
    for pos in a.pos.split(","):
        specs.append(dict(id=f"A4-{pos}-k{a.k}-r{r}", k=a.k, proc="dereg", nf="smf", boundary=None,
                          trigger=("amf", r"Deregistration request"), mode="crash", downtime=0.0, seed=r,
                          netem_ms=0, window=72.0, poll=3.0, stagger=0.0, position=pos, **POS[pos]))
a.budget = 0; a.name = "a4audit"
campaign._run_all("a4audit", specs, a)
