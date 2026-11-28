#!/usr/bin/env python3
"""OAI CN5G + UERANSIM driver (stage 4; stdlib + docker CLI). Uses DOCKER_CONTEXT=colima-recover5g-oai.

  python3 run_oai.py up                       # deploy core + gNB + UE container
  python3 run_oai.py smoke --k 2              # register, PDU session (dnn oai), UL/DL ping
  python3 run_oai.py fault --nf oai-smf --downtime 0 --window 45 --tag smf-d0
Records JSON lines in ../../results/real/oai/oai.jsonl and gzipped logs in ../../results/real/oai/logs/.
"""
import argparse
import gzip
import json
import os
import re
import subprocess
import time

ENV = dict(os.environ, DOCKER_CONTEXT=os.environ.get("OAI_DOCKER_CONTEXT", "colima-recover5g-oai"))
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "results", "real", "oai")
NFS = ["oai-nrf", "oai-udr", "oai-udm", "oai-ausf", "oai-amf", "oai-smf", "oai-upf"]
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def sh(args, timeout=120, check=False):
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=ENV)
    if check and r.returncode:
        raise RuntimeError(f"{args}: {r.stdout}{r.stderr}")
    return r


def dx(c, cmd, timeout=30):
    return sh(["docker", "exec", c, "sh", "-c", cmd], timeout=timeout)


def logs(c, since=None):
    a = ["docker", "logs"] + (["--since", f"{since:.3f}"] if since else []) + [c]
    r = sh(a, timeout=60)
    return ANSI.sub("", r.stdout + r.stderr)


def compose(*a, timeout=600):
    return sh(["docker", "compose", "-f", os.path.join(HERE, "docker-compose.yml"), *a], timeout=timeout)


def imsi(i):
    return f"imsi-2089500000000{30 + i}"


def cli(i, cmd):
    r = dx("oai-ue", f"nr-cli {imsi(i)} -e '{cmd}'")
    return (r.stdout + r.stderr).strip()


def status(i):
    d = {}
    for l in cli(i, "status").splitlines():
        m = re.match(r"\s*([\w-]+):\s*(.*)$", l)
        if m:
            d[m.group(1)] = m.group(2).strip()
    return d


def ps_list(i):
    s, cur = {}, None
    for l in cli(i, "ps-list").splitlines():
        m = re.match(r"\s*PDU Session(\d+):", l)
        if m:
            cur = int(m.group(1)); s[cur] = {}; continue
        m = re.match(r"\s*([\w-]+):\s*(.*)$", l)
        if m and cur is not None:
            s[cur][m.group(1)] = m.group(2).strip()
    return {k: v.get("address") for k, v in s.items() if v.get("state") == "PS-ACTIVE"}


def wait(pred, timeout, step=0.5):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = pred()
        if v:
            return time.time() - t0, v
        time.sleep(step)
    return None, None


def up(a=None):
    compose("--profile", "ran", "down", "-v", "-t", "1")
    t0 = time.time()
    r = compose("up", "-d", *NFS, "mysql")
    print(r.stdout[-500:], r.stderr[-800:])
    dt, _ = wait(lambda: "Received N4 ASSOCIATION SETUP RESPONSE" in logs("oai-smf"), 180)
    print("core ready (PFCP assoc) after", dt, "s; total", round(time.time() - t0, 1))
    compose("--profile", "ran", "up", "-d", "gnb", "ue")
    dt, _ = wait(lambda: "NG Setup procedure is successful" in logs("oai-gnb"), 60)
    print("gNB NG setup after", dt)


def ue_up(k):
    for i in range(1, k + 1):
        dx("oai-ue", f"nohup nr-ue -c /cfg/ue.yaml -i {imsi(i)} > /tmp/ue{i}.log 2>&1 &")
    res = {}
    for i in range(1, k + 1):
        res[f"reg{i}"] = wait(lambda: status(i).get("rm-state") == "RM-REGISTERED", 45)[0]
    time.sleep(1.5)
    for i in range(1, k + 1):
        cli(i, "ps-establish IPv4 --sst 1 --dnn oai")
    for i in range(1, k + 1):
        res[f"pdu{i}"] = wait(lambda: ps_list(i), 40)
    return res


