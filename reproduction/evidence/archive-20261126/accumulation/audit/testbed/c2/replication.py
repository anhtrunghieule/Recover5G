#!/usr/bin/env python3
"""Campaign 2: per-candidate reproduction counts, computed from the raw records -> campaign2/replication_c2.csv."""
import csv, json, os, collections
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "results", "real", "campaign2")
rows = []
def add(cand, cond, n, k, crit, src):
    rows.append({"candidate": cand, "condition": cond, "runs": n, "reproduced": k, "criterion": crit, "source": src})
f7 = list(csv.DictReader(open(f"{R}/F7_c2.csv")))
for pre, cond in [("F7-e85748e", "e85748e netem150"), ("F7-pr4485", "e85748e+PR4485 netem150"),
                  ("F7nonetem-e85748e", "e85748e netem0"), ("F7nonetem-pr4485", "e85748e+PR4485 netem0")]:
    xs = [r for r in f7 if r["id"].startswith(pre + "-s")]
    add("F7", cond, len(xs), sum(1 for r in xs if "R1" in r["persistent_conjuncts"].split(";")),
        "R1 persistent at 33.8 and 67.6 s", "F7_c2.csv")
f5 = list(csv.DictReader(open(f"{R}/F5a_c2.csv")))
for suf, cond in [("", "e85748e"), ("-pr4485", "e85748e+PR4485")]:
    xs = [r for r in f5 if (r["id"].endswith("-pr4485") if suf else not r["id"].endswith("-pr4485"))]
    add("F5a", cond, len(xs), sum(1 for r in xs if "R1" in r["persistent_conjuncts"]), "R1 (NU) persistent, next use fails", "F5a_c2.csv")
f4 = collections.defaultdict(list)
for l in open(f"{R}/f4/repro.jsonl"):
    r = json.loads(l)
    tag = r["image"].split(":")[-1] + (" k1 long1600" if "long1600" in r.get("logs", "") else "")
    f4[tag].append(any(v[0] == "R3-missing-UPF" for v in r["R_violations_final"]) and any(v[0] == "R4-blackhole" for v in r["R_violations_final"]))
for tag, v in f4.items():
    add("F4", tag, len(v), sum(v), "final R3-missing-UPF + R4-blackhole after next use", "f4/repro.jsonl")
al = collections.defaultdict(list)
for r in csv.DictReader(open(f"{R}/alias/alias_eval.csv")):
    al[(r["variant"], r["image"].split(":")[-1])].append(int(r["pfcp_deletions_after"]) >= 1 and "sm-contexts/1" in r["amf_requests_after"])
for (v, img), xs in al.items():
    add("F11 smContextRef alias", f"{v} {img}", len(xs), sum(xs), "UE1 request to ref 1 deletes UE2's PFCP session (pcap)", "alias/alias_eval.csv")
fb = [json.loads(l) for l in open(f"{R}/amf/f5b.jsonl")]
add("F12 (F5b follow-up)", "e85748e, gNB p2, re-registration", len(fb),
    sum(1 for r in fb if "R3-orphan-UPF" in (r.get("final") or {}).get("viol", [])), "UPF sessions > SMF after re-registration", "amf/f5b.jsonl")
lz = [json.loads(l) for l in open(f"{R}/lazy/lazy_c2.jsonl")]
for suf, cond in [("", "e85748e"), ("pr4485", "e85748e+PR4485")]:
    xs = [r for r in lz if ("pr4485" in r["id"]) == bool(suf)]
    add("lazy probe (SMF steady state)", cond, len(xs), sum(1 for r in xs if not r.get("lazy_repair_v2")),
        "NOT repaired under v2 rule (R id/count dirty after successful UE actions)", "lazy/lazy_c2.jsonl")
oai = collections.defaultdict(list)
for r in csv.DictReader(open(f"{R}/oai/oai_c2.csv")):
    key = (r["scenario"], r["upf_image"].split("/")[-1], r["smf_image"].split("/")[-1])
    if r["scenario"] == "i33":
        hit = r["victim_session_released"] == "True"
    elif r["scenario"] == "o1":
        hit = r["pfcp_sess_del_reqs"] in ("0", "") and r["upf_replaced_assoc_deletions"] in ("", "0")
    elif r["scenario"] == "o2":
        hit = r["probe_ok_frac"] in ("0.0", "0")
    else:
        hit = r["pfcp_sess_del_reqs"] in ("0", "")
    oai[key].append(hit)
for k, v in oai.items():
    add(f"OAI {k[0]}", f"UPF {k[1]} / SMF {k[2]}", len(v), sum(v), "see oai_c2.csv columns", "oai/oai_c2.csv")
with open(f"{R}/replication_c2.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
for r in rows:
    print(f"{r['candidate']:32s} {r['condition']:40s} {r['reproduced']}/{r['runs']}")
