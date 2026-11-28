#!/usr/bin/env python3
"""Revision 2026-11-25: replication of the orphan-session case and its repair on a fresh VM.

Recipe (after c2/f5b.py): two UEs hold one PDU session each -> AMF SIGKILL + immediate start -> the UEs register
again and establish a session with the same PSI -> two checkpoints (34 s and 68 s after the new sessions).

Conditions:
  --fault amf|none     AMF crash, or the same UE steps without any fault (control)
  --rereg powercycle   the UE process is killed and started again (initial registration), as in the original recipe
  --rereg ue           the UE is left running; `deregister switch-off`-free path: it re-registers on its own after
                       the gNB releases it (exploratory)
The gNB image is taken from $UERANSIM_IMAGE (p2 = survives SCTP loss; p1 = stock behaviour: aborts, and this
script restarts the gNB container, as an operator-visible gNB restart).

Recorded per run: proxy verdicts (count rule and identity rule) at both checkpoints, new-session service
(session active, downlink and uplink probes), UPF/SMF session counts, and the pcap. Wire adjudication is done
offline by exp/wire_truth.py, which does not read this record's verdict fields.

  . ../env.sh; R5G_INST=1 python3 exp/orphan_repl.py --image r5g/open5gs:e85748e --runs 5 --tag base-p2
"""
import argparse, gzip, json, os, re, sys, time, traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from r5g import capture, dock, observe, oracle, runner, testbed, workload  # noqa
from r5g.testbed import CORE_NFS, c, imsi  # noqa

OUT = runner.RESULTS
ANSI = re.compile(r"\x1b\[[0-9;]*m")
CHECKPOINTS = (34.0, 68.0)


def sn(ues):
    s = oracle.snapshot_id(ues)
    ul = {}
    for i, ip in s["ue_ips"].items():
        ul[i] = observe.ul_probe(ip) if ip else False
    return {"t": time.time(), "viol": [v[0] for v in oracle.check_R(s)], "vid": [list(v) for v in oracle.check_R_id(s)],
            "amf_id": s["amf_id"], "smf_id": s["smf_id"], "ues": s["ues"], "dl_ok": s["dl_ok"], "ul_ok": ul,
            "counts": s["counts"], "upf_log_ips": s["upf_log_ips"]}


def vm_clock_offset():
    """VM clock minus host clock (s); pcap timestamps are on the VM clock."""
    t0 = time.time()
    r = dock.dexec(c("probe"), "date +%s.%N")
    t1 = time.time()
    try:
        return float(r.stdout.strip()) - (t0 + t1) / 2
    except Exception:
        return None


