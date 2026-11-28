"""Run one fault schedule end to end and return a JSON-able record."""
import gzip
import json
import os
import random
import threading
import time

from . import capture, dock, inject, observe, oracle, testbed, workload
from .testbed import CORE_NFS, c

DELTA = {"open5gs": 26.0}          # Delta_core from artifact/results/timers/delta.csv (real, from source)
RESULTS = os.environ.get("R5G_OUT") or os.path.join(os.path.dirname(dock.TESTBED), "results", "real")
# Campaign 2 per-conjunct snapshot times (s after restart): legacy Delta_core 26 / window 36, UPF-restart
# Delta_j = T_b + 23.5 = 33.8 and 2*Delta_j = 67.6 (Table 4), SMF-restart R3 Delta_j = T_b + 5 ~ 5.5 (2x = 11).
SNAP_T = [5.5, 11.0, 26.0, 33.8, 36.0, 67.6]

# Boundary triggers: (NF whose log marks the boundary, regex). Verified against e85748e INFO logs.
BOUNDARIES = {
    # registration (AMF log lines bracket the AUSF/UDM/PCF calls; verified on e85748e INFO logs)
    "reg.ngap_initial_ue": ("amf", r"InitialUEMessage"),          # gNB-UE / NGAP ids allocated
    "reg.amf_ue_added": ("amf", r"\[Added\] Number of AMF-UEs"),  # AMF UE context created
    "reg.security_done": ("amf", r"Security mode complete"),       # AUSF auth ctx done, before UDM UECM
    "reg.udm_done": ("amf", r"nudm-handler\.c"),                    # UDM UECM/SDM response handled
    "reg.complete": ("amf", r"Registration complete"),             # GUTI committed
    # PDU session establishment
    "pdu.amf_sess_added": ("amf", r"\[Added\] Number of AMF-Sessions"),
    "pdu.smf_sess_added": ("smf", r"\[Added\] Number of SMF-Sessions"),   # SM context (ref) created
    "pdu.ip_allocated": ("smf", r"UE SUPI\[imsi-\d+\] DNN\[\S+\] IPv4\["),
    "pdu.upf_sess_added": ("upf", r"(?i)\[Added\] Number of UPF-Sessions"),  # PFCP session created
    "pdu.n2_modify": ("amf", r"sm-contexts/\{smContextRef\}/modify"),  # N2 SM info -> SMF update
    # PDU session release
    "rel.n2_released": ("amf", r"N2-RELEASED"),
    "rel.upf_sess_removed": ("upf", r"(?i)\[Removed\] Number of UPF-Sessions"),
    "rel.smf_sess_removed": ("smf", r"\[Removed\] Number of SMF-Sessions"),
    "rel.amf_sess_removed": ("amf", r"\[Removed\] Number of AMF-Sessions"),
    # deregistration
    "dereg.amf_rx": ("amf", r"Deregistration request"),
    "dereg.sm_release": ("amf", r"Release SM context \[204\]"),
    "dereg.smf_sess_removed": ("smf", r"\[Removed\] Number of SMF-Sessions"),
    "dereg.ue_ctx_release": ("amf", r"UE Context Release"),
}


def reset(netem_ms=0, netem_per_nf=None):
    """Fast reset between schedules: kill UEs, hard-restart every NF and the gNB (fresh volatile state)."""
    dock.dexec(c("ue"), "pkill -9 nr-ue; true")
    names = [c(n) for n in CORE_NFS] + [c("gnb")]
    dock.docker("kill", "-s", "KILL", *names, check=False)
    t = time.time()
    dock.docker("start", c("nrf"), c("scp"))
    time.sleep(1.0)
    dock.docker("start", *[c(n) for n in CORE_NFS if n not in ("nrf", "scp")])
    # wait for SMF-UPF association and AMF NRF registration after this restart
    for _ in range(120):
        if "PFCP associated" in dock.logs(c("smf"), since=t) and "NF registered" in dock.logs(c("amf"), since=t):
            break
        time.sleep(0.5)
    else:
        raise RuntimeError("reset: core not ready")
    dock.start(c("gnb"))
    for _ in range(60):
        if "NG Setup procedure is successful" in dock.logs(c("gnb"), since=t):
            break
        time.sleep(0.5)
    else:
        raise RuntimeError("reset: gNB not ready")
    if netem_ms or netem_per_nf:
        for n in CORE_NFS:
            testbed.netem(n, (netem_per_nf or {}).get(n, netem_ms))
    time.sleep(1.0)
    return time.time() - t


