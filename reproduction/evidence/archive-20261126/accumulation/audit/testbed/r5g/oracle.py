"""Cross-NF consistency relation R (paper Def. 'R') evaluated on an observed snapshot, plus the
crash-only / liveness oracles used as baselines.

Projection available on Open5GS without NF instrumentation:
  * per-NF gauges (AMF UEs/sessions, SMF UEs/SM sessions/PFCP sessions, UPF sessions) from /metrics;
  * per-UE truth from UERANSIM (RM/CM state, PS-ACTIVE sessions and their IPs);
  * data-plane probes (downlink ping from N6 through the UPF to each active UE IP);
  * UE IPs installed by the current UPF incarnation (INFO logs).
Count-level checks are sound for detecting a violated bijection (unequal counts imply no bijection) but can
miss count-preserving swaps; this limitation is documented in the README.
"""
from . import observe


def snapshot(ues, probes=True):
    cnt = observe.counts()
    view = observe.ue_view(ues)
    ue_ips = {i: ip for i, v in view.items() for ip in v["sessions"].values()}
    probe = {}
    if probes and cnt.get("upf_sess") is not None:
        for i, ip in ue_ips.items():
            probe[i] = observe.dl_probe(ip)
    try:
        upf_ips = observe.upf_session_ips()
    except Exception:
        upf_ips = []
    return {"counts": cnt, "ues": view, "ue_ips": ue_ips, "dl_ok": probe, "upf_log_ips": upf_ips}


def check_R(s):
    """Return list of (conjunct, detail) violations. Empty list means no observed proxy violation, not full R or complete data."""
    v = []
    c = s["counts"]
    ues = s["ues"]
    n_ue_reg = sum(1 for x in ues.values() if x["rm"] == "RM-REGISTERED")
    n_ue_sess = sum(len(x["sessions"]) for x in ues.values())
    down = [k for k in ("amf_sess", "smf_sess", "upf_sess") if c.get(k) is None]
    if down:
        v.append(("NONCONV", f"NF metrics unreachable: {down}"))
        return v
    # R1 dangling: a holder references a session the next NF does not have
    if c["amf_sess"] > c["smf_sess"]:
        v.append(("R1-dangling", f"AMF sessions {c['amf_sess']} > SMF sessions {c['smf_sess']}"))
    if n_ue_sess > c["smf_sess"]:
        v.append(("R1-dangling-UE", f"UE PS-ACTIVE {n_ue_sess} > SMF sessions {c['smf_sess']}"))
    # R2 orphan SMF context
    if c["smf_sess"] > c["amf_sess"]:
        v.append(("R2-orphan-SMF", f"SMF sessions {c['smf_sess']} > AMF sessions {c['amf_sess']}"))
    if c["smf_sess"] > n_ue_sess:
        v.append(("R2-orphan-SMF-vs-UE", f"SMF sessions {c['smf_sess']} > UE PS-ACTIVE {n_ue_sess}"))
    # R3 N4 bijection
    if c["upf_sess"] != c["smf_sess"]:
        kind = "R3-orphan-UPF" if c["upf_sess"] > c["smf_sess"] else "R3-missing-UPF"
        v.append((kind, f"UPF sessions {c['upf_sess']} vs SMF sessions {c['smf_sess']}"))
    # R4 black hole: CP believes active, DL does not reach UE
    for i, ok in s["dl_ok"].items():
        if not ok:
            v.append(("R4-blackhole", f"UE{i} {s['ue_ips'][i]} PS-ACTIVE but DL probe via UPF fails"))
    # R5 registration consistency (AMF vs UE)
    if c["amf_ue"] < n_ue_reg:
        v.append(("R5-amf-lost-ue", f"AMF UE contexts {c['amf_ue']} < UEs RM-REGISTERED {n_ue_reg}"))
    if c["amf_ue"] > n_ue_reg:
        v.append(("R5-stale-amf-ue", f"AMF UE contexts {c['amf_ue']} > UEs RM-REGISTERED {n_ue_reg}"))
    # R6 leak / stale identifiers at the UPF (log-derived)
    live = set(s["ue_ips"].values())
    stale = [ip for ip in s["upf_log_ips"] if ip and ip not in live]
    if stale and c["upf_sess"] > len(live):
        v.append(("R6-leak-UPF-ip", f"UPF installed IPs not held by any UE: {sorted(set(stale))}"))
    # R_g alias
    ips = list(s["ue_ips"].values())
    if len(ips) != len(set(ips)):
        v.append(("Rg-alias", f"duplicate UE IPs {ips}"))
    return v


