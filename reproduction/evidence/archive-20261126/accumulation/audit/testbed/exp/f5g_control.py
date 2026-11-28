#!/usr/bin/env python3
"""Revision 2026-11-25: free5GC v4.0.1 next-use control, with the fault runs repeated beside it.

After testbed/free5gc/run_f5g.py (7 November artifact). One UE (imsi-208930000000001, PSI 1 set up automatically).
  nf = none            no fault: the same 75 s window, then the same next use (the control the paper lacks)
  nf = smf|upf|amf     SIGKILL + immediate start of that NF, 75 s window, then next use
Next use, as in the paper's rule: release PSI 1, wait 6 s, establish a session, wait 10 s.
  old_psi_removed   PSI 1 is no longer listed at the UE after the release
  new_session_works a session is PS-ACTIVE after the establish and its uplink ping succeeds
  next_use_ok       both
  service_holds     every UE session has a working uplink at the end of the window (before next use)

  DOCKER_CONTEXT=colima-r5g-claude-ran F5G_OUT=<dir> python3 exp/f5g_control.py --nf none --runs 5
"""
import argparse, gzip, json, os, re, subprocess, sys, time, traceback

CTX = os.environ.get("DOCKER_CONTEXT", "colima-r5g-claude-ran")
HERE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "free5gc")
OUT = os.environ["F5G_OUT"]
NFS = ["nrf", "amf", "ausf", "nssf", "pcf", "smf", "udm", "udr", "chf", "upf", "ueransim"]
ANSI = re.compile(r"\x1b\[[0-9;]*m")
UE = "imsi-208930000000001"


def sh(*a, timeout=180):
    return subprocess.run(list(a), capture_output=True, text=True, timeout=timeout, env=dict(os.environ, DOCKER_CONTEXT=CTX))


def dx(c, cmd, timeout=30):
    return sh("docker", "exec", c, "sh", "-c", cmd, timeout=timeout)


def ps_list():
    out = dx("f5g-ueransim", f"nr-cli {UE} -e ps-list").stdout
    sess, cur = {}, None
    for l in out.splitlines():
        m = re.match(r"PDU Session(\d+):", l.strip())
        if m:
            cur = int(m.group(1)); sess[cur] = {}; continue
        m = re.match(r"\s*([\w-]+):\s*(.*)$", l)
        if m and cur:
            sess[cur][m.group(1)] = m.group(2).strip()
    return {k: v.get("address") for k, v in sess.items() if v.get("state") == "PS-ACTIVE"}


def ul_ok(ip):
    return dx("f5g-ueransim", f"ping -c 2 -W 1 -i 0.3 -I {ip} 10.100.200.1", timeout=10).returncode == 0


def snap(t0):
    s = ps_list()
    return {"t": round(time.time() - t0, 1), "ue_sessions": s, "ul_ok": {p: ul_ok(ip) for p, ip in s.items() if ip}}


def logs(c):
    r = sh("docker", "logs", c)
    return r.stdout + r.stderr


def fresh():
    sh("docker", "compose", "-f", os.path.join(HERE, "docker-compose.yml"), "up", "-d", "--force-recreate", timeout=400)
    for _ in range(90):
        if "NG Setup procedure is successful" in logs("f5g-ueransim") and "setup association" in logs("f5g-smf"):
            break
        time.sleep(1)
    else:
        raise RuntimeError("free5GC stack not ready")
    r = sh(os.path.join(HERE, "add_subscriber.sh"), "1")
    return (r.stdout + r.stderr).strip()


