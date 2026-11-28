#!/usr/bin/env python3
"""Revision 2026-11-25: compare the checker's verdicts with the trace reference on the held-out runs.

Inputs: heldout.jsonl (runner records) and wire_truth_heldout.jsonl (exp/wire_truth.py).
Outputs (in the same directory): heldout_runs.csv, heldout_snapshots.csv, heldout_disagreements.csv,
heldout_summary.json.

Units
  snapshot   one poll of a run (every 3 s for 72 s after the restart, or after the procedure for controls)
  checkpoint the first snapshot at or after 33.8 s and the first at or after 67.6 s
  run verdict "persistent" = violated at both checkpoints; "clean" = clean at both; "mixed" otherwise
A snapshot enters a confusion table only if the reference is known and the snapshot is not changing.
"""
import collections, csv, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from r5g.verdict import first_stably_clean

R = sys.argv[1]
SRC = sys.argv[2] if len(sys.argv) > 2 else "heldout.jsonl"
WT = sys.argv[3] if len(sys.argv) > 3 else "wire_truth_heldout.jsonl"
PFX = sys.argv[4] if len(sys.argv) > 4 else "heldout"
CP = (33.8, 67.6)
recs = {}
for l in open(os.path.join(R, SRC)):
    d = json.loads(l)
    d.setdefault("kind", "kill")
    if not d.get("error"):
        recs[d["id"]] = d
errors = [json.loads(l) for l in open(os.path.join(R, SRC)) if json.loads(l).get("error")]
wt = {}
for l in open(os.path.join(R, WT)):
    d = json.loads(l)
    wt[d["id"]] = d


def conf(pairs):
    c = collections.Counter()
    for pred, ref in pairs:
        c[("TP" if ref else "FP") if pred else ("FN" if ref else "TN")] += 1
    return {k: c.get(k, 0) for k in ("TP", "FP", "FN", "TN")}


def wilson(k, n, z=1.96):
    if n == 0:
        return (None, None)
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (round(max(0.0, c - h), 4), round(min(1.0, c + h), 4))


