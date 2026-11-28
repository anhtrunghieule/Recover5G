#!/usr/bin/env python3
"""Move records with a harness 'error' from a campaign JSONL into <name>_errors.jsonl so they are re-run."""
import json, sys
for p in sys.argv[1:]:
    keep, bad = [], []
    for l in open(p):
        (bad if json.loads(l).get("error") else keep).append(l)
    open(p, "w").writelines(keep)
    if bad:
        open(p.replace(".jsonl", "_errors.jsonl"), "a").writelines(bad)
    print(p, "kept", len(keep), "moved", len(bad))
