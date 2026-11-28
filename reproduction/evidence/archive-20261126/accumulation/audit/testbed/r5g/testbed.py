"""Deploy / tear down the Open5GS + UERANSIM testbed and provision subscribers."""
import os
import time

from . import dock

CORE_NFS = ["nrf", "scp", "ausf", "udm", "udr", "pcf", "nssf", "bsf", "smf", "amf", "upf"]
# Campaign 2: several independent testbed instances can run side by side in the same VM.
# R5G_INST=0 (default) is the campaign-1 testbed: containers r5g-*, subnet 172.22.0.0/24.
# R5G_INST=N>0: containers r5g<N>-*, subnet 172.(22+N).0.0/24, files under inst/<N>/ (see inst.py).
INST = int(os.environ.get("R5G_INST", "0"))
PREFIX = "r5g" if INST == 0 else f"r5g{INST}"
NET = f"172.{22 + INST}.0"
_LAST = {"nrf": 10, "scp": 200, "ausf": 11, "udm": 12, "udr": 20, "pcf": 13, "nssf": 14, "bsf": 15,
         "smf": 4, "amf": 5, "upf": 7, "gnb": 50, "ue": 51, "probe": 60, "mongo": 100}
NF_IP = {k: f"{NET}.{v}" for k, v in _LAST.items()}
KEY = "465B5CE8B199B49FAA5F0A2EE238A6BC"
OPC = "E8ED289DEBA952E4283B54E88E6183CA"
MAX_UES = 8


def imsi(i):
    return f"imsi-99970{i:010d}"


def c(nf):
    return f"{PREFIX}-{nf}"


SUB_JS = r"""
const n = %d;
db = db.getSiblingDB('open5gs');
for (let i = 1; i <= n; i++) {
  const imsi = '99970' + String(i).padStart(10, '0');
  db.subscribers.replaceOne({imsi: imsi}, {
    schema_version: 1, imsi: imsi, msisdn: [], imeisv: [], mme_host: [], mme_realm: [], purge_flag: [],
    security: {k: '%s', op: null, opc: '%s', amf: '8000', sqn: NumberLong(1)},
    ambr: {downlink: {value: 1, unit: 3}, uplink: {value: 1, unit: 3}},
    slice: [{sst: 1, default_indicator: true, session: [{name: 'internet', type: 3,
      qos: {index: 9, arp: {priority_level: 8, pre_emption_capability: 1, pre_emption_vulnerability: 1}},
      ambr: {downlink: {value: 1, unit: 3}, uplink: {value: 1, unit: 3}}, pcc_rule: []}]}],
    access_restriction_data: 32, subscriber_status: 0, operator_determined_barring: 0,
    network_access_mode: 0, subscribed_rau_tau_timer: 12, __v: 0}, {upsert: true});
}
print('subscribers=' + db.subscribers.countDocuments({}));
"""


def provision(n=MAX_UES):
    js = SUB_JS % (n, KEY, OPC)
    for _ in range(30):
        r = dock.sh(["docker", "exec", c("mongo"), "mongosh", "--quiet", "--eval", js], check=False)
        if r.returncode == 0 and "subscribers=" in r.stdout:
            return r.stdout.strip()
        time.sleep(1)
    raise RuntimeError("provisioning failed: " + r.stdout + r.stderr)


def down():
    dock.compose("--profile", "ran", "down", "-v", "--remove-orphans", "-t", "1", check=False)


def up(image=None, netem_ms=0):
    env = {}
    if image:
        env["OPEN5GS_IMAGE"] = image
    down()
    dock.compose("up", "-d", "mongo", "probe", env=env)
    provision()
    dock.compose("up", "-d", *CORE_NFS, env=env)
    wait_core_ready()
    dock.compose("--profile", "ran", "up", "-d", "gnb", "ue", env=env)
    wait_gnb_ready()
    if netem_ms:
        for nf in CORE_NFS:
            netem(nf, netem_ms)
    return time.time()


def netem(nf, ms):
    """Add a fixed egress delay to an NF (widens windows between procedure steps)."""
    if ms:
        dock.dexec(c(nf), f"tc qdisc replace dev eth0 root netem delay {ms}ms")


def wait_core_ready(timeout=90):
    t0 = time.time()
    while time.time() - t0 < timeout:
        smf = dock.logs(c("smf"))
        amf = dock.logs(c("amf"))
        if "PFCP associated" in smf and "NF registered" in amf:
            return time.time() - t0
        time.sleep(0.5)
    raise RuntimeError("core not ready (no PFCP association / AMF NRF registration)")


def wait_gnb_ready(timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if "NG Setup procedure is successful" in dock.logs(c("gnb")):
            return time.time() - t0
        time.sleep(0.5)
    raise RuntimeError("gNB NG setup failed")


def restart_nf(nf, netem_ms=0):
    """SIGKILL + immediate start (paper's primary fault, assumption A2)."""
    tk = dock.kill(c(nf))
    if nf == "upf":
        # the tun device lives in the container netns; the entrypoint recreates it
        pass
    ts = dock.start(c(nf))
    if netem_ms:
        time.sleep(0.3)
        netem(nf, netem_ms)
    return tk, ts


def provenance():
    out = {}
    for img in [os.environ.get("OPEN5GS_IMAGE", "r5g/open5gs:e85748e"), "r5g/ueransim:4f45e18-p1", "mongo:7.0"]:
        out[img] = dock.image_id(img)
    return out
