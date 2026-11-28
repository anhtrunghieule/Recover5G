#!/usr/bin/env python3
"""OAI CN5G campaign 2 (replays with packet capture). Reuses run_oai.py helpers; DOCKER_CONTEXT=colima-recover5g-oai.

  python3 run_oai_c2.py o1  --rep 1                 # SMF SIGKILL + immediate start, k=2, 85 s window
  python3 run_oai_c2.py o2  --rep 1                 # UPF SIGKILL + immediate start
  python3 run_oai_c2.py o3  --rep 1                 # SMF SIGKILL, 45 s down, start
  python3 run_oai_c2.py i33 --rep 1                 # OAI SMF #33 recipe (SMF+UPF restart, UE2 new PSI, UE1 dereg)
  OAI_UPF_IMAGE=r5g/oai-upf:5a0a6d4-pr43 python3 run_oai_c2.py o1 --rep 1 --tag pr43

Every run redeploys the core, captures all traffic on the compose bridge from before the NFs start (so HTTP/2
HPACK state is complete) except MySQL, and writes ../../results/real/campaign2/oai/{oai_c2.jsonl, logs/, pcap/}.
"""
import argparse
import gzip
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_oai as R  # noqa: E402

OUT = os.path.abspath(os.path.join(R.HERE, "..", "..", "results", "real", "campaign2", "oai"))
CAP = "oai-cap"


def utc(t):
    return time.strftime("%H:%M:%S", time.gmtime(t)) + f".{int((t % 1) * 1000):03d}"


def bridge():
    r = R.sh(["docker", "network", "inspect", "demo-oai-public-net", "-f", "{{.Id}}"])
    return "br-" + r.stdout.strip()[:12]


def cap_start(name):
    os.makedirs(os.path.join(OUT, "pcap"), exist_ok=True)
    R.sh(["docker", "rm", "-f", CAP])
    br = bridge()
    R.sh(["docker", "run", "-d", "--name", CAP, "--net", "host", "--cap-add", "NET_ADMIN", "--cap-add", "NET_RAW",
          "-v", f"{os.path.join(OUT, 'pcap')}:/cap", "r5g/tshark:1", "tcpdump", "-i", br, "-s", "0", "-U",
          "-w", f"/cap/{name}.pcap", "not port 3306"], check=True)
    time.sleep(1.0)
    return br


def cap_stop(name):
    R.sh(["docker", "stop", "-t", "3", CAP])
    R.sh(["docker", "rm", "-f", CAP])
    p = os.path.join(OUT, "pcap", f"{name}.pcap")
    if os.path.exists(p):
        with open(p, "rb") as fi, gzip.open(p + ".gz", "wb") as fo:
            shutil.copyfileobj(fi, fo)
        os.remove(p)
        return os.path.relpath(p + ".gz", OUT)
    return None


def up_c2(name):
    R.compose("--profile", "ran", "down", "-v", "-t", "1")
    R.compose("up", "-d", "mysql")
    # the MySQL entrypoint runs a temporary server for initdb before the real one; wait for the real one
    ok = R.wait(lambda: R.sh(["docker", "exec", "mysql", "mysql", "-h", "127.0.0.1", "-utest", "-ptest", "oai_db", "-e",
                              "select count(*) from AuthenticationSubscription"]).returncode == 0, 180, 1.0)[0]
    if ok is None:
        raise RuntimeError("mysql not ready")
    time.sleep(2)
    br = cap_start(name)
    t0 = time.time()
    R.compose("up", "-d", *R.NFS)
    dt, _ = R.wait(lambda: "Received N4 ASSOCIATION SETUP RESPONSE" in R.logs("oai-smf"), 180)
    R.compose("--profile", "ran", "up", "-d", "gnb", "ue")
    dg, _ = R.wait(lambda: "NG Setup procedure is successful" in R.logs("oai-gnb"), 60)
    return {"bridge": br, "core_ready_s": dt, "gnb_ready_s": dg, "deploy_s": round(time.time() - t0, 1)}


def establish(i, timeout=40, new_only=False):
    """Request a PDU session; with new_only, succeed only on a PSI that was not PS-ACTIVE before the request."""
    old = set(R.ps_list(i)) if new_only else set()
    R.cli(i, "ps-establish IPv4 --sst 1 --dnn oai")
    return R.wait(lambda: {k: v for k, v in R.ps_list(i).items() if k not in old}, timeout)


