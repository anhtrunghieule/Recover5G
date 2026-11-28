#!/usr/bin/env python3
"""Campaign 2 replication of measure.py lazy (SMF crash at steady state, then UE actions), identity-level, with pcap.
UE1: release PSI 1 + re-establish; UE2: deregister (UERANSIM re-registers) + establish. Lazy repair counts only if
R (count and identity) is clean AND every UE action succeeded.
  R5G_INST=4 python3 c2/lazy_c2.py --runs 5
"""
import argparse, gzip, json, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from r5g import capture, dock, observe, oracle, runner, testbed, workload  # noqa
from r5g.testbed import CORE_NFS, c  # noqa
OUT = runner.RESULTS
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def sn(ues):
    s = oracle.snapshot_id(ues)
    return {"viol": [v[0] for v in oracle.check_R(s)], "vid": [list(v) for v in oracle.check_R_id(s)],
            "amf_id": s["amf_id"], "smf_id": s["smf_id"], "ues": s["ues"], "dl_ok": s["dl_ok"]}


def one(rid, nf):
    ues = [1, 2]; t0 = time.time()
    pc = os.path.join(OUT, "pcap", f"{rid}.pcap"); capture.start(pc)
    runner.reset(); runner.bring_to("session", ues)
    dock.kill(c(nf)); dock.start(c(nf)); time.sleep(30)
    rec = {"id": rid, "nf": nf, "before": sn(ues)}
    acts = {"ue1_release": workload.ps_release_all(1)[1], "ue2_dereg": workload.deregister(2)[1]}
    time.sleep(8)
    workload.ps_establish(1); acts["ue1_session"] = workload.wait_session(1, 25)
    acts["ue2_registered"] = workload.wait_registered(2, 30); time.sleep(2)
    workload.ps_establish(2); acts["ue2_session"] = workload.wait_session(2, 25)
    time.sleep(3)
    rec["actions"] = acts; rec["after"] = sn([1, 2])
    ok = all(v and v[0] is not None for k, v in acts.items() if k.endswith("_session")) and acts["ue2_registered"] is not None
    rec["next_use_all_ok"] = bool(ok)
    rec["service_ok"] = all(rec["after"]["dl_ok"].values()) if rec["after"]["dl_ok"] else False
    rec["lazy_repair_v2"] = ok and not rec["after"]["viol"] and not rec["after"]["vid"]
    lp = os.path.join(OUT, "logs", f"{rid}.log.gz"); os.makedirs(os.path.dirname(lp), exist_ok=True)
    with gzip.open(lp, "wt") as f:
        for n in CORE_NFS + ["gnb"]:
            f.write(f"\n===== {n} =====\n" + ANSI.sub("", dock.logs(c(n), since=t0)))
        f.write("\n===== ue =====\n" + dock.dexec(c("ue"), "tail -n 200 /tmp/ue*.log").stdout)
    rec["logs"] = os.path.relpath(lp, OUT); rec["pcap"] = os.path.relpath(capture.stop(pc), OUT)
    rec["wall_s"] = round(time.time() - t0, 1)
    return rec


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--runs", type=int, default=5); p.add_argument("--nf", default="smf")
    p.add_argument("--image", default="r5g/open5gs:e85748e")
    a = p.parse_args(); testbed.up(image=a.image)
    for r in range(1, a.runs + 1):
        rid = f"LAZY-{a.nf}-{a.image.split(':')[-1]}-r{r}"
        try:
            rec = one(rid, a.nf)
        except Exception as e:
            rec = {"id": rid, "error": f"{type(e).__name__}: {e}"}
        with open(os.path.join(OUT, "lazy_c2.jsonl"), "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        print(rid, rec.get("error"), rec.get("next_use_all_ok"), rec.get("lazy_repair_v2"),
              rec.get("after", {}).get("vid"), flush=True)
