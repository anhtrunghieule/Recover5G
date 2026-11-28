#!/usr/bin/env python3
"""Campaign 2 boundary campaign aggregates from boundary_c2.csv (analyze_c2.py output)."""
import collections, csv, json, sys
rows = list(csv.DictReader(open(sys.argv[1])))
seen = {}
for r in rows:                       # ids are unique across worker files; keep the first
    seen.setdefault(r["id"], r)
rows = list(seen.values())
ok = [r for r in rows if not r["error"] and r["fault_fired"] == "True"]
out = {"schedules": len(rows), "fired": len(ok), "errors": sum(1 for r in rows if r["error"]),
       "per_seed": dict(collections.Counter(r["seed"] for r in rows)),
       "per_nf": dict(collections.Counter(r["nf"] for r in ok))}
pers = [r for r in ok if r["persistent_conjuncts"]]
out["persistent"] = len(pers)
out["persistent_per_nf"] = dict(collections.Counter(r["nf"] for r in pers))
out["persistent_class"] = dict(collections.Counter(
    ("num" if r["persistent_numeric"] else "") + ("NU" if r["persistent_NU"] else "") + ("UE" if r["persistent_UE"] else "") for r in pers))
out["crash_oracle_detects"] = sum(1 for r in ok if r["crash_oracle"])
out["liveness_fails"] = sum(1 for r in ok if r["liveness_ok"] == "False")
out["persistent_and_liveness_fail"] = sum(1 for r in pers if r["liveness_ok"] == "False")
out["persistent_liveness_silent"] = sum(1 for r in pers if r["liveness_ok"] == "True")
out["liveness_fail_R_clean"] = sum(1 for r in ok if r["liveness_ok"] == "False" and not r["persistent_conjuncts"])
out["lazy_repair_v1"] = sum(1 for r in pers if r["lazy_repair_v1"] == "True")
out["lazy_repair_v2"] = sum(1 for r in pers if r["lazy_repair_v2"] == "True")
out["gnb_tool_crash"] = sum(1 for r in ok if r["gnb_tool_crash"] == "True")
# reproducibility per schedule (proc, boundary, nf) across seeds
per = collections.defaultdict(list)
for r in ok:
    per[(r["proc"], r["boundary"], r["nf"])].append(bool(r["persistent_conjuncts"]))
rep = collections.Counter()
for k, v in per.items():
    rep[f"{sum(v)}/{len(v)}"] += 1
out["schedules_with_n_seeds"] = dict(collections.Counter(len(v) for v in per.values()))
out["persistent_fraction_per_schedule"] = dict(rep)
out["unique_keys"] = len({(r["persistent_conjuncts"], r["nf"], r["boundary"]) for r in pers})
conv = sorted(float(r["t_conv_all"]) for r in ok if r["t_conv_all"] and not r["persistent_conjuncts"])
out["converged_t_conv_median_max"] = (conv[len(conv) // 2], conv[-1]) if conv else None
print(json.dumps(out, indent=1))
print("per schedule (persistent seeds / seeds run):")
for k in sorted(per):
    v = per[k]
    labs = sorted({r["persistent_conjuncts"] for r in ok if (r["proc"], r["boundary"], r["nf"]) == k and r["persistent_conjuncts"]})
    print(f"  {k[2]:4s} {k[1]:24s} {sum(v)}/{len(v)} {labs}")