def bring_to(state, ues):
    """Pre-state for the procedure under test: 'none' | 'registered' | 'session'."""
    if state == "none":
        return
    for i in ues:
        workload.power_on(i)
    for i in ues:
        if workload.wait_registered(i, 45) is None:
            raise RuntimeError(f"pre-state: UE{i} failed to register")
    time.sleep(1.5)  # UERANSIM drops NAS sent during the post-registration RRC/UAC window (T3580=16 s)
    if state == "session":
        for i in ues:
            workload.ps_establish(i)
        for i in ues:
            if workload.wait_session(i, 40)[0] is None:
                raise RuntimeError(f"pre-state: UE{i} failed to establish PDU session")


PRE = {"reg": "none", "pdu": "registered", "rel": "session", "dereg": "session", "idle": "session"}


def do_procedure(proc, ues, rng, stagger):
    """Fire procedure `proc` for all UEs in a seed-determined order with random stagger."""
    order = list(ues)
    rng.shuffle(order)
    t = []
    for i in order:
        if proc == "reg":
            t.append(workload.power_on(i))
        elif proc == "pdu":
            t.append(workload.ps_establish(i)[0])
        elif proc == "rel":
            t.append(workload.ps_release(i, 1)[0])
        elif proc == "dereg":
            t.append(workload.deregister(i)[0])
        if stagger:
            time.sleep(rng.uniform(0, stagger))
    return order, t


def nfs_running():
    return {n: dock.running(c(n)) for n in CORE_NFS + ["gnb"]}


def save_logs(run_id, since, outdir):
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, f"{run_id}.log.gz")
    with gzip.open(path, "wt") as f:
        for n in CORE_NFS + ["gnb"]:
            f.write(f"\n===== {n} =====\n")
            f.write(dock.logs(c(n), since=since))
        f.write("\n===== ue (nr-ue logs) =====\n")
        f.write(dock.dexec(c("ue"), "tail -n 200 /tmp/ue*.log").stdout)
    return os.path.relpath(path, RESULTS)


