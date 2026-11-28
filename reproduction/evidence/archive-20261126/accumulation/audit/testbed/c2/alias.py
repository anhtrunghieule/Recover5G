#!/usr/bin/env python3
"""Campaign 2: Open5GS smContextRef reuse after an SMF restart (OAI #33 analog) -- does a stale AMF ref act on
another UE's session?

Source facts (campaign2/source_facts.md): smContextRef = smf_sess_pool slot index (src/smf/context.c:1763); the pool is
re-initialised at start, so the first session after a restart gets ref "1"; the SMF resolves /sm-contexts/{ref}/...
by index only (smf_sess_find_by_sm_context_ref, context.c:2310).

Steps: UE1, UE2 with PSI 1 (refs 1, 2) -> SMF SIGKILL + immediate start -> UE2 establishes PSI 2 (new SMF: ref 1)
-> trigger by UE1 (variant 'dereg': deregister; 'rel': ps-release 1) -> observe whether UE2's PSI 2 survives.

  R5G_INST=6 python3 c2/alias.py --variant dereg --runs 3 --image r5g/open5gs:e85748e
"""
import argparse, gzip, json, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from r5g import capture, dock, observe, oracle, runner, testbed, workload  # noqa
from r5g.testbed import CORE_NFS, c, imsi  # noqa

OUT = runner.RESULTS
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def snap(ues):
    s = oracle.snapshot_id(ues, probes=True)
    return {"smf_id": s["smf_id"], "amf_id": s["amf_id"], "ues": s["ues"], "dl_ok": s["dl_ok"],
            "counts": s["counts"], "vid": [list(v) for v in oracle.check_R_id(s)],
            "viol": [v[0] for v in oracle.check_R(s)]}


def one(rid, variant):
    ues = [1, 2]
    rec = {"id": rid, "variant": variant, "image": os.environ.get("OPEN5GS_IMAGE_TAG")}
    t_begin = time.time()
    pc = os.path.join(OUT, "pcap", f"{rid}.pcap")
    capture.start(pc)
    runner.reset(0)
    runner.bring_to("session", ues)
    rec["before"] = snap(ues)
    t_k = time.time()
    dock.kill(c("smf")); dock.start(c("smf"))
    rec["t_smf_restart"] = t_k
    observe.wait_for_log("smf", r"PFCP associated", t_k, timeout=30)
    time.sleep(3)
    rec["after_restart"] = snap(ues)
    workload.ps_establish(2)
    t2 = time.time()
    tt, ip = workload.wait_session(2, 30, psi=2)
    rec["ue2_psi2"] = {"t": tt, "ip": ip}
    time.sleep(2)
    rec["after_ue2_psi2"] = snap(ues)
    t_trig = time.time()
    if variant == "dereg":
        rec["trigger_out"] = workload.deregister(1)[1]
    else:
        rec["trigger_out"] = workload.ps_release(1, 1)[1]
    time.sleep(12)
    rec["after_trigger"] = snap(ues)
    s2 = rec["after_trigger"]["smf_id"] or {}
    ue2 = s2.get(imsi(2), {})
    rec["ue2_psi2_survives_at_smf"] = 2 in ue2
    ue2v = rec["after_trigger"]["ues"].get(2, {}).get("sessions", {})
    rec["ue2_psi2_active_at_ue"] = 2 in {int(k) for k in ue2v}
    if ip:
        rec["ue2_psi2_dl_ok"] = observe.dl_probe(ip)
        rec["ue2_psi2_ul_ok"] = observe.ul_probe(ip)
    amf = ANSI.sub("", dock.logs(c("amf"), since=t_trig))
    smf = ANSI.sub("", dock.logs(c("smf"), since=t_k))
    rec["amf_evidence"] = [l[31:] for l in amf.splitlines() if re.search(r"smContextRef|sm-contexts|Release|404|ERROR|WARN", l)][:40]
    rec["smf_evidence"] = [l[31:] for l in smf.splitlines() if re.search(r"Removed|UE SUPI|Release|release|ERROR|WARN|Unknown", l)][:60]
    os.makedirs(os.path.join(OUT, "logs"), exist_ok=True)
    lp = os.path.join(OUT, "logs", f"{rid}.log.gz")
    with gzip.open(lp, "wt") as f:
        for n in CORE_NFS + ["gnb"]:
            f.write(f"\n===== {n} =====\n" + ANSI.sub("", dock.logs(c(n), since=t_begin)))
        f.write("\n===== ue =====\n" + dock.dexec(c("ue"), "tail -n 200 /tmp/ue*.log").stdout)
    rec["logs"] = os.path.relpath(lp, OUT)
    rec["pcap"] = os.path.relpath(capture.stop(pc), OUT)
    rec["wall_s"] = round(time.time() - t_begin, 1)
    return rec


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--variant", default="dereg"); p.add_argument("--runs", type=int, default=3)
    p.add_argument("--image", default="r5g/open5gs:e85748e"); p.add_argument("--start", type=int, default=1)
    a = p.parse_args()
    os.environ["OPEN5GS_IMAGE_TAG"] = a.image
    testbed.up(image=a.image)
    tag = a.image.split(":")[-1]
    for r in range(a.start, a.start + a.runs):
        rid = f"ALIAS-{a.variant}-{tag}-r{r}"
        try:
            rec = one(rid, a.variant)
        except Exception as e:
            import traceback
            rec = {"id": rid, "error": f"{type(e).__name__}: {e}", "tb": traceback.format_exc()[-800:]}
        with open(os.path.join(OUT, "alias.jsonl"), "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        print(rid, {k: rec.get(k) for k in ["ue2_psi2", "ue2_psi2_survives_at_smf", "ue2_psi2_active_at_ue",
                                           "ue2_psi2_dl_ok", "ue2_psi2_ul_ok", "error"]}, flush=True)
