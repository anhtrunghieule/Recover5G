#!/usr/bin/env python3
"""Campaign 2 timer-phase / downtime-class runs (R2 N2): UPF SIGKILL at steady state (k=2 sessions) after a
seeded uniform 0-11 s delay (spreads the SMF heartbeat phase over one 11 s period), downtime d, restart.
Heartbeat phase, give-up and re-association are recovered offline from the pcap and the SMF log.
  R5G_INST=6 python3 c2/phase.py --downtimes 0,3,6,12 --reps 3
"""
import argparse, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import campaign  # noqa
p = argparse.ArgumentParser(); p.add_argument("--downtimes", default="0,3,6,12"); p.add_argument("--reps", type=int, default=3); p.add_argument("--seed", type=int, default=7); p.add_argument("--rstart", type=int, default=0)
a = p.parse_args()
rng = random.Random(a.seed)
specs = []
for r in range(a.rstart, a.rstart + a.reps):
    for d in [float(x) for x in a.downtimes.split(",")]:
        specs.append(dict(id=f"PH-upf-d{d:g}-r{r}", k=2, proc="idle", nf="upf", boundary=None,
                          t_offset=round(rng.uniform(0, 11), 3), mode="crash", downtime=d, seed=r, netem_ms=0,
                          window=72.0, poll=3.0))
a.budget = 0
campaign._run_all("phase", specs, a)