def one(rid, a):
    ues = [1, 2]
    t0 = time.time()
    pc = os.path.join(OUT, "pcap", f"{rid}.pcap")
    capture.start(pc)
    runner.reset()
    runner.bring_to("session", ues)
    time.sleep(2)
    rec = {"id": rid, "image": a.image, "ueransim": os.environ.get("UERANSIM_IMAGE"), "fault": a.fault,
           "rereg_mode": a.rereg, "clock_offset_s": vm_clock_offset(), "before": sn(ues)}
    old_ips = {i: v["sessions"] for i, v in rec["before"]["ues"].items()}
    tk = time.time()
    rec["t_fault"] = tk
    if a.fault == "amf":
        dock.kill(c("amf")); dock.start(c("amf"))
    time.sleep(15)
    rec["gnb_running_after_fault"] = dock.running(c("gnb"))
    rec["gnb_restarted_by_harness"] = False
    if not rec["gnb_running_after_fault"]:
        dock.start(c("gnb")); rec["gnb_restarted_by_harness"] = True
    # wait for an NG Setup after the fault (only meaningful when the AMF was restarted)
    if a.fault == "amf":
        ok = False
        for _ in range(80):
            if "NG Setup procedure is successful" in dock.logs(c("gnb"), since=tk):
                ok = True; break
            time.sleep(0.5)
        rec["ng_setup_after_fault"] = ok
        if not ok and a.restart_gnb:
            # the gNB survived but did not set up NG again on its own: restart it, as an operator would
            t_r = time.time()
            dock.docker("restart", "-t", "1", c("gnb"), check=False)
            rec["gnb_restarted_by_harness"] = True
            ok2 = False
            for _ in range(80):
                if "NG Setup procedure is successful" in dock.logs(c("gnb"), since=t_r):
                    ok2 = True; break
                time.sleep(0.5)
            rec["ng_setup_after_gnb_restart"] = ok2
            time.sleep(2)
    rec["after_fault"] = sn(ues)
    rec["gnb_log"] = [l for l in ANSI.sub("", dock.logs(c("gnb"), since=tk)).splitlines()
                      if re.search(r"r5g|NG Setup|Association|SCTP|error|ERROR|terminate", l)][:25]
    if a.rereg == "powercycle":
        for i in ues:
            workload.power_off(i)
        time.sleep(2)
        for i in ues:
            workload.power_on(i)
        rec["rereg"] = {i: workload.wait_registered(i, 45) for i in ues}
        time.sleep(2)
    else:
        # leave the UE processes alone: wait for them to notice and register again on their own
        rec["rereg"] = {}
        for i in ues:
            t1 = time.time(); got = None
            while time.time() - t1 < 90:
                st = workload.status(i)
                if st.get("rm-state") == "RM-REGISTERED" and st.get("cm-state") == "CM-CONNECTED":
                    got = time.time() - t1; break
                # nudge: a service-type procedure makes an idle UE contact the (context-less) AMF
                workload.cli(i, "ps-release-all") if time.time() - t1 > 20 and not rec.get(f"nudged{i}") else None
                rec[f"nudged{i}"] = rec.get(f"nudged{i}") or (time.time() - t1 > 20)
                time.sleep(1)
            rec["rereg"][i] = got
        time.sleep(2)
    rec["ue_sessions_before_new"] = {i: workload.ps_list(i) for i in ues}
    for i in ues:
        workload.ps_establish(i)
    rec["new_session"] = {i: list(workload.wait_session(i, 40)) for i in ues}
    t_new = time.time()
    rec["t_new_sessions"] = t_new
    rec["checkpoints"] = []
    for cp in CHECKPOINTS:
        time.sleep(max(0.0, t_new + cp - time.time()))
        s = sn(ues); s["offset_s"] = cp
        rec["checkpoints"].append(s)
    fin = rec["checkpoints"][-1]
    new = {i: (rec["new_session"][i][1] if rec["new_session"][i][0] is not None else None) for i in ues}
    rec["old_ips"] = old_ips; rec["new_ips"] = new
    rec["new_sessions_work"] = all(new[i] for i in ues) and all(
        all(cp["dl_ok"].get(i) for i in ues) and all(cp["ul_ok"].get(i) for i in ues) for cp in rec["checkpoints"])
    rec["upf_sess"] = [cp["counts"].get("upf_sess") for cp in rec["checkpoints"]]
    rec["smf_sess"] = [cp["counts"].get("smf_sess") for cp in rec["checkpoints"]]
    rec["proxy_violated_both"] = all(cp["viol"] for cp in rec["checkpoints"])
    rec["proxy_viol"] = [cp["viol"] for cp in rec["checkpoints"]]
    rec["id_viol"] = [[v[0] for v in cp["vid"]] for cp in rec["checkpoints"]]
    lp = os.path.join(OUT, "logs", f"{rid}.log.gz"); os.makedirs(os.path.dirname(lp), exist_ok=True)
    with gzip.open(lp, "wt") as f:
        for n in CORE_NFS + ["gnb"]:
            f.write(f"\n===== {n} =====\n" + ANSI.sub("", dock.logs(c(n), since=t0)))
        f.write("\n===== ue =====\n" + dock.dexec(c("ue"), "tail -n 300 /tmp/ue*.log").stdout)
    rec["logs"] = os.path.relpath(lp, OUT); rec["pcap"] = os.path.relpath(capture.stop(pc), OUT)
    rec["wall_s"] = round(time.time() - t0, 1)
    return rec


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--image", default="r5g/open5gs:e85748e")
    p.add_argument("--fault", default="amf", choices=["amf", "none"])
    p.add_argument("--rereg", default="powercycle", choices=["powercycle", "ue"])
    p.add_argument("--runs", type=int, default=5)
    p.add_argument("--tag", required=True)
    p.add_argument("--no-up", action="store_true")
    p.add_argument("--restart-gnb", action="store_true",
                   help="restart the gNB container if it did not redo NG Setup within the wait after the fault")
    a = p.parse_args()
    os.makedirs(OUT, exist_ok=True)
    if not a.no_up:
        testbed.up(image=a.image)
    prov = {"open5gs": dock.image_id(a.image), "ueransim": dock.image_id(os.environ.get("UERANSIM_IMAGE", "")),
            "commit": dock.docker("run", "--rm", a.image, "cat", "/COMMIT", check=False).stdout.split()}
    done = set()
    jp = os.path.join(OUT, "orphan_repl.jsonl")
    if os.path.exists(jp):
        for line in open(jp):
            try:
                d = json.loads(line)
                if not d.get("error"):
                    done.add(d["id"])
            except Exception:
                pass
    for r in range(1, a.runs + 1):
        rid = f"orphan-{a.tag}-r{r}"
        if rid in done:
            print(rid, "already done; skipped", flush=True)
            continue
        try:
            rec = one(rid, a)
        except Exception as e:
            rec = {"id": rid, "error": f"{type(e).__name__}: {e}", "tb": traceback.format_exc()[-800:]}
            try:
                capture.stop(os.path.join(OUT, "pcap", f"{rid}.pcap"))
            except Exception:
                pass
        rec["tag"] = a.tag; rec["provenance"] = prov
        with open(os.path.join(OUT, "orphan_repl.jsonl"), "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        print(rid, {k: rec.get(k) for k in ["error", "gnb_running_after_fault", "rereg", "new_ips", "new_sessions_work",
                                           "upf_sess", "smf_sess", "proxy_viol", "id_viol", "wall_s"]}, flush=True)
