#!/usr/bin/env python3
"""Reproduction scenarios for mined Open5GS issues (positive controls).

  python3 repro.py i4877 [--image r5g/open5gs:e85748e] [--k 2] [--hold 60]
  python3 repro.py i4860 [--image ...]
  python3 repro.py i4892 [--image r5g/open5gs:48c0cc0]   # pre-fix parent of fc26daab9b
Each scenario records a time series of per-NF gauges plus UE state, saves NF logs and writes a JSON record to
../results/real/repro.jsonl.
"""
import argparse
import gzip
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r5g import dock, observe, oracle, runner, testbed, workload  # noqa: E402
from r5g.testbed import CORE_NFS, c  # noqa: E402

OUT = runner.RESULTS
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def utc(t):
    return time.strftime("%H:%M:%S", time.gmtime(t)) + f".{int((t % 1) * 1000):03d}"


def clean(txt):
    return ANSI.sub("", txt)


PCAP = {}


def setup(image, k, pcap_name=None):
    testbed.up(image=image)
    if pcap_name:   # campaign 2: capture from before a full NF restart so every SBI connection is decodable
        from r5g import capture
        PCAP["path"] = os.path.join(OUT, "pcap", f"{pcap_name}.pcap")
        capture.start(PCAP["path"])
        runner.reset()
    ues = list(range(1, k + 1))
    runner.bring_to("session", ues)
    return ues


def sample(ues, t0, probes=False):
    cnt = observe.counts()
    view = observe.ue_view(ues) if ues else {}
    ue_sess = {i: v["sessions"] for i, v in view.items()}
    row = {"t": round(time.time() - t0, 2), **cnt, "ue_sessions": ue_sess}
    if probes:
        row["dl_ok"] = {i: observe.dl_probe(ip) for i, s in ue_sess.items() for ip in s.values()}
    return row


def save(name, rec, t_begin):
    os.makedirs(os.path.join(OUT, "logs"), exist_ok=True)
    path = os.path.join(OUT, "logs", f"{name}.log.gz")
    with gzip.open(path, "wt") as f:
        for n in CORE_NFS + ["gnb"]:
            f.write(f"\n===== {n} =====\n" + clean(dock.logs(c(n), since=t_begin)))
        f.write("\n===== ue =====\n" + dock.dexec(c("ue"), "tail -n 300 /tmp/ue*.log").stdout)
    rec["logs"] = os.path.relpath(path, OUT)
    if PCAP.get("path"):
        from r5g import capture
        rec["pcap"] = os.path.relpath(capture.stop(PCAP.pop("path")), OUT)
    with open(os.path.join(OUT, "repro.jsonl"), "a") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def evidence(nf, t_begin, patterns):
    txt = clean(dock.logs(c(nf), since=t_begin))
    return [l[31:].strip() for l in txt.splitlines() if any(re.search(p, l) for p in patterns)][:40]


def i4877(a):
    """SMF dies and stays down. TS 23.527 4.4.3.1: UPF shall delete the sessions of the unreachable SMF."""
    t_begin = time.time()
    ues = setup(a.image, a.k, f"repro_{a.scenario}_{a.tag}" if a.pcap else None)
    t0 = time.time()
    series = [sample(ues, t0)]
    dock.kill(c("smf"))
    t_kill = time.time()
    while time.time() - t_kill < a.hold:
        time.sleep(2)
        series.append(sample([], t_kill))
    ev = evidence("upf", t_begin, [r"Heartbeat", r"(?i)UPF-Sessions", r"de-associated", r"No Reponse|No Response",
                                   r"Number of UPF"])
    rec = {"scenario": "i4877", "image": a.image, "k": a.k, "hold_s": a.hold, "t_kill_utc": utc(t_kill),
           "upf_sess_before": series[0]["upf_sess"], "upf_sess_end": series[-1]["upf_sess"],
           "series": series, "upf_evidence": ev}
    # phase 2: SMF comes back (new Recovery Time Stamp) -> does the UPF clean up then?
    dock.start(c("smf"))
    t_start = time.time()
    s2 = []
    while time.time() - t_start < a.after:
        time.sleep(2)
        s2.append(sample([], t_start))
    rec["series_after_smf_restart"] = s2
    rec["upf_sess_after_restart"] = s2[-1]["upf_sess"] if s2 else None
    rec["upf_evidence_after"] = evidence("upf", t_start, [r"(?i)UPF-Sessions", r"PFCP associated", r"restoration",
                                                          r"Recovery"])
    save(f"repro_i4877_{a.tag}", rec, t_begin)
    print(json.dumps({k: v for k, v in rec.items() if not k.startswith("series")}, indent=1))


