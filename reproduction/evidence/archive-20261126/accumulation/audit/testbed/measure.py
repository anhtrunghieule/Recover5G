#!/usr/bin/env python3
"""(a) Per-NF restart time on the VM clock; (b) lazy-repair probes after SMF / AMF crash-restart.

  python3 measure.py restart --reps 3
  python3 measure.py lazy
Writes ../results/real/restart_times.csv and ../results/real/lazy.jsonl.
"""
import csv
import datetime as dt
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r5g import dock, observe, oracle, runner, workload  # noqa: E402
from r5g.testbed import CORE_NFS, c  # noqa: E402

OUT = runner.RESULTS
READY = {  # (container whose log carries the marker, regex)
    "nrf": ("nrf", r"NRF initialize\.\.\.done"), "scp": ("scp", r"NF registered \[Heartbeat"),
    "ausf": ("ausf", r"NF registered \[Heartbeat"), "udm": ("udm", r"NF registered \[Heartbeat"), "udr": ("udr", r"NF registered \[Heartbeat"),
    "pcf": ("pcf", r"NF registered \[Heartbeat"), "nssf": ("nssf", r"NF registered \[Heartbeat"), "bsf": ("bsf", r"NF registered \[Heartbeat"),
    "smf": ("smf", r"PFCP associated"), "amf": ("amf", r"\] NF registered \[Heartbeat"),
    "upf": ("upf", r"PFCP associated"), "gnb": ("gnb", r"NG Setup procedure is successful"),
}


def parse_ts(s):
    s = s.rstrip("Z")
    base, frac = (s.split(".") + ["0"])[:2]
    return dt.datetime.fromisoformat(base).replace(tzinfo=dt.timezone.utc).timestamp() + float("0." + frac[:6])


def started_at(cont):
    return parse_ts(dock.docker("inspect", "-f", "{{.State.StartedAt}}", cont).stdout.strip())


def restart(a):
    rows = []
    for rep in range(a.reps):
        for nf in CORE_NFS + ["gnb"]:
            dock.kill(c(nf))
            time.sleep(0.5)
            dock.start(c(nf))
            t_st = started_at(c(nf))
            on, pat = READY[nf]
            rx = re.compile(pat)
            ready = None
            t0 = time.time()
            while time.time() - t0 < 40 and ready is None:
                for line in dock.logs(c(on), since=time.time() - 60).splitlines():
                    m = re.match(r"(\S+)\s", line)
                    if m and rx.search(line):
                        ts = parse_ts(m.group(1))
                        if ts >= t_st:
                            ready = ts - t_st
                            break
                time.sleep(0.2)
            rows.append({"rep": rep, "nf": nf, "ready_marker": pat, "restart_to_ready_s": None if ready is None else round(ready, 3)})
            print(rows[-1], flush=True)
            time.sleep(3)
        runner.reset()
    with open(os.path.join(OUT, "restart_times.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def lazy(a):
    for nf in ["smf", "amf"]:
        runner.reset()
        ues = [1, 2]
        runner.bring_to("session", ues)
        dock.kill(c(nf))
        dock.start(c(nf))
        time.sleep(30)
        before = oracle.check_R(oracle.snapshot(ues))
        acts = {}
        # UE1: user-driven release + re-establish; UE2: deregister (UERANSIM re-registers automatically)
        acts["ue1_release"] = workload.ps_release_all(1)[1]
        acts["ue2_dereg"] = workload.deregister(2)[1]
        time.sleep(8)
        acts["ue1_est"] = workload.ps_establish(1)[1]
        acts["ue1_session"] = workload.wait_session(1, 25)
        workload.wait_registered(2, 30)
        time.sleep(2)
        workload.ps_establish(2)
        acts["ue2_session"] = workload.wait_session(2, 25)
        time.sleep(3)
        snap = oracle.snapshot(ues)
        rec = {"nf": nf, "R_before_next_use": before, "actions": acts, "R_after_next_use": oracle.check_R(snap),
               "counts_after": snap["counts"], "ues_after": snap["ues"], "dl_ok_after": snap["dl_ok"]}
        with open(os.path.join(OUT, "lazy.jsonl"), "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        print(json.dumps(rec, default=str), flush=True)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("what", choices=["restart", "lazy"])
    p.add_argument("--reps", type=int, default=3)
    a = p.parse_args()
    {"restart": restart, "lazy": lazy}[a.what](a)