snap_rows, run_rows, dis = [], [], []
for rid, rec in sorted(recs.items()):
    w = wt.get(rid)
    if not w or w.get("error"):
        run_rows.append({"id": rid, "kind": rec["kind"], "status": "adjudication-error", "detail": (w or {}).get("error", "missing")})
        continue
    rows = w["rows"]
    for r in rows:
        stable = r["changing"] is None and r["ref_status"] != "unknown"
        snap_rows.append({"id": rid, "kind": rec["kind"], "nf": rec.get("nf"), "proc": rec["proc"], "t": r["rel"],
                          "changing": r["changing"] or "", "ref_status": r["ref_status"], "ref": ";".join(r["ref"]),
                          "count_rule": ";".join(r["count_rule"]), "proxy": ";".join(r["proxy"]), "r4": ";".join(r["r4"]),
                          "stable": stable, "ref_viol": r["ref_status"] == "violated", "count_viol": bool(r["count_rule"]),
                          "proxy_viol": bool(r["proxy"]), "upf_live_ips": ";".join(r["upf_live_ips"]),
                          "upf_log_count": r["upf_log_count"], "upf_metric": r["upf_metric"]})
    cps = [next((r for r in rows if r["rel"] >= t), None) for t in CP]

    def verdict(key):
        if any(c is None for c in cps):
            return "no-checkpoint"
        if any(c["ref_status"] == "unknown" for c in cps):
            return "unknown"
        if any(c["changing"] for c in cps):
            return "changing"
        v = [(c["ref_status"] == "violated") if key == "ref" else bool(c[key]) for c in cps]
        return "persistent" if all(v) else ("clean" if not any(v) else "mixed")

    ref_v, prox_v, cnt_v = verdict("ref"), verdict("proxy"), verdict("count_rule")
    between = [r for r in rows if CP[0] <= r["rel"] <= CP[1] and r["changing"] is None and r["ref_status"] != "unknown"]
    run_rows.append({
        "id": rid, "kind": rec["kind"], "nf": rec.get("nf") or "", "proc": rec["proc"], "t_offset": rec.get("t_offset"),
        "stack": rec.get("stack"), "fault_fired": rec.get("fault_fired"), "gnb_tool_crash": rec.get("gnb_tool_crash"),
        "ref": ref_v, "proxy": prox_v, "count_rule": cnt_v,
        "liveness_flag": rec.get("liveness_ok") is False, "crash_flag": bool(rec.get("crash_oracle")),
        "next_use_all_ok": rec.get("next_use_all_ok"),
        "ref_labels_cp2": ";".join(cps[1]["ref"]) if cps[1] else "", "proxy_labels_cp2": ";".join(cps[1]["proxy"]) if cps[1] else "",
        "n_snap": len(rows), "n_changing": sum(1 for r in rows if r["changing"]),
        "n_unknown": sum(1 for r in rows if r["ref_status"] == "unknown"),
        "interval_ref_flip": len({r["ref_status"] for r in between}) > 1,
        "interval_proxy_flip": len({bool(r["proxy"]) for r in between}) > 1,
        "first_ref_clean_t": first_stably_clean(rows),
        "probe_sound": (w.get("probe") or {}).get("sound"), "probe_exact": (w.get("probe") or {}).get("exact"),
        "probe_changed": (w.get("probe") or {}).get("changed_during_probe"), "probe_fwd": ";".join((w.get("probe") or {}).get("forwarded_ips", [])),
        "probe_wire_live": ";".join((w.get("probe") or {}).get("wire_live_ips", []))})
    for r in rows:
        if r["changing"] is None and r["ref_status"] != "unknown" and (r["ref_status"] == "violated") != bool(r["proxy"]):
            dis.append({"id": rid, "kind": rec["kind"], "nf": rec.get("nf") or "", "proc": rec["proc"], "t": r["rel"],
                        "ref": ";".join(r["ref"]), "proxy": ";".join(r["proxy"]), "count_rule": ";".join(r["count_rule"]),
                        "upf_live_ips": ";".join(r["upf_live_ips"]), "upf_metric": r["upf_metric"]})


def dump(name, rows):
    keys = []
    for x in rows:
        for k in x:
            if k not in keys:
                keys.append(k)
    with open(os.path.join(R, name), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)


dump(PFX + "_runs.csv", run_rows); dump(PFX + "_snapshots.csv", snap_rows); dump(PFX + "_disagreements.csv", dis or [{"id": ""}])
ok = [r for r in run_rows if "ref" in r]
S = {"runs_recorded": len(recs), "runs_with_harness_error": len(errors), "runs_adjudicated": len(ok),
     "by_kind": dict(collections.Counter(r["kind"] for r in ok)),
     "faults_fired": sum(1 for r in ok if r["kind"] == "kill" and r["fault_fired"]),
     "gnb_tool_crash_runs": sum(1 for r in ok if r.get("gnb_tool_crash"))}
st = [s for s in snap_rows if s["stable"]]
S["snapshots"] = {"total": len(snap_rows), "changing": sum(1 for s in snap_rows if s["changing"]),
                  "unknown": sum(1 for s in snap_rows if s["ref_status"] == "unknown" and not s["changing"]),
                  "stable_known": len(st)}
S["snapshot_confusion_proxy_vs_ref"] = conf([(s["proxy_viol"], s["ref_viol"]) for s in st])
S["snapshot_confusion_count_vs_ref"] = conf([(s["count_viol"], s["ref_viol"]) for s in st])
dec = [r for r in ok if r["ref"] in ("persistent", "clean", "mixed") and r["proxy"] in ("persistent", "clean", "mixed")]
S["run_verdicts"] = {"ref": dict(collections.Counter(r["ref"] for r in ok)),
                     "proxy": dict(collections.Counter(r["proxy"] for r in ok)),
                     "count_rule": dict(collections.Counter(r["count_rule"] for r in ok))}
