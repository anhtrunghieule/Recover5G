#!/usr/bin/env python3
"""Campaign 2: identity-level decode of a testbed pcap (tshark in the r5g/tshark:1 container).

Extracts, per pcap:
  sbi   : HTTP/2 SM-context traffic (AMF<->SCP<->SMF), request (method, path) paired with response (status,
          location) per TCP stream + HTTP/2 stream id -> smContextRef issuance (201 Location) and use (modify/release)
  pfcp  : session establishment/modification/deletion requests/responses: SEIDs, UE IPv4, cause; association setup
          and heartbeat Recovery Time Stamps
  ngap  : NGAP procedure codes with AMF/RAN UE NGAP IDs, PDU session IDs and (null-ciphered) 5GSM message types
  gtpu  : GTP-U Error Indications (message type 26)
and derives: refs issued per SMF incarnation (an incarnation starts at each 201 sequence restart), every request to
a ref with its status, refs reused across incarnations, and PFCP sessions alive at the end per UPF SEID.

  python3 c2/pcap_ids.py <pcap.gz> [...]     -> writes <pcap>.ids.json next to the pcap, prints a summary
"""
import collections, gzip, json, os, subprocess, sys

IMG = "r5g/tshark:1"
CTX = os.environ.get("DOCKER_CONTEXT", "colima-recover5g")