def run(spec, outdir, log=print):
    """spec keys: id, k, proc, nf, boundary | t_offset, mode(crash|stop|pause|none), downtime, seed,
    window (s after fault end), poll (s), netem_ms, stagger (s), lazy (bool)."""
    rng = random.Random(spec.get("seed", 0))
    ues = list(range(1, spec["k"] + 1))
    rec = dict(spec)
    t_begin = time.time()
    pcap_path = None
    if spec.get("pcap", True):
        pcap_path = os.path.join(outdir, "pcap", f"{spec['id']}.pcap")
        capture.start(pcap_path)
    rec["reset_s"] = round(reset(spec.get("netem_ms", 0), spec.get("netem_per_nf")), 2)
    bring_to(PRE[spec["proc"]], ues)
    if spec.get("netem_after_pre"):      # campaign 2 (A4' audit): widen windows only for the procedure under test
        for n, ms in spec["netem_after_pre"].items():
            testbed.netem(n, ms)
    time.sleep(0.5)
    t_proc = time.time()
    nf, mode, dt = spec.get("nf"), spec.get("mode", "crash"), spec.get("downtime", 0.0)

    def fault():
        if mode == "crash":
            dock.kill(c(nf))
        elif mode == "stop":
            dock.docker("stop", "-t", "2", c(nf), check=False)
        elif mode == "pause":
            dock.pause(c(nf))

    trig = None
    if mode != "none" and (spec.get("boundary") or spec.get("trigger")):
        if spec.get("trigger"):            # custom (on, regex) trigger, e.g. for the A4' audit
            on, pat = spec["trigger"]
        else:
            on, pat = BOUNDARIES[spec["boundary"]]
        trig = inject.Trigger(on, pat, fault, delay=spec.get("trigger_delay", 0.0)).arm()
    order, _ = do_procedure(spec["proc"], ues, rng, spec.get("stagger", 0.3))
    rec["ue_order"] = order
    t_fault = None
    if trig:
        t_fault = trig.wait(timeout=40)
        rec["trigger_line"] = trig.line
    elif mode != "none" and spec.get("t_offset") is not None:
        # time-based (pod-kill baseline): fault at t_proc + offset
        time.sleep(max(0.0, t_proc + spec["t_offset"] - time.time()))
        fault()
        t_fault = time.time()
    rec["fault_fired"] = t_fault is not None
    rec["t_fault_abs"] = t_fault
    if t_fault is not None:
        rec["fault_at_s"] = round(t_fault - t_proc, 3)
        # effective crash point: last lines the victim printed before the fault
        tail = dock.logs(c(nf), since=t_proc).strip().splitlines()
        rec["victim_last_lines"] = [l[31:] for l in tail[-3:]]
        if dt:
            time.sleep(dt)
        if mode == "pause":
            dock.unpause(c(nf))
        else:
            dock.start(c(nf))
        t_restart = time.time()
        if spec.get("netem_ms"):
            time.sleep(0.3)
            testbed.netem(nf, (spec.get("netem_per_nf") or {}).get(nf, spec["netem_ms"]))
        # measure readiness in the background so R polling starts immediately after the restart
        ready_box = {}
        if mode != "pause":
            ready_thr = threading.Thread(
                target=lambda: ready_box.__setitem__("v", inject.restart_ready_time(nf, t_restart)), daemon=True)
            ready_thr.start()
    else:
        t_restart = time.time()
        ready_box = {}
    # allow the procedure itself to finish / time out at the UE before judging
    time.sleep(spec.get("settle", 2.0))
    if spec.get("netem_after_pre"):      # campaign 2: remove the procedure-only delays before observing
        time.sleep(spec.get("netem_clear_delay", 2.0))
        for n in spec["netem_after_pre"]:
            testbed.netem(n, 0) if False else dock.dexec(c(n), "tc qdisc del dev eth0 root 2>/dev/null; true")
    # UERANSIM's nr-gnb aborts ("terminate called recursively") when the AMF's SCTP association drops mid-procedure.
    # A real gNB would re-establish NG; emulate that by restarting the simulator and flag the run.
    rec["gnb_tool_crash"] = False
    if nf != "gnb" and not dock.running(c("gnb")):
        rec["gnb_tool_crash"] = True
        dock.start(c("gnb"))
        time.sleep(3)
    # --- observation window: poll R, record convergence ---
    delta = DELTA["open5gs"]
    window = spec.get("window", 72.0)
    series = []
    while True:
        el = time.time() - t_restart
        if nf != "gnb" and not dock.running(c("gnb")):   # UERANSIM gNB abort watchdog (see above)
            rec["gnb_tool_crash"] = True
            rec.setdefault("gnb_restarted_at_s", []).append(round(el, 2))
            dock.start(c("gnb"))
            time.sleep(3)
        t_abs0 = time.time()                  # revision 2026-11-25: absolute collection window of each snapshot
        snap = oracle.snapshot_id(ues, probes=True)
        t_abs1 = time.time()
        viol = oracle.check_R(snap)
        vid = oracle.check_R_id(snap)
        series.append({"t": round(el, 2), "t_abs0": t_abs0, "t_abs1": t_abs1,
                       "viol": [v[0] for v in viol], "vid": sorted({v[0] for v in vid}),
                       "counts": snap["counts"], "amf_id": snap["amf_id"], "smf_id": snap["smf_id"],
                       "ue_ips": snap["ue_ips"], "dl_ok": snap["dl_ok"], "ues": snap["ues"],
                       "upf_log_ips": snap["upf_log_ips"]})
        if el >= window:
            break
        time.sleep(spec.get("poll", 2.0))
    # verdict at Delta = first sample with t >= delta; persistent = still violated at end of window
    at_delta = next((s for s in series if s["t"] >= delta), series[-1])
    rec["viol_at_delta"] = at_delta["viol"]
    rec["viol_end"] = series[-1]["viol"]
    rec["final_snapshot"] = snap
    rec["final_detail"] = viol
    rec["final_detail_id"] = vid
    # campaign 2: per-conjunct snapshots at Delta_j / 2*Delta_j (first poll at or after t), count- and id-level
    rec["snap"] = {}
    for tt in SNAP_T + [window]:
        smp = next((x for x in series if x["t"] >= tt), None)
        rec["snap"][f"{tt:g}"] = None if smp is None else {"t": smp["t"], "viol": smp["viol"], "vid": smp["vid"]}
    tconv_id = None
    for idx in range(len(series)):
        if all(not x["vid"] and not x["viol"] for x in series[idx:]):
            tconv_id = series[idx]["t"]
            break
    rec["t_conv_all"] = tconv_id
    # convergence time: first sample after which all later samples are clean
    tconv = None
    for idx in range(len(series)):
        if all(not s["viol"] for s in series[idx:]):
            tconv = series[idx]["t"]
            break
    rec["t_conv"] = tconv
    rec["ever_violated"] = any(s["viol"] for s in series)
    rec["series"] = series
    rec["restart_ready_s"] = ready_box.get("v")
    rec["poll_started_s"] = series[0]["t"] if series else None
    # baselines' oracles on the same run
    run_state = nfs_running()
    since_logs = {n: dock.logs(c(n), since=t_proc) for n in ("amf", "smf", "upf")}
    rec["crash_oracle"] = [v[0] for v in oracle.check_crash_only(run_state, since_logs, nf)]
    # liveness oracle (pod-kill baseline): can every UE complete a fresh procedure now?
    if spec.get("lazy", True):
        rec.update(liveness_and_lazy(ues))
    rec["wall_s"] = round(time.time() - t_begin, 1)
    rec["logs"] = save_logs(spec["id"], t_begin, os.path.join(outdir, "logs"))
    if pcap_path:
        rec["pcap"] = os.path.relpath(capture.stop(pcap_path), RESULTS)
    return rec


