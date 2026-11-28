#!/usr/bin/env python3
"""Revision 2026-11-25: the orphan-session case with an independent RAN (OAI gNB + OAI NR UE, RF simulator).

No UERANSIM component is involved. Two OAI UEs register and each sets up one PDU session (the OAI UE uses PSI 10).
The AMF is SIGKILLed and started again. The script records what the OAI gNB does on its own for 20 s; it then
restarts the gNB container if no NG Setup followed the AMF restart, restarts the two UE containers (they register
and set up PSI 10 again), and takes two checkpoints 34 s and 68 s after the new sessions.

Recorded per run: gNB behaviour after the fault, session counts at AMF/SMF/UPF, SMF and AMF identity dumps, the
UEs' tunnel addresses, downlink and uplink probes, logs and a pcap. PFCP evidence is extracted offline.

  DOCKER_CONTEXT=colima-r5g-claude-ran R5G_INST=5 python3 exp/orphan_oai.py --image r5g/open5gs:e85748e --tag base
"""
import argparse, gzip, json, os, re, subprocess, sys, time, traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from r5g import capture, dock, observe, runner, testbed  # noqa
from r5g.testbed import CORE_NFS, c  # noqa

OUT = runner.RESULTS
RAN_DIR = os.path.join(os.path.dirname(dock.TESTBED), "oai-ran")
RAN = ["docker", "compose", "-f", os.path.join(RAN_DIR, "docker-compose.oai-ran.yml")]
GNB, UES = c("oai-gnb"), {1: c("oai-ue1"), 2: c("oai-ue2")}
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def ran(*args, check=False, timeout=180):
    return dock.sh(RAN + list(args), check=check, timeout=timeout)


def ue_ip(i):
    r = dock.dexec(UES[i], "ip -4 -o addr show oaitun_ue1 2>/dev/null")
    m = re.search(r"inet ([\d.]+)/", r.stdout)
    return m.group(1) if m else None


def wait_ue_ips(timeout=90, exclude=()):
    t0 = time.time(); got = {}
    while time.time() - t0 < timeout:
        for i in UES:
            ip = ue_ip(i)
            if ip:
                got.setdefault(i, (round(time.time() - t0, 1), ip))
        if len(got) == len(UES):
            break
        time.sleep(1)
    return {i: got.get(i) for i in UES}


def gnb_ng_setup_since(t):
    return "Received NGSetupResponse from AMF" in dock.logs(GNB, since=t)


def start_gnb():
    t = time.time()
    ran("up", "-d", "--force-recreate", "oai-gnb")
    for _ in range(120):
        if gnb_ng_setup_since(t):
            return round(time.time() - t, 1)
        time.sleep(0.5)
    raise RuntimeError("OAI gNB: no NG Setup")


def reset():
    ran("rm", "-sf", "oai-ue1", "oai-ue2", "oai-gnb")
    names = [c(n) for n in CORE_NFS]
    dock.docker("kill", "-s", "KILL", *names, check=False)
    t = time.time()
    dock.docker("start", c("nrf"), c("scp")); time.sleep(1.0)
    dock.docker("start", *[c(n) for n in CORE_NFS if n not in ("nrf", "scp")])
    for _ in range(120):
        if "PFCP associated" in dock.logs(c("smf"), since=t) and "NF registered" in dock.logs(c("amf"), since=t):
            break
        time.sleep(0.5)
    else:
        raise RuntimeError("reset: core not ready")
    start_gnb()
    time.sleep(3)
    ran("up", "-d", "--force-recreate", "oai-ue1", "oai-ue2")
    ips = wait_ue_ips()
    if not all(ips.values()):
        raise RuntimeError(f"pre-state: OAI UEs did not get sessions: {ips}")
    return ips


def sn():
    ips = {i: ue_ip(i) for i in UES}
    return {"t": time.time(), "counts": observe.counts(), "amf_id": observe.amf_ue_info(), "smf_id": observe.smf_pdu_info(),
            "ue_ips": ips, "dl_ok": {i: (observe.dl_probe(ip) if ip else False) for i, ip in ips.items()},
            "ul_ok": {i: (dock.dexec(UES[i], "ping -c 2 -W 1 -i 0.2 -I oaitun_ue1 10.45.0.1", timeout=15).returncode == 0)
                      if ip else False for i, ip in ips.items()}}


