"""Fault injection.

Faults (paper's A2 crash-restart plus the downtime dimension requested by reviewers):
  * crash-restart:  SIGKILL the NF container, `docker start` immediately (downtime ~ 0 s);
  * crash-downtime: SIGKILL, keep it down for D seconds, then start (D swept around heartbeat give-up);
  * pause:          `docker pause` (cgroup freezer) for D seconds, then unpause (no state loss: a
                    partition / hung process rather than a crash).

Crash points: a fault is armed on a *trigger* = first log line of NF `on` matching regex `pattern`
after arming (a boundary: the log line Open5GS emits right after a resource is created). A streaming
`docker logs -f` reader fires the fault on the matching line; `delay` adds an optional offset.
"""
import re
import subprocess
import threading
import time

from . import dock
from .testbed import c, netem


class Trigger:
    def __init__(self, on, pattern, action, delay=0.0):
        self.on, self.rx, self.action, self.delay = on, re.compile(pattern), action, delay
        self.fired_at = None
        self.line = None
        self._proc = None
        self._thr = None

    def arm(self):
        since = f"{time.time():.3f}"
        self._proc = subprocess.Popen(["docker", "logs", "-f", "--since", since, c(self.on)],
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                      env=dock.ENV, bufsize=1)
        self._thr = threading.Thread(target=self._run, daemon=True)
        self._thr.start()
        time.sleep(0.15)  # let `docker logs -f` attach
        return self

    def _run(self):
        for line in self._proc.stdout:
            if self.rx.search(line):
                if self.delay:
                    time.sleep(self.delay)
                self.fired_at = time.time()
                self.line = line.strip()
                try:
                    self.action()
                finally:
                    self._proc.kill()
                return

    def wait(self, timeout):
        self._thr.join(timeout)
        if self._proc and self._proc.poll() is None:
            self._proc.kill()
        return self.fired_at


def crash(nf, downtime=0.0, netem_ms=0):
    """SIGKILL nf, keep it down `downtime` seconds, restart. Returns dict of timestamps."""
    t_kill = dock.kill(c(nf))
    if downtime:
        time.sleep(downtime)
    t_start = dock.start(c(nf))
    if netem_ms:
        time.sleep(0.3)
        netem(nf, netem_ms)
    return {"t_kill": t_kill, "t_start": t_start}


def stop_start(nf, downtime):
    """Graceful `docker stop` (SIGTERM) then start after downtime: reviewers' #4892 recipe."""
    t0 = time.time()
    dock.docker("stop", "-t", "2", c(nf), check=False)
    time.sleep(max(0.0, downtime - (time.time() - t0)))
    t1 = dock.start(c(nf))
    return {"t_kill": t0, "t_start": t1}


def freeze(nf, duration):
    t0 = dock.pause(c(nf))
    time.sleep(duration)
    t1 = dock.unpause(c(nf))
    return {"t_kill": t0, "t_start": t1}


def restart_ready_time(nf, t_start, timeout=30):
    """Seconds from `docker start` until the NF logs its readiness marker again."""
    marker = {"upf": r"PFCP associated", "smf": r"PFCP associated", "amf": r"NF registered",
              "nrf": r"(NRF initialize|Open5GS daemon)", "gnb": r"NG Setup procedure is successful"}.get(
        nf, r"NF registered")
    on = "smf" if nf == "upf" else nf
    rx = re.compile(marker)
    t0 = time.time()
    while time.time() - t0 < timeout:
        txt = dock.logs(c(on), since=t_start)
        if rx.search(txt):
            return time.time() - t_start
        time.sleep(0.1)
    return None
