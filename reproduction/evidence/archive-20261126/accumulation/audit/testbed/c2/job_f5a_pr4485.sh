#!/bin/bash
export DOCKER_CONTEXT=colima-recover5g R5G_INST=4 R5G_OUT=/Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/results/real/campaign2/f5a
cd /Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/testbed
python3 campaign.py up --image r5g/open5gs:e85748e-pr4485 >/dev/null 2>&1
python3 - <<'PY'
import os, sys
sys.argv=['x']
sys.path.insert(0, '.')
import campaign
from r5g import runner
specs=[dict(id=f"D-smf-crash-d0-k2-s{s}-pr4485", k=2, proc="idle", nf="smf", boundary=None, t_offset=0.0, mode="crash",
            downtime=0.0, seed=s, netem_ms=0, window=72.0, poll=3.0, image="r5g/open5gs:e85748e-pr4485") for s in range(3)]
class A: budget=0
campaign._run_all("F5a", specs, A())
PY
export R5G_OUT=/Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/results/real/campaign2/lazy
python3 c2/lazy_c2.py --runs 3 --image r5g/open5gs:e85748e-pr4485
