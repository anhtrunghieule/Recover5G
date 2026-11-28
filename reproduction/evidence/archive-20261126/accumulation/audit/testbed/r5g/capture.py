"""Campaign 2: packet capture of one testbed instance's bridge (SBI h2c incl. via SCP, NGAP/SCTP, PFCP, GTP-U).

A `tcpdump` container with --net host captures on the instance's Linux bridge (br-<network id>), which sees every
container-to-container frame. MongoDB (27017) and the metrics/dumper scrapes (9090) are filtered out. The capture
is started before the per-schedule reset, so every HTTP/2 connection (and its HPACK context) is captured from its
first frame and tshark can decode paths, status codes and Location headers.
"""
import gzip
import os
import shutil
import time

from . import dock
from .testbed import PREFIX

IMAGE = "r5g/open5gs:e85748e"   # has tcpdump


def bridge():
    net = f"{PREFIX}_core"
    nid = dock.docker("network", "inspect", "-f", "{{.Id}}", net).stdout.strip()
    return "br-" + nid[:12]


def start(path):
    """Start capturing into host path `path` (must be under $HOME, which Colima mounts at the same path)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    name = f"{PREFIX}-cap"
    dock.docker("rm", "-f", name, check=False)
    d, f = os.path.dirname(path), os.path.basename(path)
    dock.docker("run", "-d", "--name", name, "--net", "host", "--cap-add", "NET_ADMIN", "--cap-add", "NET_RAW",
                "-v", f"{d}:/cap", IMAGE, "tcpdump", "-i", bridge(), "-s", "0", "-U", "-w", f"/cap/{f}",
                os.environ.get("R5G_CAP_FILTER", "not port 27017 and not port 9090"))
    time.sleep(0.8)
    return name


def stop(path, compress=True):
    name = f"{PREFIX}-cap"
    dock.docker("stop", "-t", "1", name, check=False)
    dock.docker("rm", "-f", name, check=False)
    if compress and os.path.exists(path):
        with open(path, "rb") as fi, gzip.open(path + ".gz", "wb", compresslevel=6) as fo:
            shutil.copyfileobj(fi, fo)
        os.remove(path)
        return path + ".gz"
    return path
