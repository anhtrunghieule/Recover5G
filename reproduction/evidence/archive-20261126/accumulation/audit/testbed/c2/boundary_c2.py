#!/usr/bin/env python3
"""Campaign 2 boundary campaign: all 54 schedules (18 boundaries x {amf,smf,upf}) x seeds, harness v2.

  R5G_INST=2 python3 c2/boundary_c2.py --seeds 0 --part 0/1
Seed-major order (every schedule of seed s before seed s+1), shuffled within a seed (random.Random(1)).
"""
import argparse, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import campaign  # noqa
from r5g import runner  # noqa

p = argparse.ArgumentParser()
p.add_argument("--seeds", default="0"); p.add_argument("--part", default="0/1")
p.add_argument("--nfs", default="amf,smf,upf"); p.add_argument("--budget", type=float, default=0)
p.add_argument("--name", default="boundary_c2")
p.add_argument("--skip", default="", help="comma-separated JSONL files whose (non-error) ids are skipped before partitioning")
a = p.parse_args()
i, n = map(int, a.part.split("/"))
specs = []
for seed in [int(x) for x in a.seeds.split(",")]:
    ss = []
    for proc, bs in campaign.BOUNDARY_SETS.items():
        for b in bs:
            for nf in a.nfs.split(","):
                ss.append(dict(id=f"B2-{proc}-{b}-{nf}-k2-s{seed}", k=2, proc=proc, nf=nf, boundary=b, mode="crash",
                               downtime=0.0, seed=seed, netem_ms=150, window=72.0, poll=3.0, stagger=0.3))
    random.Random(1).shuffle(ss)
    specs += ss
import json
done = set()
for f in [x for x in a.skip.split(",") if x]:
    if os.path.exists(f):
        for l in open(f):
            r = json.loads(l)
            if not r.get("error"):
                done.add(r["id"])
specs = [s for s in specs if s["id"] not in done]
specs = [s for j, s in enumerate(specs) if j % n == i]
print(len(specs), "schedules in this part", flush=True)
a.window = 72.0
campaign._run_all(a.name, specs, a)
