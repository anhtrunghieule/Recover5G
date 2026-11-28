#!/usr/bin/env python3
"""Campaign 2: runner JSONL -> CSV with per-conjunct verdicts at Delta_j and 2*Delta_j (count- and identity-level).

Per-conjunct classes (Table 4, Open5GS): fault on UPF -> every conjunct numeric, Delta_j = T_b + 23.5 = 33.8 s
(2x = 67.6 s); fault on SMF -> R3 numeric (Delta_j = T_b + 5 = 5.5 s, 2x = 11 s), AMF-side conjuncts (R1, R2, R4, R6,
Rg) NU (checked at 2*max Delta = 67.6 s and after the next use); fault on AMF -> R2, R5 (and the rest) UE class.
verdict per conjunct: 'ok' (clean at 2*Delta_j), 'transient' (violated at Delta_j, clean at 2*Delta_j), 'persistent'
(violated at Delta_j and 2*Delta_j), 'late' (clean at Delta_j, violated at 2*Delta_j). For NU/UE classes the snapshot
pair is (33.8, 67.6). lazy_repair_v2 = violated at 67.6 AND clean after next use AND every next-use action succeeded.
  python3 c2/analyze_c2.py <out.csv> <jsonl> [...]
"""
import csv, gzip, json, os, sys


def conj(label):
    if label.startswith("NONCONV"):
        return "NONCONV"
    if label.startswith("Rg"):
        return "Rg"
    return label[:2]


def classes(nf):
    if nf == "upf":
        return {c: ("num", "33.8", "67.6") for c in ["R1", "R2", "R3", "R4", "R5", "R6", "Rg", "NONCONV"]}
    if nf == "smf":
        d = {c: ("NU", "33.8", "67.6") for c in ["R1", "R2", "R4", "R5", "R6", "Rg", "NONCONV"]}
        d["R3"] = ("num", "5.5", "11")
        return d
    return {c: ("UE" if nf == "amf" else "meas", "33.8", "67.6") for c in ["R1", "R2", "R3", "R4", "R5", "R6", "Rg", "NONCONV"]}


def labels(s):
    if not s:
        return set()
    return set(s.get("viol", [])) | set(s.get("vid", []))


def row(r, src):
    out = {"src": os.path.basename(src), "id": r.get("id"), "image": r.get("image"), "proc": r.get("proc"),
           "nf": r.get("nf"), "boundary": r.get("boundary") or r.get("position") or "", "seed": r.get("seed"),
           "downtime": r.get("downtime"), "t_offset": r.get("t_offset"), "netem_ms": r.get("netem_ms"),
           "fault_fired": r.get("fault_fired"), "gnb_tool_crash": r.get("gnb_tool_crash"),
           "victim_last_line": ((r.get("victim_last_lines") or [""])[-1] or "")[-160:], "error": (r.get("error") or "")[:160]}
    snaps = r.get("snap") or {}
    for t in ["5.5", "11", "26", "33.8", "36", "67.6", "72"]:
        out[f"viol_{t}"] = ";".join(sorted(labels(snaps.get(t))))
    verdict = {}
    for c, (cls, a, b) in classes(r.get("nf")).items():
        va = any(conj(x) == c for x in labels(snaps.get(a)))
        vb = any(conj(x) == c for x in labels(snaps.get(b)))
        v = "persistent" if va and vb else "transient" if va else "late" if vb else "ok"
        if v != "ok":
            verdict[c] = f"{v}({cls})"
    out["conjunct_verdicts"] = ";".join(f"{k}:{v}" for k, v in sorted(verdict.items()))
    pers = sorted(k for k, v in verdict.items() if v.startswith("persistent") or v.startswith("late"))
    out["persistent_conjuncts"] = ";".join(pers)
    out["persistent_numeric"] = ";".join(k for k in pers if "(num)" in verdict[k])
    out["persistent_NU"] = ";".join(k for k in pers if "(NU)" in verdict[k])
    out["persistent_UE"] = ";".join(k for k in pers if "(UE)" in verdict[k] or "(meas)" in verdict[k])
    nu = r.get("next_use") or {}
    out["next_use"] = ";".join(f"{k}:{v}" for k, v in nu.items())
    out["next_use_all_ok"] = r.get("next_use_all_ok")
    after = set(r.get("viol_after_next_use") or []) | {v[0] for v in (r.get("vid_after_next_use") or [])}
    out["viol_after_next_use"] = ";".join(sorted(after))
    end = labels(snaps.get("67.6"))
    out["lazy_repair_v1"] = bool(end) and r.get("viol_after_next_use") is not None and not r.get("viol_after_next_use")
    out["lazy_repair_v2"] = bool(end) and not after and bool(r.get("next_use_all_ok"))
    out["liveness_ok"] = r.get("liveness_ok")
    out["crash_oracle"] = ";".join(r.get("crash_oracle") or [])
    out["t_conv_all"] = r.get("t_conv_all")
    out["restart_ready_s"] = r.get("restart_ready_s")
    out["wall_s"] = r.get("wall_s")
    out["pcap"] = r.get("pcap")
    out["logs"] = r.get("logs")
    # UERANSIM artefact: a UE process failed to create its TUN device (two nr-ue processes racing for uesimtunN)
    try:
        txt = gzip.open(os.path.join(os.path.dirname(src), r["logs"]), "rt").read()
        out["ue_tun_alloc_failure"] = "TUN allocation failure" in txt
    except Exception:
        out["ue_tun_alloc_failure"] = None
    return out


if __name__ == "__main__":
    rows = []
    for p in sys.argv[2:]:
        for line in open(p):
            try:
                rows.append(row(json.loads(line), p))
            except Exception as e:
                print("skip", p, e)
    if rows:
        with open(sys.argv[1], "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
    print(len(rows), "rows ->", sys.argv[1])