def run(nf, rep):
    rid = f"F5G-{nf}-r{rep}"
    rec = {"id": rid, "nf": nf, "images": "free5gc/*:v4.0.1 release images", "provision": fresh()}
    os.makedirs(os.path.join(OUT, "pcap"), exist_ok=True)
    pc = f"{rid}.pcap"
    sh("docker", "rm", "-f", "f5g-cap")
    sh("docker", "run", "-d", "--name", "f5g-cap", "--net", "host", "--cap-add", "NET_ADMIN", "--cap-add", "NET_RAW", "-v",
       f"{os.path.abspath(os.path.join(OUT, 'pcap'))}:/cap", "r5g/open5gs:e85748e", "tcpdump", "-i", "br-f5g", "-s", "0",
       "-U", "-w", f"/cap/{pc}", "not port 27017")
    t_begin = time.time()
    dx("f5g-ueransim", f"pkill -9 nr-ue; nohup nr-ue -c /cfg/uecfg.yaml -i {UE} > /tmp/ue1.log 2>&1 &")
    for _ in range(40):
        if ps_list().get(1):
            break
        time.sleep(1)
    time.sleep(2)
    rec["before"] = snap(t_begin)
    if not rec["before"]["ue_sessions"].get(1):
        rec["error"] = "no PSI 1 session before the fault"
    tk = time.time()
    if nf != "none":
        sh("docker", "kill", "-s", "KILL", f"f5g-{nf}"); sh("docker", "start", f"f5g-{nf}")
    series = []
    while time.time() - tk < 75:
        series.append(snap(tk)); time.sleep(3)
    rec["series"] = series; rec["final"] = series[-1]
    fin = series[-1]
    rec["service_holds"] = bool(fin["ue_sessions"]) and all(fin["ul_ok"].get(p) for p in fin["ue_sessions"])
    rec["next_release"] = dx("f5g-ueransim", f"nr-cli {UE} -e 'ps-release 1'").stdout.strip()
    time.sleep(6)
    rec["after_release"] = snap(tk)
    rec["next_establish"] = dx("f5g-ueransim", f"nr-cli {UE} -e 'ps-establish IPv4 --sst 1 --sd 0x010203 --dnn internet'").stdout.strip()
    time.sleep(10)
    rec["after_next_use"] = snap(tk)
    a = rec["after_next_use"]
    rec["old_psi_removed"] = 1 not in {int(k) for k in rec["after_release"]["ue_sessions"]}
    rec["new_session_works"] = any(a["ul_ok"].get(p) for p in a["ue_sessions"])
    rec["next_use_ok"] = rec["old_psi_removed"] and rec["new_session_works"]
    sh("docker", "stop", "-t", "1", "f5g-cap"); sh("docker", "rm", "-f", "f5g-cap")
    p = os.path.join(OUT, "pcap", pc)
    if os.path.exists(p):
        with open(p, "rb") as fi, gzip.open(p + ".gz", "wb") as fo:
            fo.write(fi.read())
        os.remove(p); rec["pcap"] = f"pcap/{pc}.gz"
    os.makedirs(os.path.join(OUT, "logs"), exist_ok=True)
    lp = os.path.join(OUT, "logs", f"{rid}.log.gz")
    with gzip.open(lp, "wt") as f:
        for n in NFS:
            r = sh("docker", "logs", "--timestamps", "--since", f"{t_begin:.0f}", f"f5g-{n}")
            f.write(f"\n===== {n} =====\n" + ANSI.sub("", r.stdout + r.stderr))
        f.write("\n===== ue =====\n" + dx("f5g-ueransim", "cat /tmp/ue1.log").stdout)
    rec["logs"] = f"logs/{rid}.log.gz"
    rec["ue_nas_tail"] = [l[-160:] for l in dx("f5g-ueransim", "tail -n 40 /tmp/ue1.log").stdout.splitlines()
                          if re.search(r"(?i)release|reject|cause|establish|error", l)][-12:]
    return rec


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--nf", required=True); ap.add_argument("--runs", type=int, default=3)
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    for nf in a.nf.split(","):
        for rep in range(1, a.runs + 1):
            try:
                rec = run(nf, rep)
            except Exception as e:
                rec = {"id": f"F5G-{nf}-r{rep}", "nf": nf, "error": f"{type(e).__name__}: {e}", "tb": traceback.format_exc()[-600:]}
            with open(os.path.join(OUT, "f5g_control.jsonl"), "a") as f:
                f.write(json.dumps(rec, default=str) + "\n")
            print(rec["id"], {k: rec.get(k) for k in ["error", "service_holds", "old_psi_removed", "new_session_works",
                                                     "next_use_ok"]}, "before", (rec.get("before") or {}).get("ue_sessions"),
                  "after_release", (rec.get("after_release") or {}).get("ue_sessions"),
                  "after_next_use", (rec.get("after_next_use") or {}).get("ue_sessions"), flush=True)
