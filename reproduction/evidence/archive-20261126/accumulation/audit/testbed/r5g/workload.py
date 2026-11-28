"""UE workload driver: UERANSIM nr-ue processes + nr-cli commands inside the r5g-ue container."""
import re
import time

from . import dock
from .testbed import c, imsi

UE = c("ue")


def power_on(i):
    """Start a UE process (triggers initial registration)."""
    dock.dexec(UE, f"nohup nr-ue -c /cfg/ue.yaml -i {imsi(i)} > /tmp/ue{i}.log 2>&1 &")
    return time.time()


def power_off(i):
    """Kill the UE process without signalling (radio loss); the gNB will see RLS loss."""
    dock.dexec(UE, f"pkill -9 -f 'nr-ue -c /cfg/ue.yaml -i {imsi(i)}$' ; true")
    return time.time()


def cli(i, cmd, timeout=15):
    r = dock.dexec(UE, f"nr-cli {imsi(i)} -e '{cmd}'", timeout=timeout)
    return (r.stdout + r.stderr).strip()


def deregister(i):
    t = time.time()
    return t, cli(i, "deregister normal")


def ps_establish(i):
    t = time.time()
    return t, cli(i, "ps-establish IPv4 --sst 1 --dnn internet")


def ps_release(i, psi=1):
    t = time.time()
    return t, cli(i, f"ps-release {psi}")


def ps_release_all(i):
    t = time.time()
    return t, cli(i, "ps-release-all")


def status(i):
    """Parse `nr-cli status` -> dict (rm-state, cm-state, mm-state ...). Empty dict if UE not running."""
    out = cli(i, "status")
    d = {}
    for line in out.splitlines():
        m = re.match(r"\s*([\w-]+):\s*(.*)$", line)
        if m:
            d[m.group(1)] = m.group(2).strip()
    return d


def ps_list(i):
    """Parse `nr-cli ps-list` -> {psi: {'state':..., 'address':...}}."""
    out = cli(i, "ps-list")
    sess, cur = {}, None
    for line in out.splitlines():
        m = re.match(r"\s*PDU Session(\d+):", line)
        if m:
            cur = int(m.group(1))
            sess[cur] = {}
            continue
        m = re.match(r"\s*([\w-]+):\s*(.*)$", line)
        if m and cur is not None:
            sess[cur][m.group(1)] = m.group(2).strip()
    return sess


def tun_addrs():
    """UE TUN interfaces inside the UE container: {ifname: ip}."""
    r = dock.dexec(UE, "ip -o -4 addr show | grep uesimtun || true")
    out = {}
    for line in r.stdout.splitlines():
        m = re.search(r"\d+:\s+(uesimtun\d+)\s+inet\s+([\d.]+)", line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def ue_log(i):
    return dock.dexec(UE, f"cat /tmp/ue{i}.log 2>/dev/null").stdout


def wait_registered(i, timeout=20):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = status(i)
        if st.get("rm-state") == "RM-REGISTERED" and st.get("mm-state", "").startswith("MM-REGISTERED"):
            return time.time() - t0
        time.sleep(0.3)
    return None


def wait_session(i, timeout=20, psi=None):
    t0 = time.time()
    while time.time() - t0 < timeout:
        ps = ps_list(i)
        for k, v in ps.items():
            if (psi is None or k == psi) and v.get("state") == "PS-ACTIVE" and v.get("address"):
                return time.time() - t0, v.get("address")
        time.sleep(0.3)
    return None, None
