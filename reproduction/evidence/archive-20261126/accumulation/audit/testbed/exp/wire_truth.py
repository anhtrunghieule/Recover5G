#!/usr/bin/env python3
"""Revision 2026-11-25: trace-based reference verdicts, computed without reading the checker's verdict fields.

For every snapshot of a run this script rebuilds which PFCP sessions the UPF holds, by identity, from two
sources that the deployed checker does not use for its verdicts:
  * the capture: PFCP Session Establishment / Deletion requests paired with their accepted responses
    (CP SEID, UP SEID, UE IPv4);
  * the UPF's own log: its "[Added]/[Removed] Number of UPF-Sessions is now N" lines and its start banner,
    which reveal local removals and restarts that never appear on the wire.
If the two disagree on the number of live sessions and the log count is not zero, the UPF identity set is
declared UNKNOWN for that snapshot rather than guessed.

Reference relation at a snapshot (identity level):
  REF-A-S   AMF's (SUPI, PSI) set equals the SMF's (SUPI, PSI) set                 [AMF /ue-info, SMF /pdu-info]
  REF-U-S   every UE (SUPI, PSI, IP) binding equals the SMF's, and vice versa       [UERANSIM, SMF /pdu-info]
  REF-S-P   multiset of SMF session IPs equals multiset of live UPF PFCP session IPs [SMF /pdu-info, wire + UPF log]
  REF-REG   UEs in RM-REGISTERED equal the UEs the AMF holds a context for
A snapshot is CHANGING if any PFCP session message, NGAP message or SM-context SBI request falls inside its
collection window (with a 0.3 s guard on each side); it is UNKNOWN if a readout is missing.

The deployed checker's verdicts are read only afterwards, to build the comparison tables:
  count rule    = labels of oracle.check_R except R4 (probe) and NONCONV
  proxy         = count rule plus the identity labels of oracle.check_R_id (what the paper calls R_obs)
  liveness      = the run-level liveness oracle

  python3 exp/wire_truth.py <results dir with heldout.jsonl | orphan_repl.jsonl> [--kind heldout|orphan]
"""
import argparse, collections, gzip, json, os, re, sys
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from c2 import pcap_ids  # noqa

GUARD = 0.3
DEFAULT_OFFSET = 0.0
TS = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)\.(\d+)Z ")
RE_CNT = re.compile(r"\[(Added|Removed)\] Number of UPF-[Ss]essions is now (\d+)")


def imsi(i):
    return f"imsi-99970{int(i):010d}"


def ts(line):
    m = TS.match(line)
    if not m:
        return None
    base = datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
    return base + float("0." + m.group(2))


def upf_log_timeline(logpath):
    """[(t, kind, n)] with kind in start|added|removed, from the saved UPF log section (VM clock)."""
    ev, sect = [], None
    with gzip.open(logpath, "rt", errors="replace") as f:
        for line in f:
            if line.startswith("====="):
                sect = line.strip("= \n").split()[0]
                continue
            if sect != "upf":
                continue
            t = ts(line)
            if t is None:
                continue
            if "Open5GS daemon" in line:
                ev.append((t, "start", 0))
            m = RE_CNT.search(line)
            if m:
                ev.append((t, m.group(1).lower(), int(m.group(2))))
    return ev


def decode(pcap):
    cache = (pcap[:-3] if pcap.endswith(".gz") else pcap) + ".ids.json"
    if os.path.exists(cache):
        d = json.load(open(cache))
    else:
        d = pcap_ids.decode(pcap)
        json.dump(d, open(cache, "w"), default=str)
    gcache = (pcap[:-3] if pcap.endswith(".gz") else pcap) + ".gtp.json"
    if os.path.exists(gcache):
        g = json.load(open(gcache))
    else:
        g = pcap_ids.tshark(pcap, "gtp && icmp.type == 8", ["frame.time_epoch", "ip.src", "ip.dst", "gtp.teid"])
        json.dump(g, open(gcache, "w"))
    return d, g


