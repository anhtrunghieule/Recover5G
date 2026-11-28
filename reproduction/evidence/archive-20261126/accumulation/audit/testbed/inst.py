#!/usr/bin/env python3
"""Campaign 2: generate an independent testbed instance N (containers r5g<N>-*, subnet 172.(22+N).0.0/24).

  python3 inst.py gen 1 2 3        # writes inst/<N>/docker-compose.yml and inst/<N>/config/
  R5G_INST=1 python3 campaign.py up

Instance 0 is the campaign-1 testbed (docker-compose.yml, config/) and is not generated.
"""
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def gen(n):
    d = os.path.join(HERE, "inst", str(n))
    if os.path.exists(os.path.join(d, "config")):
        shutil.rmtree(os.path.join(d, "config"))
    os.makedirs(d, exist_ok=True)
    shutil.copytree(os.path.join(HERE, "config"), os.path.join(d, "config"))
    net = f"172.{22 + n}.0."
    for root, _, files in os.walk(os.path.join(d, "config")):
        for f in files:
            p = os.path.join(root, f)
            s = open(p).read().replace("172.22.0.", net)
            open(p, "w").write(s)
    s = open(os.path.join(HERE, "docker-compose.yml")).read()
    s = s.replace("172.22.0.", net)
    s = re.sub(r"^name: r5g$", f"name: r5g{n}", s, flags=re.M)
    s = s.replace("container_name: r5g-", f"container_name: r5g{n}-")
    open(os.path.join(d, "docker-compose.yml"), "w").write(s)
    print("generated", d)


if __name__ == "__main__":
    if sys.argv[1] == "gen":
        for x in sys.argv[2:]:
            gen(int(x))