def liveness_and_lazy(ues):
    """Next-use: for each UE, use its session (uplink ping) or establish one; then re-check R."""
    out = {"next_use": {}}
    for i in ues:
        st = workload.status(i)
        if not st:
            out["next_use"][i] = "ue-dead"
            continue
        if st.get("rm-state") != "RM-REGISTERED":
            workload.power_off(i)
            workload.power_on(i)
            ok = workload.wait_registered(i, 30) is not None
            out["next_use"][i] = "re-register-ok" if ok else "re-register-FAIL"
            continue
        ps = workload.ps_list(i)
        act = [v.get("address") for v in ps.values() if v.get("state") == "PS-ACTIVE"]
        if act:
            ok = observe.ul_probe(act[0])
            out["next_use"][i] = "ul-ok" if ok else "ul-FAIL"
        else:
            workload.ps_establish(i)
            ok = workload.wait_session(i, 25)[0] is not None  # > T3580 (16 s): UERANSIM UAC glitch
            out["next_use"][i] = "pdu-ok" if ok else "pdu-FAIL"
    time.sleep(3)
    snap = oracle.snapshot_id(ues, probes=True)
    out["viol_after_next_use"] = [v[0] for v in oracle.check_R(snap)]
    out["vid_after_next_use"] = [list(v) for v in oracle.check_R_id(snap)]
    out["next_use_all_ok"] = all(str(x).endswith("-ok") for x in out["next_use"].values())
    out["liveness_ok"] = all(not str(x).endswith("FAIL") and x != "ue-dead" for x in out["next_use"].values()) \
        and all(nfs_running().values())
    return out


def write_jsonl(path, rec):
    with open(path, "a") as f:
        f.write(json.dumps(rec, default=str) + "\n")
