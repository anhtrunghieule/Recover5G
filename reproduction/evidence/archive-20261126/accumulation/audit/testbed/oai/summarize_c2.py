#!/usr/bin/env python3
"""Summarise campaign-2 OAI runs: oai_c2.jsonl + decoded pcaps -> oai_c2.csv (one row per run)."""
import csv
import gzip
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "..", "results", "real", "campaign2", "oai"))


def pfcp_rows(rid):
    p = os.path.join(OUT, "decoded", f"{rid}_pfcp.csv")
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return list(csv.DictReader(f, delimiter="|"))


def sections(r):
    """NF sections of the saved run log (full text, unlike the truncated *_evidence lists)."""
    txt = gzip.open(os.path.join(OUT, r["logs"]), "rt").read()
    out, cur = {}, None
    for line in txt.splitlines():
        m = re.match(r"===== (\S+) =====", line)
        if m:
            cur = m.group(1)
            out[cur] = []
            continue
        if cur:
            out[cur].append(line)
    return {k: "\n".join(v) for k, v in out.items()}


def main():
    recs = [json.loads(l) for l in open(os.path.join(OUT, "oai_c2.jsonl"))]
    rows = []
    for r in recs:
        rid = r["id"]
        kill = None
        pf = pfcp_rows(rid)
        # kill epoch: from t_kill_utc is ambiguous (no date) -> use AssocSetupReq ordering instead
        smf_assoc = [x for x in pf if x["msg"] == "AssocSetupReq"]
        rts = [x["recovery_time_stamp"].replace(" UTC", "") for x in smf_assoc]
        series = r.get("series", [])
        probes = [all(u["rt_ok"].values()) for s in series for u in s["ues"].values() if u["rt_ok"]]
        any_sess = [bool(u["sessions"]) for s in series for u in s["ues"].values()]
        sec = sections(r)
        logs = sec.get("oai-smf", "") + sec.get("oai-upf", "")
        row = {
            "id": rid, "scenario": r["scenario"], "rep": r["rep"], "k": r["k"], "downtime_s": r["downtime"],
            "upf_image": r["upf_image"], "smf_image": r["smf_image"], "t_kill_vm_utc": r["t_kill_utc"],
            "restart_ready_s": round(r["restart_ready_s"], 2) if r.get("restart_ready_s") else None,
            "window_s": series[-1]["t"] if series else None, "samples": len(series),
            "probe_ok_frac": round(sum(probes) / len(probes), 2) if probes else None,
            "ue_ps_active_all_samples": all(any_sess) if any_sess else None,
            "smf_assoc_setup_reqs": len(smf_assoc),
            "smf_node_id": ";".join(sorted({x["node_id_fqdn"] or x["node_id_ipv4"] for x in smf_assoc})),
            "smf_rts_sequence": ";".join(rts),
            "pfcp_sess_del_reqs": sum(1 for x in pf if x["msg"] == "SessDelReq"),
            "pfcp_sess_est_rejected": sum(1 for x in pf if x["msg"] == "SessEstRsp" and x["cause"] not in ("1", "")),
            "upf_replaced_assoc_deletions": ";".join(re.findall(r"Deleting (\d+) PFCP sessions of a replaced association", logs)),
            "smf_ctx_not_exist_warnings": len(re.findall(r"does not exit", logs)),
            "smf_upf_rejected_est": len(re.findall(r"was rejected by UPF", logs)),
        }
        nu = r.get("next_use", {})
        if nu:
            row["release_cleared_ue"] = all(not u["sessions"] or set(u["sessions"]) != set(r["before"][i]["sessions"])
                                            for i, u in nu["after_release"].items())
            row["next_use_variant"] = "existing-psi (r1 predates the new-PSI check)" if r["id"] == "o1-r1" else "new-psi"
            row["new_psi_after_release"] = ";".join(
                f"UE{k[3:]}:{'ok ' + str(v[1]) if v and v[0] is not None else 'FAIL'}"
                for k, v in nu.items() if k.startswith("est"))
        if r["scenario"].startswith("i33"):
            ue2 = r.get("ue2_new_session") or [None, None]
            row["ue2_new_psi"] = json.dumps(ue2[1])
            row["amf_new_ref"] = ";".join(re.findall(r"sm-contexts/(\d+)", " ".join(r.get("amf_refs_after_ue2_new", []))))
            ev = sec.get("oai-smf", "")
            row["smf_release_ref"] = ";".join(re.findall(r"smf_ref (\d+), method release", ev))
            row["smf_ue_initiated_release_on_ref1"] = len(re.findall(r"PDU Session Release \(UE-Initiated\), processing", ev))
            row["smf_released_pdu_session_id"] = ";".join(re.findall(r"Release SM Context Request\): pdu-session-id (\d+)", ev))
            amf = sec.get("oai-amf", "")
            row["amf_release_uri"] = ";".join(re.findall(r"sm-contexts/\d+/release", amf))
            fin = r.get("final", {}).get("2", {})
            row["ue2_final_sessions"] = json.dumps(fin.get("sessions"))
            row["ue2_final_probe"] = json.dumps(fin.get("rt_ok"))
            row["victim_session_released"] = ("2" in row["smf_released_pdu_session_id"].split(";")
                                              and "imsi-208950000000032" in ev)
        rows.append(row)
    keys = []
    for row in rows:
        for k in row:
            if k not in keys:
                keys.append(k)
    with open(os.path.join(OUT, "oai_c2.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    for row in rows:
        print(row)


if __name__ == "__main__":
    main()
