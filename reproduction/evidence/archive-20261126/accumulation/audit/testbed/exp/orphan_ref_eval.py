#!/usr/bin/env python3
"""Revision 2026-11-25: the orphan-session runs (UERANSIM conditions) judged by the trace reference of wire_truth.py.
Writes orphan_ref_summary.json: per group, runs where reference and checker are violated / clean at both checkpoints."""
import collections, json, os, sys
R = sys.argv[1]
recs = {}
for l in open(os.path.join(R, "orphan_repl.jsonl")):
    d = json.loads(l); recs[d["id"]] = d
g = collections.defaultdict(lambda: collections.Counter())
for l in open(os.path.join(R, "wire_truth_orphan.jsonl")):
    d = json.loads(l)
    if "pilot" in d["id"] or d.get("error"):
        continue
    tag = recs[d["id"]]["tag"]
    if tag.endswith("-p1"):
        continue                        # stock gNB not restarted: no re-registration, reported separately
    grp = "fault-base" if (tag.startswith("base") and recs[d["id"]].get("fault") == "amf") else "repair-or-control"
    ref = [r["ref_status"] for r in d["rows"]]; px = [bool(r["proxy"]) for r in d["rows"]]
    upf = all("REF-S-P" in r["ref"] for r in d["rows"])
    c = g[grp]; c["n"] += 1
    c["ref_violated_both"] += all(x == "violated" for x in ref); c["ref_clean_both"] += all(x == "clean" for x in ref)
    c["ref_upf_identity_both"] += upf; c["proxy_violated_both"] += all(px); c["proxy_clean_both"] += not any(px)
    c["agree"] += (all(x == "violated" for x in ref) and all(px)) or (all(x == "clean" for x in ref) and not any(px))
out = {k: dict(v) for k, v in g.items()}
json.dump(out, open(os.path.join(R, "orphan_ref_summary.json"), "w"), indent=1); print(out)
