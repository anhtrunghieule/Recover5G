#!/usr/bin/env python3
"""Recover5G real-testbed campaigns.

  python3 campaign.py up [--image r5g/open5gs:e85748e]   # fresh deploy + provision
  python3 campaign.py smoke                                # register 2 UEs, PDU session, ping via UPF
  python3 campaign.py boundary --k 2 --seeds 2             # systematic boundary campaign (AMF/SMF/UPF)
  python3 campaign.py podkill --runs 20                    # random pod-kill baseline
  python3 campaign.py benign                               # convergence of correct runs per fault/NF
  python3 campaign.py one --proc pdu --nf smf --boundary pdu.upf_sess_added --mode crash --downtime 0

Results: ../results/real/<campaign>.jsonl (+ logs/<run-id>.log.gz).
"""
import argparse
import itertools
import json
import os
import random
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r5g import dock, observe, oracle, runner, testbed, workload  # noqa: E402

OUT = runner.RESULTS


def cmd_up(a):
    t = time.time()
    testbed.up(image=a.image)
    print(f"up in {time.time()-t:.1f}s", testbed.provenance())


def cmd_smoke(a):
    ues = list(range(1, a.k + 1))
    for i in ues:
        workload.power_on(i)
    for i in ues:
        print("UE", i, "registered in", workload.wait_registered(i, 20))
    time.sleep(1.5)
    for i in ues:
        print(workload.ps_establish(i)[1])
    for i in ues:
        print("UE", i, "session", workload.wait_session(i, 20))
    print("tun", workload.tun_addrs())
    snap = oracle.snapshot(ues)
    print(json.dumps(snap, indent=1, default=str))
    print("R violations:", oracle.check_R(snap))
    for ip in snap["ue_ips"].values():
        print("UL ping", ip, observe.ul_probe(ip), "DL ping", observe.dl_probe(ip))


def _run_all(name, specs, a):
    path = os.path.join(OUT, f"{name}.jsonl")
    done = set()
    if os.path.exists(path):
        for line in open(path):
            try:
                done.add(json.loads(line)["id"])
            except Exception:
                pass
    t_end = time.time() + a.budget if a.budget else None
    for s in specs:
        if s["id"] in done:
            continue
        if t_end and time.time() > t_end:
            print("budget exhausted")
            break
        try:
            rec = runner.run(s, OUT)
        except Exception as e:  # record harness failures honestly
            rec = dict(s, error=f"{type(e).__name__}: {e}", tb=traceback.format_exc()[-800:])
        runner.write_jsonl(path, rec)
        print(f"[{name}] {s['id']}: fired={rec.get('fault_fired')} viol@Δ={rec.get('viol_at_delta')} "
              f"end={rec.get('viol_end')} tconv={rec.get('t_conv')} crash={rec.get('crash_oracle')} "
              f"live={rec.get('liveness_ok')} next={rec.get('viol_after_next_use')} err={rec.get('error','')[:120]}",
              flush=True)


BOUNDARY_SETS = {
    "reg": ["reg.ngap_initial_ue", "reg.amf_ue_added", "reg.security_done", "reg.udm_done", "reg.complete"],
    "pdu": ["pdu.amf_sess_added", "pdu.smf_sess_added", "pdu.ip_allocated", "pdu.upf_sess_added", "pdu.n2_modify"],
    "rel": ["rel.n2_released", "rel.upf_sess_removed", "rel.smf_sess_removed", "rel.amf_sess_removed"],
    "dereg": ["dereg.amf_rx", "dereg.sm_release", "dereg.smf_sess_removed", "dereg.ue_ctx_release"],
}


def cmd_boundary(a):
    specs = []
    for proc in a.procs.split(","):
        for b in BOUNDARY_SETS[proc]:
            for nf in a.nfs.split(","):
                for k in [int(x) for x in a.ks.split(",")]:
                    for seed in range(a.seeds):
                        specs.append(dict(id=f"B-{proc}-{b}-{nf}-k{k}-s{seed}", k=k, proc=proc, nf=nf,
                                          boundary=b, mode="crash", downtime=0.0, seed=seed,
                                          netem_ms=a.netem, window=a.window, poll=a.poll, stagger=0.3))
    random.Random(1).shuffle(specs)
    print(len(specs), "schedules")
    _run_all(a.name or "boundary", specs, a)