def wire_sessions(d):
    """PFCP session events on the wire: [(t, 'est'|'del', up_seid, cp_seid, ue_ip)], accepted ones only."""
    pf = [p for p in d["pfcp"] if "|" not in p["src"]]          # drop ICMP-quoted copies
    req = {}
    out = []
    for p in pf:
        key = (p["seq"], frozenset((p["src"], p["dst"])))
        seids = [x for x in p["seid"].split("|") if x]
        if p["type"] in (50, 54):
            req[(p["type"], key)] = p
        elif p["type"] == 51 and p["cause"].split("|")[0] == "1":
            q = req.pop((50, key), None)
            if q and len(seids) >= 2:
                out.append((p["t"], "est", seids[1], seids[0], q["ue_ip"].split("|")[0]))
        elif p["type"] == 55 and p["cause"].split("|")[0] == "1":
            q = req.pop((54, key), None)
            if q:
                out.append((p["t"], "del", q["seid"].split("|")[0], seids[0] if seids else None, None))
    return sorted(out)


def upf_state_at(t, wire, logev):
    """(known, {up_seid: ue_ip}, log_count) for the UPF at VM time t."""
    live, last_reset = {}, None
    resets = [e[0] for e in logev if e[1] == "start"]
    # local purge to zero: a logged count of 0 clears everything the wire had installed before it
    zeros = [e[0] for e in logev if e[1] == "removed" and e[2] == 0]
    marks = sorted([(x, "reset") for x in resets + zeros] + [(w[0], "w", w) for w in wire if w[0] <= t])
    for m in marks:
        if m[0] > t:
            break
        if m[1] == "reset":
            # a wire deletion that brings the count to zero and the log line for it are the same event
            live = {} if m[0] <= t else live
        else:
            _, kind, up, cp, ip = m[2]
            if kind == "est":
                live[up] = ip
            else:
                live.pop(up, None)
    n = 0
    for e in logev:
        if e[0] <= t:
            n = e[2]
    return (len(live) == n), live, n


def changing(t0, t1, d, wire, logev):
    lo, hi = t0 - GUARD, t1 + GUARD
    if any(lo <= p["t"] <= hi and p["type"] in (50, 51, 52, 53, 54, 55) for p in d["pfcp"]):
        return "pfcp"
    if any(lo <= float(x["time_epoch"]) <= hi for x in d["ngap"]):
        return "ngap"
    if any(lo <= q["t"] <= hi for q in d["sbi"]):
        return "sbi"
    if any(lo <= e[0] <= hi for e in logev):
        return "upf-log"
    return None


def reference(s, upf_known, upf_live):
    """Reference violations for one snapshot dict (needs ues, amf_id, smf_id). Returns (status, labels)."""
    amf, smf, ues = s.get("amf_id"), s.get("smf_id"), s.get("ues")
    c = s.get("counts") or {}
    if amf is None or smf is None or ues is None or any(c.get(k) is None for k in ("amf_sess", "smf_sess", "upf_sess")):
        return "unknown", ["readout-missing"]
    if not upf_known:
        return "unknown", ["upf-identity-ambiguous"]
    U = {(imsi(i), int(p)): ip for i, x in ues.items() for p, ip in (x.get("sessions") or {}).items()}
    S = {(u, int(p)): b.get("ip") for u, d in smf.items() for p, b in d.items()}
    A = {(u, int(p)) for u, d in amf.items() for p in (d.get("psis") or {})}
    v = []
    if A != set(S):
        v.append("REF-A-S")
    if U != {k: S[k] for k in S if k[0] in {imsi(i) for i in ues}} or set(U) - set(S):
        v.append("REF-U-S")
    if collections.Counter(S.values()) != collections.Counter(upf_live.values()):
        v.append("REF-S-P")
    reg = {imsi(i) for i, x in ues.items() if x.get("rm") == "RM-REGISTERED"}
    if reg != {u for u in amf if u.startswith("imsi-")}:
        v.append("REF-REG")
    return ("violated" if v else "clean"), v


def proxy_labels(s):
    cnt = [x for x in s.get("viol", []) if not x.startswith("R4") and x != "NONCONV"]
    vid = s.get("vid", [])
    vid = [x[0] if isinstance(x, list) else x for x in vid]
    vid = [x for x in vid if not x.startswith("NONCONV")]
    return cnt, sorted(set(cnt) | set(vid))