def check_crash_only(nfs_running, logs_since_fault, killed_nf):
    """Crash-only oracle: some NF died that we did not kill, or an assertion/FATAL appeared."""
    v = []
    for nf, up in nfs_running.items():
        if not up:
            v.append(("CRASH", f"{nf} not running"))
    for nf, txt in logs_since_fault.items():
        if "Assertion" in txt or "FATAL" in txt or "Segmentation" in txt:
            v.append(("CRASH-log", f"{nf}: assertion/fatal in log"))
    return v


# --- campaign 2: identity-level R (bindings, not counts) -------------------------------------------------------
# Readouts: AMF /ue-info -> {(supi, psi)}, SMF /pdu-info -> {(supi, psi) -> UE IP, UPF TEID}, UERANSIM -> per UE
# {psi -> IP} and RM state. UPF-side identities (CP/UP SEID, UE IP per PFCP session) come from the PFCP pcap
# offline (analyze_c2.py); smContextRef bindings come from the SBI pcap offline.
from .testbed import imsi as _imsi


def snapshot_id(ues, probes=True):
    s = snapshot(ues, probes=probes)
    s["amf_id"] = observe.amf_ue_info()
    s["smf_id"] = observe.smf_pdu_info()
    from .verdict import assess_observation
    s["assessment"] = assess_observation(s)
    return s


def check_R_id(s):
    """Identity-level conjuncts. Returns list of (label, detail)."""
    v = []
    amf, smf = s.get("amf_id"), s.get("smf_id")
    if amf is None or smf is None:
        return [("NONCONV-id", f"dumper unreachable amf={amf is None} smf={smf is None}")]
    ue = {}          # supi -> {'rm':..., 'psis': {psi: ip}}
    for i, x in s["ues"].items():
        ue[_imsi(int(i))] = {"rm": x["rm"], "psis": {int(k): ip for k, ip in x["sessions"].items()}}
    A = {(u, p) for u, d in amf.items() for p in d["psis"]}
    S = {(u, p): b for u, d in smf.items() for p, b in d.items()}
    U = {(u, p): ip for u, d in ue.items() for p, ip in d["psis"].items()}
    for k in sorted(A - set(S)):
        v.append(("R1id-dangling-AMF", f"AMF holds {k[0]} PSI {k[1]}; SMF has no such session"))
    for k in sorted(set(U) - set(S)):
        v.append(("R1id-dangling-UE", f"UE {k[0]} PSI {k[1]} ({U[k]}) PS-ACTIVE; SMF has no such session"))
    for k in sorted(set(S) - A):
        v.append(("R2id-orphan-SMF-vs-AMF", f"SMF {k[0]} PSI {k[1]} ({S[k]['ip']}) unknown to AMF"))
    for k in sorted(set(S) - set(U)):
        if k[0] in ue:   # only for UEs we drive
            v.append(("R2id-orphan-SMF-vs-UE", f"SMF {k[0]} PSI {k[1]} ({S[k]['ip']}) not active at UE"))
    # binding mismatch: same (supi, psi) but different UE IP at UE vs SMF
    for k in sorted(set(U) & set(S)):
        if U[k] != S[k]["ip"]:
            v.append(("R6id-ip-mismatch", f"{k[0]} PSI {k[1]}: UE {U[k]} vs SMF {S[k]['ip']}"))
    # alias: one UE IP bound to two different (supi, psi) across SMF and UE views
    owners = {}
    for k, b in S.items():
        owners.setdefault(b["ip"], set()).add(("smf",) + k)
    for k, ip in U.items():
        owners.setdefault(ip, set()).add(("ue",) + k)
    for ip, o in owners.items():
        keys = {(x[1], x[2]) for x in o}
        if ip and len(keys) > 1:
            v.append(("Rg-id-alias-ip", f"{ip} bound to {sorted(o)}"))
    # leak: SMF session (IP held) that neither the AMF nor the UE references
    for k in sorted(set(S) - A - set(U)):
        v.append(("R6id-leak-ip", f"SMF holds {S[k]['ip']} for {k[0]} PSI {k[1]}: no AMF or UE reference"))
    # registration (R5) by identity
    reg = {u for u, d in ue.items() if d["rm"] == "RM-REGISTERED"}
    for u in sorted(reg - set(amf)):
        v.append(("R5id-amf-lost-ue", f"{u} RM-REGISTERED at UE; AMF has no context"))
    for u in sorted(set(amf) - reg):
        if u in ue:
            v.append(("R5id-stale-amf-ue", f"AMF holds {u}; UE not RM-REGISTERED"))
    return v
