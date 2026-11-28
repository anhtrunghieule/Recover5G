#!/usr/bin/env python3
"""Campaign 2: count-level vs identity-level R on the same snapshots (67.6 s and after next use)."""
import json, sys, collections
rows = collections.Counter(); ex = collections.defaultdict(list)
for p in sys.argv[1:]:
    for l in open(p):
        r = json.loads(l)
        if r.get("error") or not r.get("snap"):
            continue
        s = r["snap"].get("67.6") or {}
        c = {x[:2] if not x.startswith("Rg") else "Rg" for x in s.get("viol", [])} - {"NO"}
        i = {x[:2] if not x.startswith("Rg") else "Rg" for x in s.get("vid", [])} - {"NO"}
        rows["runs"] += 1
        if c or i:
            rows["violated_any"] += 1
        if i - c:
            rows["id_only_conjunct"] += 1; ex["id_only"].append((r["id"], sorted(i - c)))
        if c - i:
            rows["count_only_conjunct"] += 1; ex["count_only"].append((r["id"], sorted(c - i)))
        if i and not c:
            rows["id_flags_count_silent"] += 1
        if c and not i:
            rows["count_flags_id_silent"] += 1
print(dict(rows))
for k, v in ex.items():
    agg = collections.Counter(tuple(x[1]) for x in v)
    print(k, dict(agg))