def one(rid, a):
    t0 = time.time()
    pc = os.path.join(OUT, "pcap", f"{rid}.pcap"); capture.start(pc)
    rec = {"id": rid, "image": a.image, "ran": "oai-gnb+oai-nr-ue 2025.w40 (rfsim)", "fault": a.fault}
    rec["pre_ips"] = reset()
    time.sleep(3)
    rec["before"] = sn()
    tk = time.time(); rec["t_fault"] = tk
    if a.fault == "amf":
        dock.kill(c("amf")); dock.start(c("amf"))
    time.sleep(20)
    gl = ANSI.sub("", dock.logs(GNB, since=tk))
    rec["gnb_running_after_fault"] = dock.running(GNB)
    rec["gnb_ng_setup_on_its_own"] = "Received NGSetupResponse from AMF" in gl
    rec["gnb_log_after_fault"] = [l[31:] for l in gl.splitlines() if re.search(r"SCTP|NGAP|GNB_APP|AMF", l)][:20]
    rec["ue_ips_20s_after_fault"] = {i: ue_ip(i) for i in UES}
    rec["after_fault"] = sn()
    rec["gnb_restarted_by_harness"] = False
    if a.fault == "amf" and not rec["gnb_ng_setup_on_its_own"]:
        ran("rm", "-sf", "oai-ue1", "oai-ue2")
        rec["gnb_restart_ng_setup_s"] = start_gnb(); rec["gnb_restarted_by_harness"] = True
        time.sleep(3)
    else:
        ran("rm", "-sf", "oai-ue1", "oai-ue2")
        time.sleep(3)
    ran("up", "-d", "--force-recreate", "oai-ue1", "oai-ue2")          # UE power cycle
    rec["new_session"] = wait_ue_ips()
    t_new = time.time(); rec["t_new_sessions"] = t_new
    rec["checkpoints"] = []
    for cp in (34.0, 68.0):
        time.sleep(max(0.0, t_new + cp - time.time()))
        s = sn(); s["offset_s"] = cp; rec["checkpoints"].append(s)
    rec["new_sessions_work"] = all(rec["new_session"].values()) and all(
        all(cp["dl_ok"].values()) and all(cp["ul_ok"].values()) for cp in rec["checkpoints"])
    rec["upf_sess"] = [cp["counts"].get("upf_sess") for cp in rec["checkpoints"]]
    rec["smf_sess"] = [cp["counts"].get("smf_sess") for cp in rec["checkpoints"]]
    rec["amf_sess"] = [cp["counts"].get("amf_sess") for cp in rec["checkpoints"]]
    rec["ue_sess"] = [sum(1 for v in cp["ue_ips"].values() if v) for cp in rec["checkpoints"]]
    lp = os.path.join(OUT, "logs", f"{rid}.log.gz"); os.makedirs(os.path.dirname(lp), exist_ok=True)
    with gzip.open(lp, "wt") as f:
        for n in CORE_NFS:
            f.write(f"\n===== {n} =====\n" + ANSI.sub("", dock.logs(c(n), since=t0)))
        f.write("\n===== oai-gnb (control lines) =====\n" + "\n".join(
            l for l in ANSI.sub("", dock.logs(GNB, since=t0)).splitlines() if re.search(r"NGAP|SCTP|GNB_APP|RRC\]", l)))
        for i in UES:
            f.write(f"\n===== oai-ue{i} (NAS lines) =====\n" + "\n".join(
                l for l in ANSI.sub("", dock.logs(UES[i], since=t0)).splitlines() if re.search(r"NAS|OIP|RRC\]", l)))
    rec["logs"] = os.path.relpath(lp, OUT); rec["pcap"] = os.path.relpath(capture.stop(pc), OUT)
    rec["wall_s"] = round(time.time() - t0, 1)
    return rec


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--image", default="r5g/open5gs:e85748e"); p.add_argument("--fault", default="amf", choices=["amf", "none"])
    p.add_argument("--runs", type=int, default=5); p.add_argument("--tag", required=True)
    a = p.parse_args()
    os.makedirs(OUT, exist_ok=True)
    jp = os.path.join(OUT, "orphan_oai.jsonl")
    done = set()
    if os.path.exists(jp):
        for line in open(jp):
            try:
                d = json.loads(line)
                if not d.get("error"):
                    done.add(d["id"])
            except Exception:
                pass
    ran("rm", "-sf", "oai-ue1", "oai-ue2", "oai-gnb")
    env = {"OPEN5GS_IMAGE": a.image}
    dock.compose("down", "-v", "--remove-orphans", "-t", "1", check=False)
    dock.compose("up", "-d", "mongo", "probe", env=env); testbed.provision()
    dock.compose("up", "-d", *CORE_NFS, env=env); testbed.wait_core_ready()
    prov = {"open5gs": dock.image_id(a.image), "oai_gnb": dock.image_id("oaisoftwarealliance/oai-gnb:2025.w40"),
            "oai_ue": dock.image_id("oaisoftwarealliance/oai-nr-ue:2025.w40"),
            "commit": dock.docker("run", "--rm", a.image, "cat", "/COMMIT", check=False).stdout.split()}
    for r in range(1, a.runs + 1):
        rid = f"orphan-oai-{a.tag}-r{r}"
        if rid in done:
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
        with open(jp, "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        print(rid, {k: rec.get(k) for k in ["error", "gnb_running_after_fault", "gnb_ng_setup_on_its_own",
                                           "gnb_restarted_by_harness", "new_session", "new_sessions_work", "ue_sess",
                                           "amf_sess", "smf_sess", "upf_sess", "wall_s"]}, flush=True)
