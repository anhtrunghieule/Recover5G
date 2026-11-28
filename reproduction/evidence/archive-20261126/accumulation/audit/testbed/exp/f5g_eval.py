#!/usr/bin/env python3
"""Revision 2026-11-25: evaluation of the free5GC next-use runs (exp/f5g_control.py).

Two readings of "the release removes the old session" are reported, because the UERANSIM UE in this setup has
PSI 1 in its configured session list and sets it up again by itself as soon as it is released:
  literal   PSI 1 is not listed at the UE 6 s after the release request (the paper's wording)
  identity  the session that carried the pre-release address is gone 6 s after the release request, i.e. PSI 1
            is absent or carries a different address; plus whether the UE logged a Release Command
A new session "works" if some PS-ACTIVE session answers an uplink ping at the end.
Writes f5g_eval.csv and f5g_summary.json.
"""
import collections, csv, gzip, json, os, re, sys

R = sys.argv[1]
rows = []
for l in open(os.path.join(R, "f5g_control.jsonl")):
    r = json.loads(l)
    row = {"id": r["id"], "nf": r["nf"], "error": r.get("error", "")}
    if r.get("after_release") is None:
        rows.append(row); continue
    fin = {int(k): v for k, v in r["final"]["ue_sessions"].items()}
    ar = {int(k): v for k, v in r["after_release"]["ue_sessions"].items()}
    an = {int(k): v for k, v in r["after_next_use"]["ue_sessions"].items()}
    old_ip = fin.get(1) or {int(k): v for k, v in r["before"]["ue_sessions"].items()}.get(1)
    ue = ""
    try:
        with gzip.open(os.path.join(R, r["logs"]), "rt", errors="replace") as f:
            txt = f.read()
        ue = txt.split("===== ue =====")[-1]
    except Exception:
        pass
    rel_req = [m.start() for m in re.finditer(r"Sending PDU Session Release Request for PSI\[1\]", ue)]
    after_req = ue[rel_req[-1]:] if rel_req else ""
    row.update({
        "service_holds": r.get("service_holds"), "psi1_at_end_of_window": 1 in fin, "old_ip": old_ip or "",
        "literal_old_psi_removed": 1 not in ar,
        "identity_old_session_gone": bool(old_ip) and ar.get(1) != old_ip,
        "release_request_sent": bool(rel_req), "release_command_received": "PDU Session Release Command received" in after_req,
        "release_rejected_or_no_answer": bool(rel_req) and "PDU Session Release Command received" not in after_req,
        "psi1_ip_after_release": ar.get(1, ""), "sessions_after_next_use": json.dumps(an),
        "new_session_works": any(r["after_next_use"]["ul_ok"].get(str(p)) or r["after_next_use"]["ul_ok"].get(p) for p in an),
    })
    row["next_use_literal"] = row["literal_old_psi_removed"] and row["new_session_works"]
    row["next_use_identity"] = row["identity_old_session_gone"] and row["new_session_works"]
    rows.append(row)
keys = []
for x in rows:
    for k in x:
        if k not in keys:
            keys.append(k)
with open(os.path.join(R, "f5g_eval.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)
S = {}
for nf in ("none", "smf", "upf", "amf"):
    xs = [x for x in rows if x["nf"] == nf]
    ok = [x for x in xs if "next_use_literal" in x and not x["error"]]
    if not xs:
        continue
    S[nf] = {"runs": len(xs), "valid": len(ok),
             **{k: sum(1 for x in ok if x[k]) for k in ("service_holds", "literal_old_psi_removed", "identity_old_session_gone",
                                                         "release_command_received", "new_session_works", "next_use_literal",
                                                         "next_use_identity")}}
json.dump(S, open(os.path.join(R, "f5g_summary.json"), "w"), indent=1)
print(json.dumps(S, indent=1))
