#!/usr/bin/env python3
"""Campaign 2, item 9: free5GC v4.0.1 (release images, arm64) + gtp5g v0.9.14 in the recover5g VM.
One UE (imsi-208930000000001, auto PDU session PSI 1), then SIGKILL + immediate restart of the SMF or the UPF;
poll the UE view and an uplink ping (echo reply needs the UPF DL path too) for 75 s; then next use
(release PSI 1 + re-establish). NF logs and a bridge pcap are saved.
  python3 run_f5g.py smf upf
"""
import gzip, json, os, re, subprocess, sys, time
CTX = "colima-recover5g"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "results", "real", "campaign2", "free5gc")
NFS = ["nrf", "amf", "ausf", "nssf", "pcf", "smf", "udm", "udr", "chf", "upf", "ueransim"]
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def sh(*a, check=False, timeout=120):
    return subprocess.run(list(a), capture_output=True, text=True, timeout=timeout, env=dict(os.environ, DOCKER_CONTEXT=CTX))


def dx(c, cmd, timeout=30):
    return sh("docker", "exec", c, "sh", "-c", cmd, timeout=timeout)


def ps_list():
    out = dx("f5g-ueransim", "nr-cli imsi-208930000000001 -e ps-list").stdout
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
    r = dx("f5g-ueransim", f"ping -c 2 -W 1 -i 0.3 -I {ip} 10.100.200.1", timeout=10)
    return r.returncode == 0


def snap(t0):
    s = ps_list()
    return {"t": round(time.time() - t0, 1), "ue_sessions": s, "ul_ok": {p: ul_ok(ip) for p, ip in s.items() if ip}}


def fresh():
    sh("docker", "compose", "-f", os.path.join(HERE, "docker-compose.yml"), "up", "-d", "--force-recreate", timeout=300)
    for _ in range(60):
        if "NG Setup procedure is successful" in sh("docker", "logs", "f5g-ueransim").stdout + sh("docker", "logs", "f5g-ueransim").stderr \
                and "setup association" in sh("docker", "logs", "f5g-smf").stdout + sh("docker", "logs", "f5g-smf").stderr:
            break
        time.sleep(1)
    sh(os.path.join(HERE, "add_subscriber.sh"), "1")


def run(nf, rep):
    rid = f"F5G-{nf}-restart-r{rep}"
    fresh()
    bid = sh("docker", "network", "inspect", "-f", "{{.Id}}", "f5g_privnet").stdout.strip()
    pc = f"{rid}.pcap"
    os.makedirs(os.path.join(OUT, "pcap"), exist_ok=True)
    sh("docker", "rm", "-f", "f5g-cap")
    sh("docker", "run", "-d", "--name", "f5g-cap", "--net", "host", "--cap-add", "NET_ADMIN", "--cap-add", "NET_RAW", "-v",
       f"{os.path.abspath(os.path.join(OUT, 'pcap'))}:/cap", "r5g/open5gs:e85748e", "tcpdump", "-i", "br-f5g", "-s", "0",
       "-U", "-w", f"/cap/{pc}", "not port 27017")
    t_begin = time.time()
    dx("f5g-ueransim", "pkill -9 nr-ue; nohup nr-ue -c /cfg/uecfg.yaml -i imsi-208930000000001 > /tmp/ue1.log 2>&1 &")
    for _ in range(30):
        if ps_list().get(1):
            break
        time.sleep(1)
    rec = {"id": rid, "nf": nf, "images": "free5gc/*:v4.0.1 (release; not the paper's pinned commits)", "gtp5g": "v0.9.14 3b9166f",
           "before": snap(t_begin)}
    tk = time.time(); sh("docker", "kill", "-s", "KILL", f"f5g-{nf}"); sh("docker", "start", f"f5g-{nf}")
    series = []
    while time.time() - tk < 75:
        series.append(snap(tk)); time.sleep(3)
    rec["series"] = series
    rec["final"] = series[-1]
    # next use: release PSI 1 and establish again
    rec["next_release"] = dx("f5g-ueransim", "nr-cli imsi-208930000000001 -e 'ps-release 1'").stdout.strip()
    time.sleep(6)
    rec["next_establish"] = dx("f5g-ueransim", "nr-cli imsi-208930000000001 -e 'ps-establish IPv4 --sst 1 --sd 0x010203 --dnn internet'").stdout.strip()
    time.sleep(10)
    rec["after_next_use"] = snap(tk)
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
    ev = {}
    for n in ["smf", "upf", "amf"]:
        r = sh("docker", "logs", "--since", f"{tk:.0f}", f"f5g-{n}")
        ev[n] = [ANSI.sub("", l)[-200:] for l in (r.stdout + r.stderr).splitlines()
                 if re.search(r"(?i)heartbeat|association|restart|recovery|release|session|error|warn", l)][:40]
    rec["evidence"] = ev
    with open(os.path.join(OUT, "free5gc.jsonl"), "a") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    print(rid, "before", rec["before"], "final", rec["final"], "after_next_use", rec["after_next_use"], flush=True)


if __name__ == "__main__":
    for nf in sys.argv[1:]:
        run(nf, 1)