def ues_up_sequential(k):
    """Register all UEs, then establish UE1's session before UE2's (deterministic smContextRef order)."""
    res = {}
    for i in range(1, k + 1):
        R.dx("oai-ue", f"nohup nr-ue -c /cfg/ue.yaml -i {R.imsi(i)} > /tmp/ue{i}.log 2>&1 &")
    for i in range(1, k + 1):
        res[f"reg{i}"] = R.wait(lambda: R.status(i).get("rm-state") == "RM-REGISTERED", 45)[0]
    time.sleep(1.5)
    for i in range(1, k + 1):
        res[f"pdu{i}"] = establish(i)
    return res


def ue_state(k):
    out = {}
    for i in range(1, k + 1):
        st = R.status(i)
        ps = R.ps_list(i) if st else {}
        out[i] = {"rm": st.get("rm-state"), "cm": st.get("cm-state"), "sessions": ps,
                  "rt_ok": {ip: R.ping_ul(ip) for ip in ps.values()}}
    return out


def observe(k, t_ref, window, step=5):
    series = []
    while time.time() - t_ref < window:
        time.sleep(step)
        series.append({"t": round(time.time() - t_ref, 1), "ues": ue_state(k)})
    return series


def save_logs(name, since):
    os.makedirs(os.path.join(OUT, "logs"), exist_ok=True)
    p = os.path.join(OUT, "logs", f"{name}.log.gz")
    with gzip.open(p, "wt") as f:
        for c in R.NFS + ["oai-gnb"]:
            f.write(f"\n===== {c} =====\n" + R.logs(c, since))
        f.write("\n===== ue =====\n" + R.dx("oai-ue", "tail -n 300 /tmp/ue*.log").stdout)
    return os.path.relpath(p, OUT)


def grep(c, since, pats, limit=60):
    import re
    out = []
    for l in R.logs(c, since).splitlines():
        if any(re.search(p, l) for p in pats):
            out.append(l.strip()[:300])
    return out[:limit]


def images():
    out = {}
    for c in R.NFS:
        r = R.sh(["docker", "inspect", "-f", "{{.Config.Image}} {{.Image}}", c])
        out[c] = r.stdout.strip()
    return out


def fault_run(a, nf_list, downtime, scenario):
    name = f"{scenario}-{a.tag}-r{a.rep}" if a.tag else f"{scenario}-r{a.rep}"
    t_begin = time.time()
    rec = {"id": name, "scenario": scenario, "rep": a.rep, "k": a.k, "downtime": downtime,
           "upf_image": os.environ.get("OAI_UPF_IMAGE", "oaisoftwarealliance/oai-upf:v2.2.2"),
           "smf_image": os.environ.get("OAI_SMF_IMAGE", "oaisoftwarealliance/oai-smf:v2.2.2")}
    rec["deploy"] = up_c2(name)
    rec["images"] = images()
    rec["setup"] = ues_up_sequential(a.k)
    if any(v is None or (isinstance(v, (list, tuple)) and v[0] is None) for v in rec["setup"].values()):
        cap_stop(name)
        raise RuntimeError(f"setup failed: {rec['setup']}")
    time.sleep(2)
    rec["before"] = ue_state(a.k)
    t_kill = time.time()
    for nf in nf_list:
        R.sh(["docker", "kill", "-s", "KILL", nf])
    rec["t_kill_utc"] = utc(t_kill)
    if downtime:
        time.sleep(downtime)
    t_start = time.time()
    for nf in reversed(nf_list):          # UPF before SMF when both restart
        R.sh(["docker", "start", nf])
    rec["t_start_utc"] = utc(t_start)
    rr, _ = R.wait(lambda: "Received N4 ASSOCIATION SETUP RESPONSE" in R.logs("oai-smf", t_start), 60, 0.2)
    rec["restart_ready_s"] = rr
    return name, t_begin, t_kill, t_start, rec


def finish(name, t_begin, rec):
    rec["logs"] = save_logs(name, t_begin)
    rec["pcap"] = cap_stop(name)
    rec["wall_s"] = round(time.time() - t_begin, 1)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "oai_c2.jsonl"), "a") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    print(json.dumps({k: v for k, v in rec.items() if k not in ("series",)}, indent=1, default=str)[:6000])


