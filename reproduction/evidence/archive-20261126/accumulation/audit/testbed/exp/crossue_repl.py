#!/usr/bin/env python3
"""Revision 2026-11-25: replication of the cross-UE deletion (reference reuse after an SMF restart) on a fresh VM,
with the two ablations the paper reports. Recipe after c2/alias.py. No netem delay is used.

  full        UE1, UE2 hold PSI 1 -> SMF SIGKILL + start -> UE2 establishes PSI 2 -> UE1 releases PSI 1
  norestart   the same steps without the SMF restart
  nonewsess   SMF restart, UE2 establishes nothing new, UE1 releases PSI 1

Outcome per run: is UE2's newest session still present at the SMF, at the UE, and does its downlink work?
Wire evidence is extracted offline (exp/crossue_eval.py): the reference issued to UE2's new session, the release
request sent for UE1, and the PFCP deletion that follows.

  . ../env.sh; R5G_INST=3 python3 exp/crossue_repl.py --runs 5
"""
import argparse, gzip, json, os, re, sys, time, traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from r5g import capture, dock, observe, oracle, runner, testbed, workload  # noqa
from r5g.testbed import CORE_NFS, c, imsi  # noqa

OUT = runner.RESULTS
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def snap(ues):
    s = oracle.snapshot_id(ues, probes=True)
    return {"t": time.time(), "smf_id": s["smf_id"], "amf_id": s["amf_id"], "ues": s["ues"], "dl_ok": s["dl_ok"],
            "counts": s["counts"], "vid": [list(v) for v in oracle.check_R_id(s)],
            "viol": [v[0] for v in oracle.check_R(s)]}


def one(rid, variant, trigger):
    ues = [1, 2]
    rec = {"id": rid, "variant": variant, "trigger": trigger}
    t_begin = time.time()
    pc = os.path.join(OUT, "pcap", f"{rid}.pcap")
    capture.start(pc)
    runner.reset(0)
    runner.bring_to("session", ues)
    time.sleep(2)
    rec["before"] = snap(ues)
    t_k = time.time()
    if variant != "norestart":
        dock.kill(c("smf")); dock.start(c("smf"))
        observe.wait_for_log("smf", r"PFCP associated", t_k, timeout=30)
    time.sleep(3)
    rec["after_restart"] = snap(ues)
    new_psi, ip = None, None
    if variant != "nonewsess":
        workload.ps_establish(2)
        tt, ip = workload.wait_session(2, 30, psi=2)
        new_psi = 2
        rec["ue2_new"] = {"t": tt, "ip": ip, "psi": 2}
        time.sleep(2)
    rec["before_trigger"] = snap(ues)
    t_trig = time.time(); rec["t_trigger"] = t_trig
    rec["trigger_out"] = workload.deregister(1)[1] if trigger == "dereg" else workload.ps_release(1, 1)[1]
    time.sleep(12)
    rec["after_trigger"] = snap(ues)
    smf2 = (rec["after_trigger"]["smf_id"] or {}).get(imsi(2), {})
    ue2 = {int(k): v for k, v in rec["after_trigger"]["ues"].get(2, {}).get("sessions", {}).items()}
    target = new_psi or 1                      # the session of UE2 that must survive UE1's release
    rec["ue2_target_psi"] = target
    rec["ue2_at_smf"] = (target in {int(k) for k in smf2}) if rec["after_trigger"]["smf_id"] is not None else None
    rec["ue2_at_ue"] = target in ue2
    tip = ue2.get(target) or ip
    rec["ue2_dl_ok"] = observe.dl_probe(tip) if tip else None
    rec["ue2_ul_ok"] = observe.ul_probe(tip) if tip else None
    rec["cross_ue_deletion"] = bool(rec["ue2_at_ue"] and rec["ue2_at_smf"] is False)
    lp = os.path.join(OUT, "logs", f"{rid}.log.gz"); os.makedirs(os.path.dirname(lp), exist_ok=True)
    with gzip.open(lp, "wt") as f:
        for n in CORE_NFS + ["gnb"]:
            f.write(f"\n===== {n} =====\n" + ANSI.sub("", dock.logs(c(n), since=t_begin)))
        f.write("\n===== ue =====\n" + dock.dexec(c("ue"), "tail -n 200 /tmp/ue*.log").stdout)
    rec["logs"] = os.path.relpath(lp, OUT); rec["pcap"] = os.path.relpath(capture.stop(pc), OUT)
    rec["wall_s"] = round(time.time() - t_begin, 1)
    return rec


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--runs", type=int, default=5); p.add_argument("--image", default="r5g/open5gs:e85748e")
    p.add_argument("--variants", default="full,norestart,nonewsess"); p.add_argument("--trigger", default="rel")
    a = p.parse_args()
    os.makedirs(OUT, exist_ok=True)
    jp = os.path.join(OUT, "crossue_repl.jsonl")
    done = set()
    if os.path.exists(jp):
        for line in open(jp):
            try:
                d = json.loads(line)
                if not d.get("error"):
                    done.add(d["id"])
            except Exception:
                pass
    testbed.up(image=a.image)
    for r in range(1, a.runs + 1):
        for v in a.variants.split(","):
            rid = f"crossue-{v}-{a.trigger}-r{r}"
            if rid in done:
                continue
            try:
                rec = one(rid, v, a.trigger)
            except Exception as e:
                rec = {"id": rid, "variant": v, "error": f"{type(e).__name__}: {e}", "tb": traceback.format_exc()[-800:]}
                try:
                    capture.stop(os.path.join(OUT, "pcap", f"{rid}.pcap"))
                except Exception:
                    pass
            rec["image"] = a.image
            with open(jp, "a") as f:
                f.write(json.dumps(rec, default=str) + "\n")
            print(rid, {k: rec.get(k) for k in ["ue2_new", "ue2_at_smf", "ue2_at_ue", "ue2_dl_ok", "ue2_ul_ok",
                                               "cross_ue_deletion", "error"]}, flush=True)
