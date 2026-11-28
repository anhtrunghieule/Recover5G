#!/usr/bin/env python3
"""Revision 2026-11-25: held-out runs for validating the checker against trace evidence.

The schedules are new: they were drawn after the paper's checker and campaign were frozen, from a seed that no
earlier campaign used, and they use no netem delay (natural timing on the bridge).

  kind 'kill'    : SIGKILL + immediate start of a random NF (amf|smf|upf) at a random offset in [0, 2] s into a
                   random procedure (reg|pdu|rel|dereg), or at steady state with sessions up (idle)
  kind 'nofault' : the same procedures with no fault (clean controls)

Per run: the normal runner record (count rule, identity rule, liveness / next use, crash-only), a pcap of the
whole run, and at the very end an identity probe of the UPF: one downlink ping to every address the pool can
have handed out in this run. The GTP-U packets that the UPF emits for those pings show, per UE IP, whether the
UPF still forwards for it. The probe runs after every recorded verdict, so it cannot change them.

  . ../env.sh; R5G_INST=1 python3 exp/heldout.py --part 0 --parts 2
"""
import argparse, json, os, random, sys, time, traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from r5g import capture, dock, observe, oracle, runner, testbed, workload  # noqa
from r5g.testbed import c  # noqa

OUT = runner.RESULTS
SEED = 20261125
N_KILL, N_NOFAULT = 60, 12
PROBE_IPS = [f"10.45.0.{i}" for i in range(2, 14)]


def specs():
    rng = random.Random(SEED)
    out = []
    for r in range(N_KILL):
        proc = rng.choice(["reg", "pdu", "rel", "dereg", "idle"])
        nf = rng.choice(["amf", "smf", "upf"])
        out.append(dict(id=f"HO-kill-{r:02d}", kind="kill", k=2, proc=proc, nf=nf, boundary=None,
                        t_offset=round(rng.uniform(0.0, 2.0), 3), mode="crash", downtime=0.0,
                        seed=SEED + r, netem_ms=0, window=72.0, poll=3.0, stagger=0.3, pcap=False))
    for r in range(N_NOFAULT):
        proc = ["reg", "pdu", "rel", "dereg", "idle"][r % 5]
        out.append(dict(id=f"HO-nofault-{r:02d}", kind="nofault", k=2, proc=proc, nf=None, boundary=None,
                        t_offset=None, mode="none", downtime=0.0, seed=SEED + 1000 + r, netem_ms=0,
                        window=72.0, poll=3.0, stagger=0.3, pcap=False))
    rng2 = random.Random(SEED + 7)
    rng2.shuffle(out)          # interleave controls and faults; order fixed by the seed
    return out


def clock_offset():
    t0 = time.time(); r = dock.dexec(c("probe"), "date +%s.%N"); t1 = time.time()
    try:
        return float(r.stdout.strip()) - (t0 + t1) / 2
    except Exception:
        return None


def upf_identity_probe():
    t = time.time()
    for ip in PROBE_IPS:
        dock.dexec(c("upf"), f"ping -c 1 -W 1 {ip} >/dev/null 2>&1; true", timeout=10)
    time.sleep(1.0)
    return {"t0": t, "t1": time.time(), "ips": PROBE_IPS}


def one(s):
    pc = os.path.join(OUT, "pcap", f"{s['id']}.pcap")
    capture.start(pc)
    try:
        if s["proc"] == "idle":
            runner.PRE["idle"] = "session"
        rec = runner.run(s, OUT)
        rec["clock_offset_s"] = clock_offset()
        rec["upf_probe"] = upf_identity_probe()
    finally:
        try:
            p = capture.stop(pc)
        except Exception:
            p = None
    rec["pcap"] = os.path.relpath(p, OUT) if p else None
    return rec


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", type=int, default=0); ap.add_argument("--parts", type=int, default=1)
    ap.add_argument("--image", default="r5g/open5gs:e85748e"); ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    S = specs()
    if a.list:
        for s in S:
            print(s["id"], s["proc"], s["nf"], s["t_offset"])
        sys.exit(0)
    mine = [s for i, s in enumerate(S) if i % a.parts == a.part]
    if a.limit:
        mine = mine[:a.limit]
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "heldout.jsonl")
    done = set()
    if os.path.exists(path):
        for line in open(path):
            try:
                d = json.loads(line)
                if not d.get("error"):
                    done.add(d["id"])
            except Exception:
                pass
    testbed.up(image=a.image)
    for s in mine:
        if s["id"] in done:
            continue
        try:
            rec = one(s)
        except Exception as e:
            rec = dict(s, error=f"{type(e).__name__}: {e}", tb=traceback.format_exc()[-800:])
        rec["stack"] = int(os.environ.get("R5G_INST", "0")); rec["image"] = a.image
        runner.write_jsonl(path, rec)
        print(s["id"], s["proc"], s["nf"], s.get("t_offset"), "fired", rec.get("fault_fired"),
              "end", rec.get("viol_end"), "id_end", [v[0] for v in rec.get("final_detail_id", [])],
              "live", rec.get("liveness_ok"), "crash", rec.get("crash_oracle"), "err", rec.get("error", "")[:100],
              flush=True)
