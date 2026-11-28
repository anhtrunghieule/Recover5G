"""State observers: Prometheus metrics of each NF, NF logs, UE-side state and data-plane probes."""
import re
import time

from . import dock, workload
from .testbed import NF_IP, NET, c, imsi

# Prometheus gauges exported by Open5GS NFs (names verified against e85748e at runtime; see README).
METRICS = {
    "amf": {"amf_ue": "fivegs_amffunction_rm_registeredsubnbr", "amf_sess": "amf_session",
            "ran_ue": "ran_ue", "gnb": "gnb"},
    "smf": {"smf_ue": "ues_active", "smf_sess": "fivegs_smffunction_sm_sessionnbr",
            "pfcp_sess": "pfcp_sessions_active", "pfcp_peers": "pfcp_peers_active"},
    "upf": {"upf_sess": "fivegs_upffunction_upf_sessionnbr"},
}


def scrape(nf):
    """Return {metric_name: summed value} for an NF's /metrics, or None if unreachable."""
    r = dock.dexec(c("probe"), f"curl -s -m 2 http://{NF_IP[nf]}:9090/metrics", timeout=10)
    if r.returncode != 0 or not r.stdout:
        return None
    vals = {}
    for line in r.stdout.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        m = re.match(r"([a-zA-Z_:][\w:]*)(\{[^}]*\})?\s+([-\d.eE+]+)", line)
        if m:
            vals[m.group(1)] = vals.get(m.group(1), 0.0) + float(m.group(3))
    return vals


def counts():
    """Snapshot of cross-NF counters (None = NF unreachable)."""
    out = {}
    for nf, mp in METRICS.items():
        v = scrape(nf)
        for k, name in mp.items():
            out[k] = None if v is None else int(v.get(name, 0))
    return out


def ue_view(ues):
    """Per-UE view from UERANSIM: registration state + PDU sessions (with IPs)."""
    out = {}
    for i in ues:
        st = workload.status(i)
        ps = workload.ps_list(i) if st else {}
        out[i] = {"rm": st.get("rm-state"), "cm": st.get("cm-state"), "mm": st.get("mm-state"),
                  "sessions": {k: v.get("address") for k, v in ps.items() if v.get("state") == "PS-ACTIVE"}}
    return out


def dl_probe(ip, count=2, wait=1):
    """Downlink probe: ping a UE IP from the UPF's N6 side (ogstun). True if echo replies return."""
    r = dock.dexec(c("upf"), f"ping -c {count} -W {wait} -i 0.2 {ip}", timeout=15)
    return r.returncode == 0


def ul_probe(ip, count=2, wait=1):
    """Uplink probe: ping the UPF gateway from the UE TUN bound to `ip`."""
    r = dock.dexec(c("ue"), f"ping -c {count} -W {wait} -i 0.2 -I {ip} 10.45.0.1", timeout=15)
    return r.returncode == 0


# --- log-derived identity sets ------------------------------------------------------------

RE_SMF_ADD = re.compile(r"UE SUPI\[(imsi-\d+)\] DNN\[(\S+?)\] IPv4\[([\d.]*)\]")
RE_SMF_DEL = re.compile(r"Removed Session: UE IMSI:\[(imsi-\d+)\] DNN:\[(\S+?)\] IPv4:\[([\d.]*)\]")
RE_UPF_ADD = re.compile(r"UE F-SEID\[UP:(0x[0-9a-f]+) CP:(0x[0-9a-f]+)\] APN\[(\S+?)\] PDN-Type\[\d+\] IPv4\[([\d.]*)\]")


def nf_logs(nf, since=None):
    return dock.logs(c(nf), since=since)


def last_start_logs(nf):
    """Logs since the NF's most recent (re)start, identified by the Open5GS banner."""
    txt = nf_logs(nf)
    idx = txt.rfind("Open5GS daemon")
    return txt[idx:] if idx >= 0 else txt


def upf_session_ips():
    """UE IPs the current UPF incarnation has installed and not removed (best effort from INFO logs)."""
    txt = last_start_logs("upf")
    ips = []
    for m in RE_UPF_ADD.finditer(txt):
        ips.append(m.group(4))
    return ips


def grep_count(nf, pattern, since=None):
    return len(re.findall(pattern, nf_logs(nf, since=since)))


def wait_for_log(nf, pattern, since, timeout=30, poll=0.05):
    """Block until `pattern` appears in nf logs after `since`; return detection time or None."""
    rx = re.compile(pattern)
    t0 = time.time()
    while time.time() - t0 < timeout:
        if rx.search(nf_logs(nf, since=since)):
            return time.time()
        time.sleep(poll)
    return None


# --- campaign 2: identity-level readouts (Open5GS JSON dumpers on the metrics port, present at e85748e) ----------
# AMF /ue-info (src/amf/ue-info.c): per UE supi, guti, cm_state, NGAP ids, pdu_sessions[{psi, dnn}].
# SMF /pdu-info (src/smf/pdu-info.c): per UE supi, pdu[{psi, ipv4, n3.gnb.teid, n3.upf.teid, pdu_state}].
import json as _json


def _dump(nf, path):
    r = dock.dexec(c("probe"), f"curl -s -m 3 'http://{NF_IP[nf]}:9090/{path}?page=-1'", timeout=10)
    if r.returncode != 0 or not r.stdout.strip():
        return None
    try:
        return _json.loads(r.stdout)
    except Exception:
        return None


def amf_ue_info():
    """{supi: {'psis': {psi: dnn}, 'guti':..., 'cm':..., 'amf_ue_ngap_id':..., 'ran_ue_ngap_id':...}} or None."""
    d = _dump("amf", "ue-info")
    if d is None:
        return None
    out = {}
    for it in d.get("items", []):
        g = it.get("gnb") or {}
        key = it.get("supi") or f"nosupi:{it.get('suci') or g.get('amf_ue_ngap_id')}"
        out[key] = {"psis": {int(p["psi"]): p.get("dnn") for p in it.get("pdu_sessions", []) if "psi" in p},
                               "guti": it.get("guti"), "cm": it.get("cm_state"),
                               "amf_ue_ngap_id": g.get("amf_ue_ngap_id"), "ran_ue_ngap_id": g.get("ran_ue_ngap_id")}
    return out


def smf_pdu_info():
    """{supi: {psi: {'ip':..., 'upf_teid':..., 'gnb_teid':..., 'state':...}}} or None."""
    d = _dump("smf", "pdu-info")
    if d is None:
        return None
    out = {}
    for it in d.get("items", []):
        m = {}
        for p in it.get("pdu", []):
            n3 = p.get("n3") or {}
            m[int(p.get("psi", 0))] = {"ip": p.get("ipv4"), "upf_teid": (n3.get("upf") or {}).get("teid"),
                                       "gnb_teid": (n3.get("gnb") or {}).get("teid"), "state": p.get("pdu_state")}
        out[it.get("supi") or "nosupi"] = m
    return out


RE_UPF_ADD_TS = re.compile(r"^(\S+) .*UE F-SEID\[UP:(0x[0-9a-f]+) CP:(0x[0-9a-f]+)\] APN\[(\S+?)\] PDN-Type\[\d+\] IPv4\[([\d.]*)\]")