EVID_UPF = [r"ASSOCIATION", r"Associated", r"(?i)delet", r"(?i)remov", r"SESSION_ESTABLISHMENT", r"rejected",
            r"(?i)replaced association", r"HEARTBEAT"]
EVID_SMF = [r"ASSOCIATION", r"does not exit", r"(?i)release", r"rejected", r"SUPI", r"Location", r"0x26",
            r"(?i)heartbeat", r"(?i)node.*fail"]
EVID_AMF = [r"Location of the created SMF context", r"sm-contexts", r"(?i)release", r"(?i)error", r"404", r"400"]


def scen_fault(a, nf_list, downtime, scenario):
    name, t_begin, t_kill, t_start, rec = fault_run(a, nf_list, downtime, scenario)
    rec["series"] = observe(a.k, t_start, a.window)
    rec["after_window"] = ue_state(a.k)
    nxt = {}
    for i in range(1, a.k + 1):
        nxt[f"rel{i}"] = R.cli(i, "ps-release-all")
    time.sleep(6)
    nxt["after_release"] = ue_state(a.k)
    for i in range(1, a.k + 1):
        nxt[f"est{i}"] = establish(i, 30, new_only=True)
    rec["next_use"] = nxt
    rec["final"] = ue_state(a.k)
    rec["upf_evidence"] = grep("oai-upf", t_kill - 1, EVID_UPF)
    rec["smf_evidence"] = grep("oai-smf", t_start - 1, EVID_SMF)
    rec["amf_evidence"] = grep("oai-amf", t_kill - 1, EVID_AMF)
    finish(name, t_begin, rec)


def scen_i33(a):
    """#33 recipe: UE1 (ref 1) and UE2 (ref 2) have sessions; restart UPF+SMF (UPF too, so the new SMF's CP SEIDs
    are not rejected as in UPF #41); UE2 opens a new session (PSI 2) -> new SMF gives ref 1; UE1 deregisters
    (switch-off) -> AMF releases its stale sm-contexts/1 -> does the SMF release UE2's PSI 2?"""
    nfs = ["oai-smf", "oai-upf"] if not a.smf_only else ["oai-smf"]
    name, t_begin, t_kill, t_start, rec = fault_run(a, nfs, 0, "i33" + ("-smfonly" if a.smf_only else ""))
    time.sleep(3)
    rec["after_restart"] = ue_state(a.k)
    t_new = time.time()
    rec["ue2_new_session"] = establish(2, 40, new_only=True)
    time.sleep(3)
    rec["after_ue2_new"] = ue_state(a.k)
    rec["amf_refs_after_ue2_new"] = grep("oai-amf", t_new - 1, [r"Location of the created SMF context"])
    t_trig = time.time()
    rec["t_trigger_utc"] = utc(t_trig)
    if a.trigger == "dereg":
        rec["ue1_trigger_out"] = R.cli(1, "deregister switch-off")
    else:
        rec["ue1_trigger_out"] = R.cli(1, "ps-release 1")
    rec["series"] = observe(a.k, t_trig, a.window)
    rec["final"] = ue_state(a.k)
    rec["smf_evidence"] = grep("oai-smf", t_start - 1, EVID_SMF + [r"PDU Session ID", r"Find PDU Session", r"scid",
                                                                    r"SM Context", r"Remove PDU", r"Delete"])
    rec["amf_evidence"] = grep("oai-amf", t_kill - 1, EVID_AMF)
    rec["upf_evidence"] = grep("oai-upf", t_kill - 1, EVID_UPF)
    finish(name, t_begin, rec)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("scenario", choices=["o1", "o2", "o3", "i33"])
    p.add_argument("--rep", type=int, default=1)
    p.add_argument("--k", type=int, default=2)
    p.add_argument("--window", type=float, default=85)
    p.add_argument("--tag", default="")
    p.add_argument("--trigger", default="dereg", choices=["dereg", "release"])
    p.add_argument("--smf-only", action="store_true")
    a = p.parse_args()
    if a.scenario == "o1":
        scen_fault(a, ["oai-smf"], 0, "o1")
    elif a.scenario == "o2":
        scen_fault(a, ["oai-upf"], 0, "o2")
    elif a.scenario == "o3":
        scen_fault(a, ["oai-smf"], 45, "o3")
    else:
        scen_i33(a)


if __name__ == "__main__":
    main()
