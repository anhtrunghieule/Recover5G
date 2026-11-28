#!/usr/bin/env python3
"""Revision 2026-11-25: wire evaluation of exp/crossue_repl.py runs.

Per run, from the capture only:
  * the PFCP session of each UE IP (CP SEID, UP SEID) in establishment order;
  * the smContextRef issued for each POST /sm-contexts and the SMF incarnation that issued it;
  * the requests the AMF sends to /sm-contexts/{ref}/... after UE1's trigger and their status codes;
  * every PFCP Session Deletion Request and the session (UE IP) its SEID belongs to.
A run counts as a cross-UE deletion when the only release in the run is UE1's and a PFCP deletion removes the
session that carries UE2's newest address. The record supplies what the UE saw afterwards (session still listed
at the UE, downlink and uplink probes).
"""
import csv, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from c2 import pcap_ids  # noqa

R = sys.argv[1]
rows = []
for l in open(os.path.join(R, "crossue_repl.jsonl")):
    r = json.loads(l)
    if r.get("error"):
        rows.append({"id": r["id"], "variant": r.get("variant"), "error": r["error"]}); continue
    pc = os.path.join(R, r["pcap"]); ids = pc[:-3] + ".ids.json"
    if os.path.exists(ids):
        o = json.load(open(ids))
    else:
        o = pcap_ids.decode(pc); json.dump(o, open(ids, "w"), default=str)
    pf = [p for p in o["pfcp"] if "|" not in p["src"]]
    sess, pend = [], {}
    for p in pf:
        if p["type"] == 50:
            pend[p["seq"]] = p
        elif p["type"] == 51 and p["seq"] in pend and p["cause"].split("|")[0] == "1":
            q = pend.pop(p["seq"]); s = p["seid"].split("|")
            sess.append({"t": q["t"], "ip": q["ue_ip"].split("|")[0], "cp": s[0], "up": s[1] if len(s) > 1 else None})
    dels = [p for p in pf if p["type"] == 54]
    by_up = {s["up"]: s for s in sess}
    del_ips = [by_up.get(d["seid"].split("|")[0], {}).get("ip", "?") for d in dels]
    del_order = [sess.index(by_up[d["seid"].split("|")[0]]) + 1 if d["seid"].split("|")[0] in by_up else None for d in dels]
    refs = [f"{x['ref']}@inc{x['smf_incarnation']}" for x in o["refs_issued"]]
    t_last_est = sess[-1]["t"] if sess else 0
    amf_ip_suffix = ".5"
    after = [u for u in o["ref_uses"] if u["t"] > t_last_est + 1.0 and u["src"].endswith(amf_ip_suffix)]
    ue2_new_ip = (r.get("ue2_new") or {}).get("ip")
    ue2_ips = list((r["before_trigger"]["ues"].get("2") or r["before_trigger"]["ues"].get(2) or {}).get("sessions", {}).values())
    ue1_ips = list((r["before_trigger"]["ues"].get("1") or r["before_trigger"]["ues"].get(1) or {}).get("sessions", {}).values())
    # the session that carries UE2's newest address is the LAST establishment with that IP
    last_for_ip = {}
    for i, s in enumerate(sess):
        last_for_ip[s["ip"]] = i + 1
    deleted_new_ue2 = bool(ue2_new_ip and any(o_ == last_for_ip.get(ue2_new_ip) for o_ in del_order)
                           and len(sess) >= 3)
    at = r["after_trigger"]
    smf2 = (at["smf_id"] or {}).get("imsi-999700000000002", {})
    rows.append({
        "id": r["id"], "variant": r["variant"], "error": "",
        "sessions_established": ";".join(f"{i+1}:{s['ip']}" for i, s in enumerate(sess)),
        "refs_issued": ";".join(refs), "refs_reused": ";".join(o["refs_reused_across_incarnations"]),
        "amf_requests_after_trigger": ";".join(f"{u['path'].split('/v1/')[-1]}->{u['status']}" for u in after),
        "pfcp_deletions": len(dels), "deleted_session_order": ";".join(str(x) for x in del_order),
        "deleted_ips": ";".join(del_ips), "ue1_ips_before_trigger": ";".join(ue1_ips),
        "ue2_ips_before_trigger": ";".join(ue2_ips), "ue2_new_ip": ue2_new_ip or "",
        "wire_cross_ue_deletion": deleted_new_ue2,
        "ue2_target_listed_at_ue": r.get("ue2_at_ue"), "ue2_dl_ok": r.get("ue2_dl_ok"), "ue2_ul_ok": r.get("ue2_ul_ok"),
        "smf_ue2_after": json.dumps(smf2), "upf_sess_after": at["counts"].get("upf_sess"),
        "smf_sess_after": at["counts"].get("smf_sess"), "proxy_after": ";".join(sorted(set(at["viol"]))),
        "gtpu_error_indications": len(o["gtpu_error_indication"]), "pcap": r["pcap"], "logs": r["logs"]})
keys = []
for x in rows:
    for k in x:
        if k not in keys:
            keys.append(k)
with open(os.path.join(R, "crossue_eval.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)
for x in rows:
    print(x["id"], x.get("error") or (x["sessions_established"], x["refs_issued"], "after:", x["amf_requests_after_trigger"],
          "del:", x["deleted_session_order"], x["deleted_ips"], "X-UE:", x["wire_cross_ue_deletion"],
          "ue2 dl/ul", x["ue2_dl_ok"], x["ue2_ul_ok"], "upf", x["upf_sess_after"]))