def cmd_podkill(a):
    rng = random.Random(a.seed)
    specs = []
    for r in range(a.runs):
        proc = rng.choice(["reg", "pdu", "rel", "dereg"])
        nf = rng.choice(["amf", "smf", "upf"])
        specs.append(dict(id=f"P-{r}", k=rng.choice([1, 2, 3, 4]) if a.ks == "rand" else int(a.ks),
                          proc=proc, nf=nf, boundary=None, t_offset=round(rng.uniform(0.0, 2.0), 3),
                          mode="crash", downtime=0.0, seed=r, netem_ms=a.netem, window=a.window, poll=a.poll))
    _run_all(a.name or "podkill", specs, a)


def cmd_downtime(a):
    """Downtime dimension: stop NF at steady state (sessions active) for D seconds, then start."""
    specs = []
    for nf in a.nfs.split(","):
        for d in [float(x) for x in a.downtimes.split(",")]:
            for seed in range(a.seeds):
                specs.append(dict(id=f"D-{nf}-{a.mode}-d{d:g}-k{a.k}-s{seed}", k=a.k, proc="idle", nf=nf,
                                  boundary=None, t_offset=0.0, mode=a.mode, downtime=d, seed=seed,
                                  netem_ms=0, window=a.window, poll=a.poll))
    _run_all(a.name or "downtime", specs, a)


def cmd_one(a):
    spec = dict(id=a.id or f"one-{int(time.time())}", k=a.k, proc=a.proc, nf=a.nf, boundary=a.boundary,
                t_offset=a.t_offset, mode=a.mode, downtime=a.downtime, seed=a.seed, netem_ms=a.netem,
                window=a.window, poll=a.poll)
    rec = runner.run(spec, OUT)
    runner.write_jsonl(os.path.join(OUT, a.name or "one.jsonl"), rec)
    rec.pop("series", None)
    print(json.dumps(rec, indent=1, default=str))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("up"); s.add_argument("--image", default=None)
    s = sub.add_parser("smoke"); s.add_argument("--k", type=int, default=2)
    common = dict(netem=("--netem", int, 0), window=("--window", float, 72.0), poll=("--poll", float, 3.0),
                  budget=("--budget", float, 0), name=("--name", str, None))

    def add_common(sp):
        for _, (flag, typ, dflt) in common.items():
            sp.add_argument(flag, type=typ, default=dflt)
    s = sub.add_parser("boundary"); add_common(s)
    s.add_argument("--procs", default="reg,pdu,rel,dereg"); s.add_argument("--nfs", default="amf,smf,upf")
    s.add_argument("--ks", default="2"); s.add_argument("--seeds", type=int, default=1)
    s = sub.add_parser("podkill"); add_common(s)
    s.add_argument("--runs", type=int, default=20); s.add_argument("--seed", type=int, default=0)
    s.add_argument("--ks", default="2")
    s = sub.add_parser("downtime"); add_common(s)
    s.add_argument("--nfs", default="upf,smf,amf,nrf,gnb"); s.add_argument("--downtimes", default="0,10,30")
    s.add_argument("--mode", default="crash"); s.add_argument("--k", type=int, default=2)
    s.add_argument("--seeds", type=int, default=1)
    s = sub.add_parser("one"); add_common(s)
    s.add_argument("--id"); s.add_argument("--k", type=int, default=2); s.add_argument("--proc", default="pdu")
    s.add_argument("--nf", default="smf"); s.add_argument("--boundary", default=None)
    s.add_argument("--t-offset", type=float, default=None); s.add_argument("--mode", default="crash")
    s.add_argument("--downtime", type=float, default=0.0); s.add_argument("--seed", type=int, default=0)
    a = p.parse_args()
    {"up": cmd_up, "smoke": cmd_smoke, "boundary": cmd_boundary, "podkill": cmd_podkill,
     "downtime": cmd_downtime, "one": cmd_one}[a.cmd](a)


if __name__ == "__main__":
    main()