def tshark(pcap, filt, fields, extra=()):
    d, f = os.path.dirname(os.path.abspath(pcap)), os.path.basename(pcap)
    cmd = f"gunzip -c /p/{f} > /tmp/x.pcap 2>/dev/null || cp /p/{f} /tmp/x.pcap; tshark -r /tmp/x.pcap " \
          f"-o nas-5gs.null_decipher:TRUE -d tcp.port==7777,http2 -d sctp.port==38412,ngap {' '.join(extra)} -Y '{filt}' -T fields " \
          f"-E separator='\t' -E occurrence=a -E aggregator='|' " + " ".join(f"-e {x}" for x in fields)
    r = subprocess.run(["docker", "--context", CTX, "run", "--rm", "-v", f"{d}:/p:ro", IMG, "sh", "-c", cmd],
                       capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError("Packet decoding failed: " + r.stderr[-1000:])
    rows = []
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        rows.append(dict(zip(fields, parts + [""] * (len(fields) - len(parts)))))
    return rows


def decode(pcap):
    out = {"pcap": os.path.basename(pcap)}
    sbi = tshark(pcap, "http2.header", ["frame.time_epoch", "ip.src", "ip.dst", "tcp.stream", "http2.streamid",
                                       "http2.headers.method", "http2.headers.path", "http2.headers.status",
                                       "http2.headers.location"])
    req, ev = {}, []
    for r in sbi:
        sids = r["http2.streamid"].split("|")
        meth, path = r["http2.headers.method"].split("|"), r["http2.headers.path"].split("|")
        st, loc = r["http2.headers.status"].split("|"), r["http2.headers.location"].split("|")
        if path and path[0]:
            for i, p in enumerate(path):
                if "sm-contexts" in p:
                    sid = sids[min(i, len(sids) - 1)]
                    req[(r["tcp.stream"], sid)] = {"t": float(r["frame.time_epoch"]), "src": r["ip.src"],
                                                   "dst": r["ip.dst"], "method": meth[min(i, len(meth) - 1)], "path": p}
        if st and st[0]:
            for i, s in enumerate(st):
                sid = sids[min(i, len(sids) - 1)]
                q = req.pop((r["tcp.stream"], sid), None)
                if q:
                    q.update(status=int(s), t_rsp=float(r["frame.time_epoch"]),
                             location=(loc[i] if i < len(loc) else "") or None)
                    ev.append(q)
    for q in req.values():
        q["status"] = None
        ev.append(q)
    ev.sort(key=lambda x: x["t"])
    out["sbi"] = ev
    pf = tshark(pcap, "pfcp", ["frame.time_epoch", "ip.src", "ip.dst", "pfcp.msg_type", "pfcp.seid",
                               "pfcp.ue_ip_addr_ipv4", "pfcp.cause", "pfcp.recovery_time_stamp", "pfcp.seqno"])
    out["pfcp"] = [{"t": float(r["frame.time_epoch"]), "src": r["ip.src"], "dst": r["ip.dst"],
                    "type": int(r["pfcp.msg_type"].split("|")[0] or 0), "seid": r["pfcp.seid"],
                    "ue_ip": r["pfcp.ue_ip_addr_ipv4"], "cause": r["pfcp.cause"], "rts": r["pfcp.recovery_time_stamp"],
                    "seq": r["pfcp.seqno"]} for r in pf if int(r["pfcp.msg_type"].split("|")[0] or 0) not in (1, 2)]
    hb = [r for r in pf if int(r["pfcp.msg_type"].split("|")[0] or 0) in (1, 2)]
    out["pfcp_heartbeats"] = [{"t": float(r["frame.time_epoch"]), "src": r["ip.src"], "type": int(r["pfcp.msg_type"].split("|")[0]),
                               "rts": r["pfcp.recovery_time_stamp"]} for r in hb]
    ng = tshark(pcap, "ngap", ["frame.time_epoch", "ip.src", "ngap.procedureCode", "ngap.AMF_UE_NGAP_ID",
                               "ngap.RAN_UE_NGAP_ID", "ngap.pDUSessionID", "nas-5gs.mm.message_type",
                               "nas-5gs.sm.message_type", "nas-5gs.pdu_session_id", "nas-5gs.mm.req_type",
                               "nas-5gs.sm.5gsm_cause", "nas-5gs.mm.5gmm_cause"])
    out["ngap"] = [{k.split(".")[-1]: v for k, v in r.items()} for r in ng]
    gt = tshark(pcap, "gtp.message == 26", ["frame.time_epoch", "ip.src", "ip.dst", "gtp.teid"])
    out["gtpu_error_indication"] = gt
    # derived: smContextRef issuance per SMF incarnation and uses
    issued, inc, last = [], 0, None
    for q in ev:
        if q["method"] == "POST" and q["path"].rstrip("/").endswith("sm-contexts") and q.get("status") == 201 \
                and q.get("location") and q["src"].endswith(".200"):    # SCP->AMF leg would be dst=AMF; keep SMF->SCP rsp
            ref = q["location"].rstrip("/").split("/")[-1]
            issued.append({"t": q["t"], "ref": ref})
    # incarnation boundaries: SMF PFCP association setup requests (type 5) from the SMF
    smf_assoc = [p["t"] for p in out["pfcp"] if p["type"] == 5]
    for it in issued:
        it["smf_incarnation"] = sum(1 for t in smf_assoc if t <= it["t"])
    out["refs_issued"] = issued
    by_ref = collections.defaultdict(set)
    for it in issued:
        by_ref[it["ref"]].add(it["smf_incarnation"])
    out["refs_reused_across_incarnations"] = sorted(r for r, s in by_ref.items() if len(s) > 1)
    out["ref_uses"] = [{"t": q["t"], "src": q["src"], "dst": q["dst"], "method": q["method"], "path": q["path"],
                        "status": q.get("status")} for q in ev if "/sm-contexts/" in q["path"]]
    return out


if __name__ == "__main__":
    for p in sys.argv[1:]:
        o = decode(p)
        dst = p[:-3] if p.endswith(".gz") else p
        json.dump(o, open(dst + ".ids.json", "w"), indent=0, default=str)
        st = collections.Counter((u["path"].split("/sm-contexts/")[-1].split("/")[-1] if "/" in u["path"].split("/sm-contexts/")[-1] else "update", u["status"]) for u in o["ref_uses"])
        print(os.path.basename(p), "refs_issued", [(x["ref"], x["smf_incarnation"]) for x in o["refs_issued"]],
              "reused", o["refs_reused_across_incarnations"], "uses(status)", dict(st),
              "pfcp", collections.Counter(x["type"] for x in o["pfcp"]), "gtpu_err_ind", len(o["gtpu_error_indication"]))