def ping_ul(ip):
    return dx("oai-ue", f"ping -c 2 -W 1 -i 0.3 -I {ip} 192.168.70.134").returncode == 0


def ping_dl(ip):
    return dx("oai-upf", f"ping -c 2 -W 1 -i 0.3 {ip}").returncode == 0


def view(k):
    out = {}
    for i in range(1, k + 1):
        st = status(i)
        ps = ps_list(i) if st else {}
        out[i] = {"rm": st.get("rm-state"), "cm": st.get("cm-state"), "sessions": ps,
                  # UE->UPF(N3 IP) ping round trip; verified to traverse GTP-U both ways (simple-switch UPF does
                  # not route pings originated inside its own container towards UEs, so no N6-side DL probe)
                  "dl": {ip: ping_ul(ip) for ip in ps.values()}}
    return out


def smoke(a):
    res = ue_up(a.k)
    print("registration/PDU:", res)
    print(json.dumps(view(a.k), indent=1))


def save_logs(tag, since):
    os.makedirs(os.path.join(OUT, "logs"), exist_ok=True)
    p = os.path.join(OUT, "logs", f"{tag}.log.gz")
    with gzip.open(p, "wt") as f:
        for c in NFS + ["oai-gnb"]:
            f.write(f"\n===== {c} =====\n" + logs(c, since))
        f.write("\n===== ue =====\n" + dx("oai-ue", "tail -n 200 /tmp/ue*.log").stdout)
    return os.path.relpath(p, OUT)


def fault(a):
    t_begin = time.time()
    up()
    res = ue_up(a.k)
    before = view(a.k)
    t_kill = time.time()
    sh(["docker", "kill", "-s", "KILL", a.nf])
    if a.downtime:
        time.sleep(a.downtime)
    t_start = time.time()
    sh(["docker", "start", a.nf])
    # readiness: N4 association re-established (SMF or UPF restart), else first log line
    if a.nf in ("oai-smf", "oai-upf"):
        rr, _ = wait(lambda: "Received N4 ASSOCIATION SETUP RESPONSE" in logs("oai-smf", t_start), 60, 0.2)
    else:
        rr, _ = wait(lambda: logs(a.nf, t_start).strip(), 30, 0.2)
    series = []
    while time.time() - t_start < a.window:
        time.sleep(5)
        v = {i: {"rm": s["rm"], "sessions": s["sessions"], "dl": s["dl"]} for i, s in view(a.k).items()}
        series.append({"t": round(time.time() - t_start, 1), "ues": v})
    after = view(a.k)
    # next use: release + re-establish for each UE
    nxt = {}
    for i in range(1, a.k + 1):
        nxt[f"rel{i}"] = cli(i, "ps-release-all")
    time.sleep(4)
    for i in range(1, a.k + 1):
        cli(i, "ps-establish IPv4 --sst 1 --dnn oai")
    for i in range(1, a.k + 1):
        nxt[f"est{i}"] = wait(lambda: ps_list(i), 30)
    final = view(a.k)
    rec = {"tag": a.tag, "nf": a.nf, "downtime": a.downtime, "k": a.k, "setup": res, "before": before,
           "t_kill_utc": time.strftime("%H:%M:%S", time.gmtime(t_kill)), "restart_ready_s": rr,
           "series": series, "after_window": after, "next_use": nxt, "final": final,
           "logs": save_logs(f"oai_{a.tag}", t_begin)}
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "oai.jsonl"), "a") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    print(json.dumps({k: v for k, v in rec.items() if k != "series"}, indent=1, default=str))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["up", "smoke", "fault"])
    p.add_argument("--k", type=int, default=2)
    p.add_argument("--nf", default="oai-smf")
    p.add_argument("--downtime", type=float, default=0)
    p.add_argument("--window", type=float, default=45)
    p.add_argument("--tag", default="t")
    a = p.parse_args()
    {"up": up, "smoke": smoke, "fault": fault}[a.cmd](a)


if __name__ == "__main__":
    main()
