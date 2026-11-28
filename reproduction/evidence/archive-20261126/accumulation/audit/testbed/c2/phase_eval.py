#!/usr/bin/env python3
"""Campaign 2: heartbeat phase / UPF usable time per phase run (from the saved NF logs, VM clock).
t_kill ~ (restarted UPF's first log line) - d; G = SMF 'No Heartbeat from UPF'; phi = G - 7.5 - t_kill (s from the kill
to the next SMF heartbeat request); phi_pred = 11 - ((t_kill - t_assoc0) mod 11) from the deterministic 11 s period;
T_b = SMF re-association - UPF start; detection path = give-up (G before re-association) or RTS-only.
Writes phase/phase_eval.csv."""
import csv, gzip, json, os, re, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
R = os.path.join(HERE, "..", "..", "results", "real", "campaign2", "phase")
TS = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+)Z")


def ts(line):
    m = TS.match(line)
    return datetime.datetime.fromisoformat(m.group(1)[:26]).timestamp() if m else None


def sections(txt):
    out, cur = {}, None
    for l in txt.splitlines():
        m = re.match(r"===== (\S+)", l)
        if m:
            cur = m.group(1); out[cur] = []; continue
        if cur:
            out[cur].append(l)
    return out


rows = []
recs = {json.loads(l)["id"]: json.loads(l) for l in open(os.path.join(R, "phase.jsonl"))}
for rid, r in sorted(recs.items()):
    if r.get("error"):
        continue
    s = sections(gzip.open(os.path.join(R, r["logs"]), "rt").read())
    smf, upf = s.get("smf", []), s.get("upf", [])
    banners = [ts(l) for l in upf if "Open5GS daemon" in l]
    t_start = banners[-1] if len(banners) >= 2 else None
    d = float(r.get("downtime") or 0)
    t_kill = t_start - d - 0.1 if t_start else None
    assoc = [ts(l) for l in smf if "PFCP associated" in l]
    a0 = assoc[0] if assoc else None
    g = next((ts(l) for l in smf if "No Heartbeat from UPF" in l), None)
    rts = next((ts(l) for l in smf if "Remote PFCP restarted" in l), None)
    a1 = next((t for t in assoc if t_start and t >= t_start), None)
    phi = round(g - 7.5 - t_kill, 2) if g and t_kill else None
    phi_pred = round(11 - ((t_kill - a0) % 11), 2) if t_kill and a0 else None
    rows.append({"id": rid, "downtime_s": d, "t_offset_s": r.get("t_offset"), "phi_s": phi, "phi_pred_s": phi_pred,
                 "giveup_after_kill_s": round(g - t_kill, 2) if g and t_kill else None,
                 "upf_start_minus_giveup_s": round(t_start - g, 2) if g and t_start else None,
                 "T_b_s": round(a1 - t_start, 2) if a1 and t_start else None,
                 "d_eff_s": round(max(d, (g - t_kill) if g and t_kill else d) + ((a1 - t_start) if a1 and t_start and g and t_start > g else 0), 2),
                 "path": ("give-up" if g and (a1 is None or g <= a1 + 0.01) else "RTS-only") + ("+RTS" if rts else ""),
                 "skip_restoration": sum("Skip restoration" in l for l in smf),
                 "viol_33.8": ";".join((r.get("snap") or {}).get("33.8", {}).get("viol", []) if (r.get("snap") or {}).get("33.8") else []),
                 "viol_67.6": ";".join((r.get("snap") or {}).get("67.6", {}).get("viol", []) if (r.get("snap") or {}).get("67.6") else []),
                 "t_conv_all": r.get("t_conv_all"), "next_use": json.dumps(r.get("next_use")), "liveness_ok": r.get("liveness_ok")})
if rows:
    with open(os.path.join(R, "phase_eval.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
for x in rows:
    print(x)