S["run_confusion_persistent"] = {
    "proxy_vs_ref": conf([(r["proxy"] == "persistent", r["ref"] == "persistent") for r in dec]),
    "count_vs_ref": conf([(r["count_rule"] == "persistent", r["ref"] == "persistent") for r in dec]),
    "liveness_vs_ref": conf([(r["liveness_flag"], r["ref"] == "persistent") for r in dec]),
    "crash_only_vs_ref": conf([(r["crash_flag"], r["ref"] == "persistent") for r in dec]),
    "n_decidable_runs": len(dec)}
for k in ("proxy_vs_ref", "count_vs_ref", "liveness_vs_ref", "crash_only_vs_ref"):
    c = S["run_confusion_persistent"][k]
    c["fn_rate_ci95"] = wilson(c["FN"], c["FN"] + c["TP"]); c["fp_rate_ci95"] = wilson(c["FP"], c["FP"] + c["TN"])
ctl = [r for r in dec if r["kind"] == "nofault"]
S["controls"] = {"n": len(ctl), "ref_persistent": sum(1 for r in ctl if r["ref"] == "persistent"),
                 "proxy_persistent": sum(1 for r in ctl if r["proxy"] == "persistent"),
                 "proxy_any_checkpoint": sum(1 for r in ctl if r["proxy"] != "clean"),
                 "liveness_flag": sum(1 for r in ctl if r["liveness_flag"])}
S["interval"] = {"runs_ref_flips_between_checkpoints": sum(1 for r in dec if r["interval_ref_flip"]),
                 "runs_proxy_flips_between_checkpoints": sum(1 for r in dec if r["interval_proxy_flip"]),
                 "runs_same_endpoints_but_flip_inside": sum(1 for r in dec if r["ref"] in ("persistent", "clean") and r["interval_ref_flip"])}
late = [r for r in dec if r["kind"] == "kill" and r["first_ref_clean_t"] is not None]
S["convergence"] = {"kill_runs_ending_clean": len(late),
                    "clean_from_first_snapshot": sum(1 for r in late if r["first_ref_clean_t"] <= 3.5),
                    "first_clean_after_33.8s": sum(1 for r in late if r["first_ref_clean_t"] > 33.8),
                    "max_first_clean_t": max([r["first_ref_clean_t"] for r in late], default=None)}
pr = [r for r in ok if r.get("probe_sound") is not None]
S["upf_probe"] = {"runs": len(pr), "sound": sum(1 for r in pr if r["probe_sound"]),
                  "exact_match": sum(1 for r in pr if r["probe_exact"]),
                  "changed_during_probe": sum(1 for r in pr if r["probe_changed"])}
S["disagreeing_snapshots"] = len(dis)
pers = [r for r in dec if r["ref"] == "persistent"]
S["ref_persistent_breakdown"] = {
    "with_upf_identity_conjunct": sum(1 for r in pers if "REF-S-P" in r["ref_labels_cp2"]),
    "shared_readouts_only": sum(1 for r in pers if "REF-S-P" not in r["ref_labels_cp2"]),
    "by_victim": dict(collections.Counter(r["nf"] for r in pers)),
    "labels": dict(collections.Counter(r["ref_labels_cp2"] for r in pers))}
S["upf_identity_conjunct_stable_polls_violated"] = sum(1 for s_ in st if "REF-S-P" in s_["ref"])
S["upf_identity_conjunct_stable_polls_flagged_by_count_rule"] = sum(1 for s_ in st if "REF-S-P" in s_["ref"] and s_["count_viol"])
S["liveness_missed_by_victim"] = dict(collections.Counter(r["nf"] + "/" + r["proc"] for r in pers if not r["liveness_flag"]))
json.dump(S, open(os.path.join(R, PFX + "_summary.json"), "w"), indent=1)
print(json.dumps(S, indent=1))
