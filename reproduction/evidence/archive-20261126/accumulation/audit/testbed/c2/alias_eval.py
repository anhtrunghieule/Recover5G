#!/usr/bin/env python3
"""Campaign 2: per alias run, identity-level evidence from the pcap: after UE2's new PSI 2 got smContextRef X in the
restarted SMF, did a request issued in UE1's context to /sm-contexts/X/... lead to PFCP deletion of UE2's session?
Writes alias/alias_eval.csv."""
import csv, json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
R = os.path.join(HERE, "..", "..", "results", "real", "campaign2", "alias")
rows = []
for l in open(os.path.join(R, "alias.jsonl")):
    r = json.loads(l)
    if r.get("error"):
        continue
    pc = os.path.join(R, r["pcap"])
    ids = pc[:-3] + ".ids.json"
    if not os.path.exists(ids):
        subprocess.run([sys.executable, os.path.join(HERE, "pcap_ids.py"), pc], capture_output=True)
    o = json.load(open(ids))
    ip2 = (r.get("ue2_psi2") or {}).get("ip")
    est = [p for p in o["pfcp"] if p["type"] == 50 and p["ue_ip"] == ip2]
    t_est = est[-1]["t"] if est else None
    # UP SEID of UE2's PSI 2 session = SEID in the establishment response that follows (type 51, same seq)
    rsp = [p for p in o["pfcp"] if p["type"] == 51 and t_est and p["t"] >= t_est and p["seq"] == est[-1]["seq"]]
    new_ref = [x["ref"] for x in o["refs_issued"] if t_est and x["t"] <= t_est + 1 and x["t"] >= t_est - 5]
    t_trig = r["after_ue2_psi2"] and None
    after = [u for u in o["ref_uses"] if t_est and u["t"] > t_est + 1 and u["src"].endswith(".5")]
    dels = [p for p in o["pfcp"] if p["type"] == 54 and t_est and p["t"] > t_est + 1]
    rows.append({"id": r["id"], "variant": r["variant"], "image": r.get("image"), "ue2_psi2_ip": ip2,
                 "ue2_psi2_ref": ";".join(new_ref), "refs_issued": ";".join(f"{x['ref']}@inc{x['smf_incarnation']}" for x in o["refs_issued"]),
                 "amf_requests_after": ";".join(f"{u['method']} {u['path'].split('/v1/')[-1]} -> {u['status']}" for u in after),
                 "pfcp_deletions_after": len(dels), "ue2_session_at_smf_after": r.get("ue2_psi2_survives_at_smf"),
                 "ue2_smf_state_after": json.dumps((r["after_trigger"]["smf_id"] or {}).get("imsi-999700000000002", {})),
                 "ue2_active_at_ue": r.get("ue2_psi2_active_at_ue"), "pcap": r["pcap"], "logs": r["logs"]})
with open(os.path.join(R, "alias_eval.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
for x in rows:
    print(x["id"], x["ue2_psi2_ref"], "|", x["amf_requests_after"], "| PFCPdel", x["pfcp_deletions_after"], "| smf", x["ue2_smf_state_after"])
