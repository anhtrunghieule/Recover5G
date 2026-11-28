#!/usr/bin/env python3
"""Revision 2026-11-25: evaluation of the delay-dependence runs (exp/timing.py).

Per run
  fired        the log trigger matched and the kill was issued
  persistent   the checker (count rule or identity rule) reports a violation at both checkpoints
               (first poll at or after 33.8 s and at or after 67.6 s); the labels common to both are the signature
  lateness_ms  time stamp of the victim's last log line minus time stamp of the trigger line (Open5GS log clock,
               1 ms resolution, same VM). 0 means the victim logged nothing after the trigger line.
Across conditions, a schedule is delay-dependent if it is persistent under one delay setting and not another.
Writes timing_matrix.csv and timing_summary.json into the results directory.

  python3 exp/timing_eval.py <dir with timing_*.jsonl>
"""
import collections, csv, glob, json, os, re, statistics, sys

R = sys.argv[1]
ANSI = re.compile(r"\x1b\[[0-9;]*m")
TS = re.compile(r"(\d\d)/(\d\d) (\d\d):(\d\d):(\d\d)\.(\d\d\d)")


def ms(line):
    m = TS.search(ANSI.sub("", line or ""))
    if not m:
        return None
    _, d, h, mi, s, x = (int(g) for g in m.groups())
    return ((d * 24 + h) * 60 + mi) * 60000 + s * 1000 + x


def labels(snap):
    if not snap:
        return None
    return sorted(set(snap.get("viol", [])) | set(snap.get("vid", [])))


conds, runs, first_errors = [], {}, collections.Counter()
for fp in sorted(glob.glob(os.path.join(R, "timing_*.jsonl"))):
    cond = os.path.basename(fp)[7:-6]
    conds.append(cond)
    for l in open(fp):
        r = json.loads(l)
        if r.get("error"):
            first_errors[cond] += 1      # a later record of the same schedule replaces this one if the rerun worked
        key = (r["proc"], r["boundary"], r["nf"])
        row = {"cond": cond, "proc": r["proc"], "boundary": r["boundary"], "nf": r["nf"], "error": r.get("error", "")}
        if not r.get("error"):
            a, b = labels(r["snap"].get("33.8")), labels(r["snap"].get("67.6"))
            tl, vl = ms(r.get("trigger_line")), [ms(x) for x in r.get("victim_last_lines") or []]
            vl = [x for x in vl if x is not None]
            late = None if (tl is None or not vl) else max(0, max(vl) - tl)
            row.update({"fired": bool(r.get("fault_fired")), "cp1": ";".join(a or []), "cp2": ";".join(b or []),
                        "persistent": bool(a) and bool(b), "signature": ";".join(sorted(set(a or []) & set(b or []))),
                        "state_persistent": bool([x for x in (a or []) if not x.startswith("R4")]) and bool([x for x in (b or []) if not x.startswith("R4")]),
                        "liveness_flag": r.get("liveness_ok") is False, "crash_flag": bool(r.get("crash_oracle")),
                        "next_use_all_ok": r.get("next_use_all_ok"), "viol_after_next_use": ";".join(r.get("viol_after_next_use") or []),
                        "gnb_tool_crash": bool(r.get("gnb_tool_crash")), "fault_at_s": r.get("fault_at_s"),
                        "lateness_ms": late, "stack": r.get("stack"), "wall_s": r.get("wall_s")})
        runs[(cond,) + key] = row
keys = sorted({k[1:] for k in runs})
mat = []
for k in keys:
    row = {"proc": k[0], "boundary": k[1], "nf": k[2]}
    for c in conds:
        x = runs.get((c,) + k)
        row[c] = "" if x is None else ("ERR" if x["error"] else ("not-fired" if not x["fired"] else (x["signature"] if x["persistent"] else "-")))
        row[c + "_late_ms"] = "" if x is None or x.get("lateness_ms") is None else x["lateness_ms"]
    mat.append(row)
with open(os.path.join(R, "timing_matrix.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(mat[0].keys())); w.writeheader(); w.writerows(mat)
allrows = list(runs.values())
with open(os.path.join(R, "timing_runs.csv"), "w", newline="") as f:
    ks = []
    for x in allrows:
        for k in x:
            if k not in ks:
                ks.append(k)
    w = csv.DictWriter(f, fieldnames=ks); w.writeheader(); w.writerows(allrows)
S = {"conditions": {}}
for c in conds:
    xs = [x for x in allrows if x["cond"] == c]
    ok = [x for x in xs if not x["error"]]
    fired = [x for x in ok if x["fired"]]
    lat = [x["lateness_ms"] for x in fired if x.get("lateness_ms") is not None]
    S["conditions"][c] = {
        "runs": len(xs), "errors": len(xs) - len(ok), "harness_error_attempts": first_errors[c], "fired": len(fired),
        "not_fired": len(ok) - len(fired),
        "persistent": sum(1 for x in fired if x["persistent"]), "state_persistent": sum(1 for x in fired if x["state_persistent"]),
        "persistent_by_nf": dict(collections.Counter(x["nf"] for x in fired if x["persistent"])),
        "signatures": dict(collections.Counter(x["signature"] for x in fired if x["persistent"])),
        "liveness_flags": sum(1 for x in fired if x["liveness_flag"]), "crash_flags": sum(1 for x in fired if x["crash_flag"]),
        "persistent_and_liveness_passes": sum(1 for x in fired if x["persistent"] and not x["liveness_flag"]),
        "gnb_tool_crash": sum(1 for x in ok if x["gnb_tool_crash"]),
        "lateness_n": len(lat), "lateness_median_ms": statistics.median(lat) if lat else None,
        "lateness_p90_ms": sorted(lat)[int(0.9 * (len(lat) - 1))] if lat else None, "lateness_max_ms": max(lat) if lat else None,
        "lateness_gt5ms": sum(1 for v in lat if v > 5), "lateness_eq0": sum(1 for v in lat if v == 0),
        "wall_hours": round(sum(x.get("wall_s") or 0 for x in ok) / 3600, 2)}
pairs = {}
for a in conds:
    for b in conds:
        if a >= b:
            continue
        both = [k for k in keys if (a,) + k in runs and (b,) + k in runs and not runs[(a,) + k]["error"] and not runs[(b,) + k]["error"]
                and runs[(a,) + k]["fired"] and runs[(b,) + k]["fired"]]
        pa = {k for k in both if runs[(a,) + k]["persistent"]}; pb = {k for k in both if runs[(b,) + k]["persistent"]}
        pairs[f"{a}_vs_{b}"] = {"comparable": len(both), "both": len(pa & pb), f"only_{a}": len(pa - pb), f"only_{b}": len(pb - pa),
                                "neither": len(both) - len(pa | pb),
                                f"only_{a}_list": ["/".join(k) for k in sorted(pa - pb)], f"only_{b}_list": ["/".join(k) for k in sorted(pb - pa)],
                                "same_signature": sum(1 for k in pa & pb if runs[(a,) + k]["signature"] == runs[(b,) + k]["signature"])}
S["pairs"] = pairs
json.dump(S, open(os.path.join(R, "timing_summary.json"), "w"), indent=1)
print(json.dumps(S, indent=1))
