#!/usr/bin/env python3
"""Revision 2026-11-25: evaluation of the orphan-session replication (exp/orphan_repl.py, exp/orphan_oai.py).

Per run, three independent kinds of evidence:
  service   both UEs hold a new session and its downlink and uplink probes succeed at both checkpoints (record)
  state     UPF / SMF / AMF / UE session counts at both checkpoints (record); residue = UPF count above SMF count
  wire      PFCP sessions in establishment order from the capture; the first two are the pre-fault ("old")
            sessions. "old deleted" = each old session received an accepted PFCP Session Deletion.
Writes orphan_eval.csv (one row per run) and orphan_summary.csv (one row per condition).

  python3 exp/orphan_eval.py <dir with orphan_repl.jsonl> [<dir with orphan_oai.jsonl>]
"""
import collections, csv, gzip, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from c2 import pcap_ids  # noqa


def wire(pcap):
    ids = (pcap[:-3] if pcap.endswith(".gz") else pcap) + ".ids.json"
    if os.path.exists(ids):
        o = json.load(open(ids))
    else:
        o = pcap_ids.decode(pcap); json.dump(o, open(ids, "w"), default=str)
    pf = [p for p in o["pfcp"] if "|" not in p["src"]]
    sess, pend, dpend, deleted = [], {}, {}, set()
    for p in pf:
        if p["type"] == 50:
            pend[p["seq"]] = p
        elif p["type"] == 51 and p["seq"] in pend and p["cause"].split("|")[0] == "1":
            q = pend.pop(p["seq"]); s = p["seid"].split("|")
            sess.append({"t": q["t"], "ip": q["ue_ip"].split("|")[0], "up": s[1] if len(s) > 1 else None})
        elif p["type"] == 54:
            dpend[p["seq"]] = p
        elif p["type"] == 55 and p["seq"] in dpend and p["cause"].split("|")[0] == "1":
            deleted.add(dpend.pop(p["seq"])["seid"].split("|")[0])
    return sess, deleted, len([p for p in pf if p["type"] == 54])


rows = []
for root in sys.argv[1:]:
    for name in ("orphan_repl.jsonl", "orphan_oai.jsonl"):
        fp = os.path.join(root, name)
        if not os.path.exists(fp):
            continue
        for l in open(fp):
            r = json.loads(l)
            if "pilot" in r["id"]:
                continue
            tag = r.get("tag", "")
            row = {"id": r["id"], "condition": tag, "ran": "OAI gNB + OAI UE" if name == "orphan_oai.jsonl" else
                   ("UERANSIM, patched gNB" if "p2" in tag else
                    ("UERANSIM, stock gNB restarted" if "p1r" in tag else "UERANSIM, stock gNB not restarted")),
                   "build": "repair" if "repair" in tag else "e85748e", "fault": r.get("fault", ""), "error": r.get("error", "")}
            if r.get("error"):
                rows.append(row); continue
            sess, deleted, ndel = wire(os.path.join(root, r["pcap"]))
            old = sess[:2]
            cps = r["checkpoints"]
            row.update({
                "gnb_survived": r.get("gnb_running_after_fault"),
                "gnb_restarted_by_harness": r.get("gnb_restarted_by_harness"),
                "new_sessions_work": r.get("new_sessions_work"),
                "ue_sess": "/".join(str(sum(1 for v in (cp.get("ue_ips") or {i: (x.get("sessions") or None) for i, x in cp.get("ues", {}).items()}).values() if v)) for cp in cps),
                "amf_sess": "/".join(str(cp["counts"].get("amf_sess")) for cp in cps),
                "smf_sess": "/".join(str(cp["counts"].get("smf_sess")) for cp in cps),
                "upf_sess": "/".join(str(cp["counts"].get("upf_sess")) for cp in cps),
                "residue_both_checkpoints": all((cp["counts"].get("upf_sess") or 0) > (cp["counts"].get("smf_sess") or 0) for cp in cps),
                "proxy_viol": " | ".join(",".join(cp.get("viol", [])) for cp in cps) if "viol" in cps[0] else "",
                "wire_sessions": len(sess), "wire_deletions": ndel,
                "old_deleted": sum(1 for s in old if s["up"] in deleted),
                "old_all_deleted": len(old) == 2 and all(s["up"] in deleted for s in old),
                "pcap": r["pcap"], "logs": r["logs"]})
            # mechanism signature in the SMF log: the code path that removes an old session locally
            with gzip.open(os.path.join(root, r["logs"]), "rt", errors="replace") as lf:
                txt = lf.read()
            row["smf_old_session_warnings"] = txt.count("OLD Session Will Release")
            row["repair_deletions_logged"] = txt.count("F12-repair: PFCP deletion")
            rows.append(row)
out = sys.argv[1]
keys = []
for x in rows:
    for k in x:
        if k not in keys:
            keys.append(k)
with open(os.path.join(out, "orphan_eval.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)
g = collections.OrderedDict()
for x in rows:
    g.setdefault((x["ran"], x["build"], x["fault"]), []).append(x)
summ = []
for (ran, build, fault), xs in g.items():
    ok = [x for x in xs if not x["error"]]
    summ.append({"ran": ran, "build": build, "fault": fault, "runs": len(xs), "errors": len(xs) - len(ok),
                 "new_sessions_work": sum(1 for x in ok if x["new_sessions_work"]),
                 "residue_both_checkpoints": sum(1 for x in ok if x["residue_both_checkpoints"]),
                 "old_sessions_all_deleted_on_wire": sum(1 for x in ok if x["old_all_deleted"]),
                 "runs_with_two_old_session_warnings": sum(1 for x in ok if x["smf_old_session_warnings"] == 2),
                 "gnb_survived": sum(1 for x in ok if x["gnb_survived"]),
                 "gnb_restarted_by_harness": sum(1 for x in ok if x["gnb_restarted_by_harness"]),
                 "upf_sess_values": ",".join(sorted({x["upf_sess"] for x in ok})),
                 "smf_sess_values": ",".join(sorted({x["smf_sess"] for x in ok}))})
with open(os.path.join(out, "orphan_summary.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(summ[0].keys())); w.writeheader(); w.writerows(summ)
for s in summ:
    print(s)