def i4860(a):
    """UPF dies and stays down. Does the SMF release the UEs' sessions (towards AMF/UE) after HB give-up?"""
    t_begin = time.time()
    ues = setup(a.image, a.k, f"repro_{a.scenario}_{a.tag}" if a.pcap else None)
    t0 = time.time()
    series = [sample(ues, t0)]
    dock.kill(c("upf"))
    t_kill = time.time()
    while time.time() - t_kill < a.hold:
        time.sleep(2)
        series.append(sample(ues, t_kill))
    ev = evidence("smf", t_begin, [r"Heartbeat", r"de-associated", r"No UPF", r"Removed", r"release", r"Release"])
    rec = {"scenario": "i4860", "image": a.image, "k": a.k, "hold_s": a.hold, "series": series,
           "t_kill_utc": utc(t_kill), "t_upf_start_utc": None,
           "smf_evidence": ev, "amf_evidence": evidence("amf", t_kill, [r"Release", r"Removed", r"N1N2"])}
    dock.start(c("upf"))
    t_start = time.time()
    s2 = []
    while time.time() - t_start < a.after:
        time.sleep(2)
        s2.append(sample(ues, t_start, probes=True))
    rec["series_after_upf_restart"] = s2
    save(f"repro_i4860_{a.tag}", rec, t_begin)
    print(json.dumps({k: v for k, v in rec.items() if not k.startswith("series")}, indent=1, default=str))
    for r in series[::3] + s2[::3]:
        print(r)


def i4892(a):
    """Reporter's deterministic recipe: freeze the UEs so the N1/N2 release cannot complete, keep the UPF down
    across the SMF heartbeat give-up, start it again (restoration runs while sessions are mid-release), then let
    the UEs back. Pre-fix: UPF re-gets PDRs for pre-outage UE IPs (stale) next to the current ones."""
    t_begin = time.time()
    ues = setup(a.image, a.k, f"repro_{a.scenario}_{a.tag}" if a.pcap else None)
    before = sample(ues, t_begin)
    old_ips = sorted(ip for s in before["ue_sessions"].values() for ip in s.values())
    dock.pause(c("ue"))                      # UEs frozen: cannot answer N1 release
    t_freeze = time.time()
    dock.docker("stop", "-t", "1", c("upf"))   # UPF down (state lost)
    t_stop = time.time()
    series = []
    while time.time() - t_stop < a.hold:
        time.sleep(2)
        series.append(sample([], t_stop))
    dock.start(c("upf"))                       # UPF back with new Recovery Time Stamp -> SMF restoration
    t_start = time.time()
    time.sleep(a.settle)
    mid = sample([], t_start)
    upf_ips_mid = observe.upf_session_ips()
    dock.unpause(c("ue"))
    t_unfreeze = time.time()
    s2 = []
    while time.time() - t_unfreeze < a.after:
        time.sleep(3)
        s2.append(sample(ues, t_unfreeze))
    pre_next = sample(ues, t_unfreeze, probes=True)
    pre_next_R = oracle.check_R(oracle.snapshot(ues))
    # next use: each UE releases its (possibly stale) session and establishes a fresh one
    next_use = {}
    for i in ues:
        if workload.ps_list(i):
            next_use[f"rel{i}"] = workload.ps_release_all(i)[1]
    time.sleep(6)
    for i in ues:
        workload.ps_establish(i)
    for i in ues:
        next_use[f"est{i}"] = workload.wait_session(i, 25)
    time.sleep(3)
    final = sample(ues, t_unfreeze, probes=True)
    upf_ips_final = observe.upf_session_ips()
    new_ips = sorted(ip for s in final["ue_sessions"].values() for ip in s.values())
    snap = oracle.snapshot(ues)
    rec = {"scenario": "i4892", "image": a.image, "k": a.k, "hold_s": a.hold, "old_ips": old_ips,
           "t_freeze_utc": utc(t_freeze), "t_upf_stop_utc": utc(t_stop), "t_upf_start_utc": utc(t_start),
           "t_unfreeze_utc": utc(t_unfreeze),
           "new_ips": new_ips, "upf_after_restoration": mid, "upf_ips_installed_after_restart_mid": upf_ips_mid,
           "upf_ips_installed_since_restart_final": upf_ips_final, "final": final,
           "R_violations_final": oracle.check_R(snap), "before_next_use": pre_next,
           "R_violations_before_next_use": pre_next_R, "next_use": next_use,
           "smf_evidence": evidence("smf", t_freeze, [r"Heartbeat", r"Session Release", r"ACTIVATING", r"Unknown event", r"restor", r"Restor", r"Skip", r"PFCP associated",
                                                     r"Removed Session", r"UE SUPI"]),
           "upf_evidence": evidence("upf", t_start, [r"(?i)UPF-Sessions", r"UE F-SEID", r"PFCP associated"]),
           "series_upf_down": series, "series_after_unfreeze": s2}
    save(f"repro_i4892_{a.tag}", rec, t_begin)
    print(json.dumps({k: v for k, v in rec.items() if not k.startswith("series")}, indent=1, default=str))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("scenario", choices=["i4877", "i4860", "i4892"])
    p.add_argument("--image", default="r5g/open5gs:e85748e")
    p.add_argument("--k", type=int, default=2)
    p.add_argument("--hold", type=float, default=60)
    p.add_argument("--after", type=float, default=30)
    p.add_argument("--settle", type=float, default=6)
    p.add_argument("--tag", default="")
    p.add_argument("--pcap", action="store_true", help="campaign 2: capture N2/N4/SBI into OUT/pcap/")
    a = p.parse_args()
    a.tag = a.tag or a.image.split(":")[-1]
    a.scenario = a.scenario
    globals()[a.scenario](a)


if __name__ == "__main__":
    main()