def adjudicate_run(rec, root, kind):
    pcap = os.path.join(root, rec["pcap"]); log = os.path.join(root, rec["logs"])
    d, g = decode(pcap)
    wire = wire_sessions(d); logev = upf_log_timeline(log)
    off = rec.get("clock_offset_s")
    if off is None:
        off = DEFAULT_OFFSET      # runs without a recorded VM-host clock offset; within the 0.3 s guard
    if kind == "heldout":
        snaps = [dict(x, t0=x["t_abs0"] + off, t1=x["t_abs1"] + off, rel=x["t"]) for x in rec["series"]]
    else:
        snaps = [dict(x, t0=x["t"] - 12.0 + off, t1=x["t"] + off, rel=x["offset_s"]) for x in rec["checkpoints"]]
    rows = []
    for s in snaps:
        known, live, n = upf_state_at((s["t0"] + s["t1"]) / 2, wire, logev)
        ch = changing(s["t0"], s["t1"], d, wire, logev)
        status, labels = reference(s, known, live)
        cnt, prox = proxy_labels(s)
        rows.append({"id": rec["id"], "rel": s["rel"], "changing": ch, "ref_status": status, "ref": labels,
                     "count_rule": cnt, "proxy": prox, "r4": [x for x in s.get("viol", []) if x.startswith("R4")],
                     "upf_live_ips": sorted(live.values()), "upf_log_count": n,
                     "upf_metric": (s.get("counts") or {}).get("upf_sess")})
    out = {"id": rec["id"], "rows": rows, "n_wire_est": sum(1 for w in wire if w[1] == "est"),
           "n_wire_del": sum(1 for w in wire if w[1] == "del")}
    pr = rec.get("upf_probe")
    if pr:
        t0, t1 = pr["t0"] + off, pr["t1"] + off
        fwd = set()
        for x in g:
            if t0 - 0.5 <= float(x["frame.time_epoch"]) <= t1 + 0.5:
                fwd.add(x["ip.dst"].split("|")[-1])
        # the probe takes about 12 s; the UPF's sessions can change while it runs (late establishments after next use),
        # so the reconstruction is taken at the start and at the end of the probe
        known, live, n = upf_state_at(t0, wire, logev)
        known1, live1, n1 = upf_state_at(t1, wire, logev)
        a, b = set(live.values()), set(live1.values())
        out["probe"] = {"forwarded_ips": sorted(fwd), "wire_live_ips": sorted(a), "wire_live_ips_end": sorted(b),
                        "log_count": n, "log_count_end": n1, "known": known and known1, "changed_during_probe": a != b,
                        "sound": fwd <= (a | b), "exact": fwd == a or fwd == b}
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("root"); ap.add_argument("--kind", default="heldout")
    ap.add_argument("--src", default=None, help="record file (default heldout.jsonl / orphan_repl.jsonl)")
    ap.add_argument("--dst", default=None); ap.add_argument("--default-offset", type=float, default=0.0)
    a = ap.parse_args()
    DEFAULT_OFFSET = a.default_offset
    src = os.path.join(a.root, a.src or ("heldout.jsonl" if a.kind == "heldout" else "orphan_repl.jsonl"))
    dst = os.path.join(a.root, a.dst or f"wire_truth_{a.kind}.jsonl")
    n = 0
    with open(dst, "w") as fo:
        for line in open(src):
            rec = json.loads(line)
            if rec.get("error") or not rec.get("pcap"):
                continue
            try:
                o = adjudicate_run(rec, a.root, a.kind)
            except Exception as e:
                o = {"id": rec["id"], "error": f"{type(e).__name__}: {e}"}
            fo.write(json.dumps(o) + "\n"); n += 1
            print(o["id"], o.get("error") or [(r["rel"], r["ref_status"], r["ref"], r["proxy"], r["changing"]) for r in o["rows"]][-2:],
                  o.get("probe", ""), flush=True)
    print("adjudicated", n, "->", dst)
