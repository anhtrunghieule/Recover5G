#!/usr/bin/env python3
"""Decode campaign-2 OAI pcaps with tshark (in the r5g/tshark:1 helper container on the OAI VM).

  python3 decode_c2.py [id ...]          # default: every pcap/*.pcap.gz without a decoded/<id>_pfcp.csv

Writes ../../results/real/campaign2/oai/decoded/<id>_pfcp.csv (non-heartbeat PFCP: time, src, dst, msg type,
SEID(s), Node ID, Recovery Time Stamp, F-SEID IPv4, cause) and <id>_sbi.csv (HTTP/2 on :8080: time, src, dst,
stream, method, path, status, location), excluding NRF traffic.
"""
import glob
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "..", "results", "real", "campaign2", "oai"))
ENV = dict(os.environ, DOCKER_CONTEXT="colima-recover5g-oai")
PFCP_T = {5: "AssocSetupReq", 6: "AssocSetupRsp", 50: "SessEstReq", 51: "SessEstRsp", 52: "SessModReq",
          53: "SessModRsp", 54: "SessDelReq", 55: "SessDelRsp", 56: "SessReportReq", 57: "SessReportRsp",
          1: "HeartbeatReq", 2: "HeartbeatRsp", 9: "AssocReleaseReq", 10: "AssocReleaseRsp"}


def tshark(pcap, args):
    cmd = ["docker", "run", "--rm", "-v", f"{os.path.join(OUT, 'pcap')}:/cap", "r5g/tshark:1", "tshark",
           "-r", f"/cap/{os.path.basename(pcap)}", *args]
    r = subprocess.run(cmd, capture_output=True, text=True, env=ENV, timeout=300)
    return r.stdout


def decode(rid):
    pcap = os.path.join(OUT, "pcap", f"{rid}.pcap.gz")
    os.makedirs(os.path.join(OUT, "decoded"), exist_ok=True)
    pf = tshark(pcap, ["-Y", "pfcp && !(pfcp.msg_type==1 || pfcp.msg_type==2)", "-T", "fields", "-E", "separator=|",
                       "-e", "frame.time_epoch", "-e", "ip.src", "-e", "ip.dst", "-e", "pfcp.msg_type", "-e",
                       "pfcp.seid", "-e", "pfcp.node_id_fqdn", "-e", "pfcp.node_id_ipv4", "-e",
                       "pfcp.recovery_time_stamp", "-e", "pfcp.f_seid.ipv4", "-e", "pfcp.cause"])
    with open(os.path.join(OUT, "decoded", f"{rid}_pfcp.csv"), "w") as f:
        f.write("t_epoch|src|dst|msg|seid|node_id_fqdn|node_id_ipv4|recovery_time_stamp|fseid_ipv4|cause\n")
        for l in pf.splitlines():
            p = l.split("|")
            try:
                p[3] = PFCP_T.get(int(p[3]), p[3])
            except (ValueError, IndexError):
                pass
            f.write("|".join(p) + "\n")
    sb = tshark(pcap, ["-d", "tcp.port==8080,http2", "-Y",
                       "http2.headers.path || http2.headers.status", "-T", "fields", "-E", "separator=|",
                       "-e", "frame.time_epoch", "-e", "ip.src", "-e", "ip.dst", "-e", "http2.streamid", "-e",
                       "http2.headers.method", "-e", "http2.headers.path", "-e", "http2.headers.status", "-e",
                       "http2.headers.location"])
    n = 0
    with open(os.path.join(OUT, "decoded", f"{rid}_sbi.csv"), "w") as f:
        f.write("t_epoch|src|dst|streams|method|path|status|location\n")
        for l in sb.splitlines():
            if "192.168.70.130" in l.split("|")[1:3]:      # NRF traffic
                continue
            f.write(l + "\n")
            n += 1
    return len(pf.splitlines()), n


def main():
    ids = sys.argv[1:] or [os.path.basename(p)[:-8] for p in sorted(glob.glob(os.path.join(OUT, "pcap", "*.pcap.gz")))
                           if not os.path.exists(os.path.join(OUT, "decoded", os.path.basename(p)[:-8] + "_pfcp.csv"))]
    for rid in ids:
        print(rid, decode(rid))


if __name__ == "__main__":
    main()
