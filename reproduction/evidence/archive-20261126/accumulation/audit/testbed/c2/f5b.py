#!/usr/bin/env python3
"""Campaign 2 F5b follow-up (R1 N3): AMF SIGKILL + immediate restart with 2 UEs holding sessions (patched gNB),
then drive UE re-registration (power-cycle: initial registration, no PDU session) and a new PDU session; check for
orphan SMF sessions / UPF sessions / leaked UE IPs by identity (SMF /pdu-info) at +72 s after re-registration.
  UERANSIM_IMAGE=r5g/ueransim:4f45e18-p2 R5G_INST=4 python3 c2/f5b.py --runs 5
"""
import argparse, gzip, json, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from r5g import capture, dock, observe, oracle, runner, testbed, workload  # noqa
from r5g.testbed import CORE_NFS, c, imsi  # noqa
OUT = runner.RESULTS
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def sn(ues):
    s = oracle.snapshot_id(ues)
    return {"viol": [v[0] for v in oracle.check_R(s)], "vid": [list(v) for v in oracle.check_R_id(s)],
            "amf_id": s["amf_id"], "smf_id": s["smf_id"], "ues": s["ues"], "dl_ok": s["dl_ok"], "counts": s["counts"]}


def one(rid):
    ues = [1, 2]; t0 = time.time()
    pc = os.path.join(OUT, "pcap", f"{rid}.pcap"); capture.start(pc)
    runner.reset(); runner.bring_to("session", ues)
    rec = {"id": rid, "before": sn(ues)}
    old_ips = {i: v["sessions"] for i, v in rec["before"]["ues"].items()}
    tk = time.time(); dock.kill(c("amf")); dock.start(c("amf"))
    time.sleep(15)
    rec["gnb_running"] = dock.running(c("gnb"))
    rec["after_amf_restart"] = sn(ues)
    rec["gnb_log"] = [l for l in ANSI.sub("", dock.logs(c("gnb"), since=tk)).splitlines() if re.search(r"r5g|NG Setup|Association|SCTP|error|ERROR", l)][:20]
    # re-registration: power-cycle each UE (initial registration with SUCI), then a new PDU session
    for i in ues:
        workload.power_off(i)
    time.sleep(2)
    for i in ues:
        workload.power_on(i)
    rec["rereg"] = {i: workload.wait_registered(i, 40) for i in ues}
    time.sleep(2)
    for i in ues:
        workload.ps_establish(i)
    rec["new_session"] = {i: workload.wait_session(i, 30) for i in ues}
    time.sleep(72)
    rec["final"] = sn(ues)
    smf = rec["final"]["smf_id"] or {}
    new = {i: (rec["new_session"][i][1] if rec["new_session"][i] else None) for i in ues}
    rec["old_ips"] = old_ips; rec["new_ips"] = new
    rec["smf_sessions_final"] = {u: {p: b["ip"] for p, b in d.items()} for u, d in smf.items()}
    rec["orphan_old_sessions"] = sum(1 for u, d in smf.items() for p, b in d.items()
                                     if b["ip"] not in [x for x in new.values() if x])
    rec["upf_sess_final"] = rec["final"]["counts"].get("upf_sess")
    lp = os.path.join(OUT, "logs", f"{rid}.log.gz"); os.makedirs(os.path.dirname(lp), exist_ok=True)
    with gzip.open(lp, "wt") as f:
        for n in CORE_NFS + ["gnb"]:
            f.write(f"\n===== {n} =====\n" + ANSI.sub("", dock.logs(c(n), since=t0)))
        f.write("\n===== ue =====\n" + dock.dexec(c("ue"), "tail -n 200 /tmp/ue*.log").stdout)
    rec["logs"] = os.path.relpath(lp, OUT); rec["pcap"] = os.path.relpath(capture.stop(pc), OUT)
    rec["wall_s"] = round(time.time() - t0, 1)
    return rec


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--runs", type=int, default=5)
    a = p.parse_args()
    for r in range(1, a.runs + 1):
        rid = f"F5B-rereg-r{r}"
        try:
            rec = one(rid)
        except Exception as e:
            import traceback
            rec = {"id": rid, "error": f"{type(e).__name__}: {e}", "tb": traceback.format_exc()[-600:]}
        with open(os.path.join(OUT, "f5b.jsonl"), "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        print(rid, {k: rec.get(k) for k in ["error", "gnb_running", "rereg", "new_session", "orphan_old_sessions",
                                           "smf_sessions_final", "upf_sess_final"]}, flush=True)
