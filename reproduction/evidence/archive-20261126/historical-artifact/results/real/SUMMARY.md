# Recover5G — REAL testbed results (incremental log)

Status: campaign 1 COMPLETE (2026-11-06, ~3 h wall time); **campaign 2 (round-2 review items) is appended at the end ("# Campaign 2")**. See "At a glance" at the end. Every entry here is a
real measurement on the container testbed in `artifact/testbed/`; nothing is projected.

## Environment
- Host: macOS arm64 (Apple M5 Max). Colima profile `recover5g` (aarch64, VZ, 8 vCPU, 16 GiB), Docker context
  `colima-recover5g`. Kernel 6.8.0-117-generic, `sctp` module loaded.
- Open5GS built from source at pinned `e85748ef3d798fa0b4435c80438e81c41bbe5e13` (2026-11-05, = paper's pinned commit).
- Note: Open5GS commit `fc26daab9b` (2026-11-04, "smf: Restore only operational sessions after UPF restart",
  refs #4892) is an ancestor of `e85748e`, so #4892 is FIXED at the pinned commit; reproduction needs the
  parent `48c0cc0374`. #4877 and #4860 are still OPEN upstream as of 2026-11-06; #4863 (EPC release on UPF
  loss) merged 2026-10-14 (`26f9edd`). PR #4895 is still open.

- **SBI transport (reviewer item 4):** default Open5GS configs (as used) have no `tls:` section → SBI is
  **cleartext HTTP/2 (h2c)** (`nghttp2_server() [http://172.22.0.x]:7777` in every NF log).
- **SCP routing (reviewer item 4): ON.** Every NF's `sbi.client` lists only `scp: http://172.22.0.200:7777` with no
  `delegated` block → AUTO delegation: NF↔NF requests and NRF discovery go through the SCP (Model D-style indirect
  communication). An SBI tap at the SCP would therefore see all NF↔NF SBI traffic.
- OAI CN5G v2.2.2 (F6) uses direct NF↔NF SBI (no SCP) over HTTP/2 per its fed config.

## Findings

### F1 — Open5GS #4877 REPRODUCED at pre-fix commit (positive control) — R3 orphan UPF sessions / O3 violated
- Upstream state (2026-11-06): issue #4877 OPEN; code fix `9265502032f2` "[UPF] Delete sessions of SMF on heartbeat
  failure" (2026-10-31, "Issues: #4877") is an ancestor of the pinned `e85748e`.
- Pre-fix image `r5g/open5gs:pre4877` = parent `d915126147c0ae77d4ce3c651de2c6aa74a9f559`.
- Recipe (`python3 repro.py i4877 --image r5g/open5gs:pre4877 --k 2 --hold 60`): 2 UEs with active PDU sessions;
  `docker kill -s KILL r5g-smf` (SMF stays down 60 s); poll UPF `fivegs_upffunction_upf_sessionnbr`; then start SMF.
- Result at `d915126`: SMF killed 18:28:14.279 UTC; UPF logs heartbeat give-up 8.5 s later and de-associates, but
  **keeps both sessions for the whole 61.8 s hold** (UPF gauge 2 at every 4 s sample). Sessions are removed only
  when the SMF returns with a new Recovery Time Stamp (restoration path), 62 s after the kill.
  Evidence (`logs/repro_i4877_pre4877-d915126.log.gz`):
  ```
  18:28:22.828 [upf] WARNING: No Heartbeat from SMF [172.22.0.4]:8805 (../src/upf/pfcp-sm.c:343)
  18:28:22.828 [upf] INFO: PFCP de-associated [172.22.0.4]:8805 (../src/upf/pfcp-sm.c:184)
  ... (no session removal for 53 s; UPF session gauge stays 2) ...
  18:29:16.296 [upf] INFO: PFCP associated [172.22.0.4]:8805
  18:29:16.297 [upf] INFO: [Removed] Number of UPF-sessions is now 1 / now 0
  ```
- Same recipe at `e85748e` (post-fix): the UPF removes both sessions at heartbeat give-up
  (`18:22:29.719 No Heartbeat from SMF` → `[Removed] Number of UPF-sessions is now 0` in the same millisecond).
  → R3/O3 holds post-fix; violated pre-fix. Oracle that catches it: R3 (UPF sessions 2 vs SMF unreachable/0);
  a crash-only oracle sees nothing (no NF crashed apart from the injected kill; UPF healthy).

### F2 — Open5GS #4860 (SMF keeps sessions after UPF heartbeat failure): NOT reproducible in 5G at `e85748e`
- Recipe `repro.py i4860`: 2 UEs with sessions; kill UPF, keep down 50 s.
- At `e85748e` the SMF detects UPF loss (`No Heartbeat from UPF`, `No UPF available`, `PFCP de-associated`) and
  releases both sessions (`Session Release [PFCP-Delete-Trigger:5]`), AMF sessions go 2→0 and UERANSIM shows no
  PS-ACTIVE session: cross-NF state is consistent (R holds) within one heartbeat give-up. This matches the
  upstream discussion: the 5G path already released via `reselect_upf()`; #4860's open part is EPC (fixed by
  #4863 `26f9edd`, not testable with UERANSIM).
- Observation (lazy repair): the UEs immediately re-requested a session while no UPF was associated; those
  requests were rejected (`No UPFs are PFCP associated that are suited to RR`) and after the UPF returned the UEs
  stayed without a session until the user re-established one (no network-initiated re-activation). Consistent, but
  service recovery is UE-driven only.

### F3 — Open5GS #4892 mechanism REPRODUCED at pre-fix commit `48c0cc0` (positive control) — R4 black-hole, non-convergent
- Upstream: #4892 OPEN; code fix `fc26daab9b` "smf: Restore only operational sessions after UPF restart"
  (2026-11-04, "Issues #4892"); pre-fix image `r5g/open5gs:48c0cc0` = parent `48c0cc03740f1c36e5d868c94d21774a86bd8512`.
- Recipe (reporter's deterministic variant; `python3 repro.py i4892 --image r5g/open5gs:48c0cc0 --k 2 --hold 30 --after 60`):
  2 UEs with sessions → `docker pause r5g-ue` (UEs cannot answer N1 release) → `docker stop r5g-upf` →
  wait 30 s (> SMF heartbeat give-up, measured 8.1–8.3 s after UPF stop) → `docker start r5g-upf` →
  6 s later `docker unpause r5g-ue` → observe 60 s → UE next use (release + re-establish).
- Reproduced in 2/2 runs (`logs/repro_i4892_pre4892-48c0cc0.log.gz`, `..._run2.log.gz`). Run 2 timeline (UTC):
  ```
  18:33:19.766 docker stop upf
  18:33:28.060 [smf] WARNING: No Heartbeat from UPF ... ; Session Release [PFCP-Delete-Trigger:5] (x2)  (UE frozen: release cannot finish)
  18:33:52.755 docker start upf
  18:33:54.989 [pfcp] ERROR: Remote PFCP restarted ... in Heartbeat REQ
  18:33:54.989 [smf] INFO: UE SUPI[imsi-999700000000001] DNN[internet] IPv4[10.45.0.2] (../src/smf/pfcp-sm.c:492)   <- restoration of a session that is mid-release
  18:33:54.989 [smf] ERROR: Unknown event [SMF_EVT_N4_MESSAGE] (x2)
  18:34:14.720 [smf] ERROR: Service-Request: ACTIVATING FAILED   / [amf] 403:DEACTIVATED:PDU_SESSION_ANCHOR_CHANGE
  18:35:07     UE PDU Session Release Request -> [smf] ERROR: Unknown message [209]; [amf] No SmContextUpdateError [400]
  18:35:09     [upf] ERROR: No PFCP session report response   (SMF discards the restored sessions' reports)
  ```
  State 62.8 s after unfreeze (and still at 81.8 s): SMF 2 sessions, UPF 2 (restored), AMF 2, both UEs PS-ACTIVE on
  their pre-outage IPs, **downlink probe fails for both UEs** → R4 black-hole persists > 3×Δ_core (26 s).
  Symptom differs from the reporter's (they saw stale-IP PDRs next to new ones on eUPF because their UEs had obtained
  new IPs); the root mechanism — restoration re-installing sessions that are mid-release — is the same and is
  exactly what `fc26daab9b` removes (see F4: post-fix logs say "Skip restoration: not operational").

### F4 — CANDIDATE NEW VIOLATION at pinned HEAD `e85748e` (candidate, not yet reported upstream)
**Interrupted network-initiated release leaves zombie PDU sessions in SMF/AMF/UE after a UPF outage (R1/R3/R4/R6, non-convergent).**
- Same recipe as F3 at `e85748e` (post-#4892-fix). `logs/repro_i4892_postfix-e85748e.log.gz`.
- What the fix changes: SMF now logs `[imsi-...:1] Skip restoration: not operational` (18:36:54.341), so the UPF gets
  **0** sessions (no stale PDRs) — the #4892 symptom is gone.
- What remains broken: the two sessions stay in the SMF in the releasing state **forever** (observed ≥ 82.5 s after
  unfreeze; long-tail run below): SMF `sm_sessionnbr`=2, AMF `amf_session`=2, both UEs PS-ACTIVE on 10.45.0.2/.3, UPF 0.
  - UE Service Request → `[amf] Service-Request: ACTIVATING FAILED [403:DEACTIVATED:PDU_SESSION_ANCHOR_CHANGE]`, but the
    session is not released.
  - UE-initiated PDU Session Release → `[smf] ERROR: Unknown message [209] (../src/smf/gsm-sm.c:4033)`,
    `[amf] No SmContextUpdateError [400]`, gNB `Error indication ... protocol/semantic-error`; UE retransmits on T3582.
  - The UE can only open a *new* PSI (got PSI 2 with 10.45.0.4): the old UE IPs 10.45.0.2/.3 stay allocated (R6 leak),
    the old SM contexts stay referenced by the AMF (R1/R2 hold only syntactically: both sides hold a dead session),
    the SMF↔UPF bijection is broken (R3: SMF 2 vs UPF 0) and downlink to the PS-ACTIVE PSI is black-holed (R4).
- Precondition: UE unreachable (frozen) while the SMF runs the UPF-loss release. Without the freeze the release
  completes and R holds (F2), so this is a crash-point/interleaving-dependent bug, not a steady-state one.
- Minimized replay (k=1, one UE, one PDU session): `python3 repro.py i4892 --image r5g/open5gs:e85748e --k 1 --hold 30 --after 300`
  (`logs/repro_i4892_postfix-e85748e-k1-long.log.gz`): UPF restarted 18:40:06.969, UE unfrozen 18:40:13.401; at
  +302 s SMF 1 session, AMF 1, UE PS-ACTIVE 10.45.0.2, UPF 0, DL probe fails; after the UE's release + re-establish
  (+316 s) unchanged (release rejected, old PSI kept). **Non-convergent for > 12×Δ_core (26 s)**; Δ_full (785 s,
  T3512-driven periodic registration) was not waited out, so whether periodic re-registration eventually cleans it
  is untested.
- Minimized steps: (1) UE has 1 PDU session; (2) make the UE unreachable (UERANSIM process frozen); (3) stop UPF;
  (4) wait > SMF heartbeat give-up (~8–10 s; we used 30 s); (5) start UPF; (6) un-freeze UE.
- Same symptom class also present pre-fix (F3: zombie sessions + Unknown message [209]); the #4892 fix removed the
  UPF-side stale PDRs but not the SMF/AMF/UE-side zombie state.

### F5 — Downtime / steady-state fault sweep at `e85748e` (reviewer item: downtime dimension, gNB & NRF faults)
`campaign.py downtime` (`downtime.jsonl/.csv`, logs `logs/D-*.log.gz`): 2 UEs with active sessions, fault at steady
state, NF ∈ {UPF, SMF, AMF, NRF, gNB}, mode SIGKILL, downtime ∈ {0, 10, 30} s (Open5GS N4 heartbeat give-up measured
8.1–8.5 s; Δ_N4 from source 18.5 s), R polled every 3 s for 36 s after restart; verdict at Δ_core = 26 s.
One seed per cell (15 schedules). `D-upf-crash-d30` was re-run because its first run hit a harness false alarm
(liveness wait 10 s < UERANSIM T3580 16 s; superseded record kept in `downtime_superseded.jsonl`).

| NF | downtime 0 s | 10 s | 30 s | crash-only oracle | liveness oracle |
|---|---|---|---|---|---|
| UPF | converged by ≤ 19.8 s (first poll; polling began after SMF re-association at 17.8 s) | converged by ≤ 9.1 s (re-assoc 7.1 s) | converged by ≤ 3.2 s (SMF had released sessions during the outage) | silent | ok (d30 re-run) |
| SMF | **persistent R1-dangling + R4 black-hole** | same | same | silent | detects (UL ping fails) |
| AMF | **persistent R2-orphan-SMF + R5 (AMF lost UE contexts)** | same | same | silent | **silent** (data plane OK) |
| NRF | converged ≤ 2.0 s (no R impact) | ≤ 2.0 s | ≤ 2.0 s | silent | ok |
| gNB | converged 6.9 s | 2.0 s | 2.0 s | silent | ok |

**F5a (candidate R violation at HEAD; may be "expected" because TS 23.527 §6.1 leaves SBI-context restoration
unspecified):** SMF crash-restart (any downtime) — the new SMF incarnation has 0 SM contexts, the UPF drops the old
sessions (new Recovery Time Stamp → restoration path), but the AMF keeps 2 SM-context refs and both UEs stay
PS-ACTIVE; downlink and uplink are black-holed for the whole window (36 s > Δ). No NF notifies AMF/UE (no
recoveryTime-driven cleanup → oracle O6 class). Sample: `D-smf-crash-d0`: AMF sess 2, SMF 0, UPF 0, UEs PS-ACTIVE
10.45.0.2/.3, DL probe fails at every poll. Lazy-repair probe: see `lazy.jsonl` (if present).

**F5b (candidate, same caveat):** AMF crash-restart — AMF loses all UE contexts (registered-subscriber gauge 0)
while UEs remain RM-REGISTERED/CM-CONNECTED and the SMF keeps 2 sessions with 2 UPF sessions (orphans w.r.t. the AMF);
the data plane keeps working, so **both the crash-only and the liveness oracle are silent**; only R (R2/R5) sees it.

**Benign convergence (reviewer item 3: is Δ a valid bound?):** every non-persistent schedule was clean by ≤ 19.8 s
< Δ_core = 26 s. Caveat: in these downtime runs the harness started polling R only after the SMF re-associated with
a restarted UPF (17.8 s for d0, 7.1 s for d10, 0.95 s for d30), so for UPF faults the figure is a "converged-by" upper
bound; the transient window (UPF restarted with 0 sessions until SMF detects the new Recovery Time Stamp and runs
restoration) was not sampled. Fixed afterwards (readiness measured in a background thread; pod-kill runs poll from
t≈2 s). For gNB d0 the transient was observed (violated at the first poll, clean at 6.9 s).
No schedule was violated at Δ and clean later in the window (late convergence = 0), i.e. Δ was not exceeded by
any convergent run. Measured heartbeat give-up 8.1–8.5 s vs source-derived Δ_N4 = 18.5 s (bound holds, ~2× slack).
**Lazy repair:** UPF outage > give-up: SMF releases sessions with "reactivation requested"; the UE re-requests
immediately, is rejected (`PDU Session Establishment Reject [NETWORK_FAILURE]`) while no UPF is associated, and
the session only comes back on a later UE attempt (UE-driven repair).

### F6 — OAI CN5G v2.2.2 (second core; stage 4, separate VM `recover5g-oai`) — single runs, candidates
Source: `oai/FINDINGS-oai.md`, `oai/oai.jsonl`, `oai/oai_faults.csv`, logs `oai/logs/*.log.gz`; setup
`testbed/oai/README-oai.md`. Release images v2.2.2 (2026-10-30), not the paper's pinned OAI commits. Registration,
PDU sessions and UE→UPF ping (GTP-U verified by tcpdump) work; UPF in simple-switch mode; restart-to-ready SMF 1.1 s,
UPF 0.25 s. Integrity order had to be changed to NIA2,NIA1,NIA0 for UERANSIM. One run each (k=2):
- **O-1 SMF crash, immediate restart:** SMF re-associates; UPF deletes nothing (`Associated with CP function
  oai-smf`, no deletion); UPF keeps forwarding for 48 s (> Δ_OAI 40 s) with no SMF context → R3 orphan UPF
  sessions + R1 dangling AMF/UE refs; UE release later fails `SM Context associated with this id 0x1 does not exit!`.
- **O-2 UPF crash, immediate restart:** SMF re-associates but neither restores nor releases; UEs PS-ACTIVE, data
  plane fails in every sample for 47 s → R4 black-hole + R3.
- **O-3 SMF down 45 s:** the UPF sends **no** heartbeat toward the SMF during the outage (only SMF→UPF heartbeat lines
  exist), consistent with `timers.csv` (UPF→SMF HB only if the SMF PFCP Node ID is IPv4; here FQDN `oai-smf`) →
  TS 23.527 §4.4.3.1 cleanup cannot fire; sessions survive outage + re-association.
- Caveat: "SMF restarted" interpretation assumes a new Recovery Time Stamp in the Association Setup (not decoded).

### F7 — CANDIDATE (boundary campaign, `e85748e`; candidate, not yet reported upstream): SMF crash right after the PFCP session is installed during PDU session establishment leaves the AMF with dangling SM-context refs; retries of the same PSI are black-holed
- Schedule `B-pdu-pdu.upf_sess_added-smf-k2-s0` (`boundary.jsonl`, `logs/B-pdu-pdu.upf_sess_added-smf-k2-s0.log.gz`):
  2 registered UEs request PDU sessions (seeded order UE1, UE2; netem 150 ms); trigger = UPF log
  `[Added] Number of UPF-Sessions is now 1` (19:17:30.650) → `docker kill -s KILL r5g-smf` → immediate start.
  Victim's last line: `UE SUPI[imsi-999700000000001] DNN[internet] IPv4[10.45.0.2]` (IP allocated, PFCP sent).
- After restart the SMF has 0 contexts, UPF 0, but the AMF keeps 2 sessions with `smContextRef[1]`, `smContextRef[2]`.
  Each UE retransmission (T3580) of the PDU Session Establishment Request for the same PSI is forwarded by the AMF to
  the stale ref and fails silently at the UE:
  ```
  19:17:41.442 [gmm] UE SUPI[imsi-999700000000001] ... smContextRef[1] smContextResourceURI[http://172.22.0.4:7777/nsmf-pdusession/v1/...
  19:17:42.688 [amf] ERROR: [1:0] Error Indication [state:19] (../src/amf/nsmf-handler.c:1213)
  ... repeated at 19:17:57, 19:18:14, 19:18:50, 19:19:06 for both UEs ...
  UE: PDU Session Establishment procedure failure, no response from the network after 5 attempts
  ```
  UE1 recovered only by using a **new PSI** (PSI 2 at 19:18:28, AMF session count grows to 3: two dead entries
  remain — leak); UE2's next-use establishment for PSI 1 failed again (liveness oracle: FAIL).
- R verdict at Δ and at window end: `R1-dangling` (AMF 2 vs SMF 0); crash-only oracle silent.
- Contrast within the same campaign: SMF crash at `pdu.smf_sess_added` (before IP allocation/PFCP) converged
  at 7.6 s with no violation → the outcome depends on the crash point, as the paper's Theorem 1 boundary model predicts.
- Likely same root cause family as F5a (AMF never learns that SMF contexts were lost; no recoveryTime-driven
  cleanup), observed here at a procedure boundary rather than at steady state.

### F8 — Systematic boundary campaign at `e85748e` (stage 3b) — 27 of 54 planned schedules (65-min budget)
`campaign.py boundary` (`boundary.jsonl/.csv`, `summary.json["boundary"]`, logs `logs/B-*.log.gz`): k = 2 UEs, seed 0,
crash (SIGKILL + immediate start) of AMF / SMF / UPF on the first log line marking a resource boundary of
registration (5 boundaries), PDU establishment (5), release (4), deregistration (4); netem 150 ms on every NF;
schedule order shuffled (seed 1), so the 27 executed schedules are an unbiased subset of the 54 (covering all four
procedures; per NF: UPF 12, AMF 8, SMF 7). Verdict = R violated both at Δ = 26 s and at the end of the 36 s window.

| | count |
|---|---|
| schedules executed / fault fired / harness errors | 27 / 27 / 0 |
| persistent R violations (schedules) | **8** (unique keys (conjuncts, NF, boundary): 8) |
| … of which crash-only oracle detects | **0** |
| … of which liveness (pod-kill) oracle detects | 5 (3 missed) |
| … cleared by the UE's next use (lazy repair) | 6 of 8 |
| schedules to first violation (execution order) | 4 |
| non-persistent schedules: converged-by time median / max | 7.6 s / 37.8 s |
| violated at Δ but clean later (Δ exceeded) | 1 (AMF crash at `pdu.smf_sess_added`, converged at 37.8 s — confounded by gNB-tool restart, see below) |

Per NF:
- **SMF (5/7 schedules violate):** boundaries `pdu.ip_allocated`, `pdu.upf_sess_added` (F7), `rel.smf_sess_removed`,
  `dereg.amf_rx`, `dereg.smf_sess_removed` → persistent **R1-dangling** (AMF keeps SM-context refs the restarted SMF
  does not have). For the release/dereg boundaries the UE's next use cleared it (lazy repair); for the PDU
  boundaries it did not (liveness failure: same-PSI retries black-holed, F7). Crashes at `pdu.smf_sess_added` and
  `dereg.ue_ctx_release` converged (7.6 s, 2.4 s) — crash-point dependence as predicted by Theorem 1.
- **UPF (0/12 violate):** every UPF crash converged (2.4–20.0 s), via the SMF detecting the new Recovery Time Stamp and
  restoring sessions (or the procedure completing/failing cleanly).
- **AMF (3/8 violate persistently: R5 ×2, R2+R3+R4 ×1):** caveat — in **all 8** AMF-target schedules UERANSIM's
  `nr-gnb` aborted when its SCTP association dropped (`terminate called ... sctp::SctpError`), and the harness
  restarted the gNB (`gnb_tool_crash = true`). AMF outcomes are therefore "AMF crash + gNB restart" composites;
  two earlier AMF runs without the watchdog are kept in `boundary_superseded.jsonl` and excluded.
  The R2+R3+R4 case (AMF crash at `rel.upf_sess_removed`): SMF keeps a session whose UPF session is gone while the UE
  still uses it → black-hole; not repaired by next use.

### F9 — Random pod-kill baseline and oracle comparison (stage 3c)
`campaign.py podkill --runs 12` (`podkill.jsonl/.csv`): same workloads (k = 2, procedure ∈ {reg, pdu, rel, dereg},
NF ∈ {AMF, SMF, UPF} chosen at random, crash at a uniform offset of 0–2 s after the procedure starts, netem 150 ms).
On every schedule of all three campaigns we evaluated three oracles on the *same* run:

| campaign (schedules) | R persistent (unique keys) | crash-only oracle | liveness oracle (pod-kill baseline) | R-violations missed by liveness | lazy repair |
|---|---|---|---|---|---|
| downtime (15) | 6 (2) | 0 | 3 | 3 | 0 |
| boundary (27) | 8 (8) | 0 | 5 | 3 | 6 |
| pod-kill (12) | 4 (3) | 0 | 2 | 2 | 4 |

- The crash-only oracle detected **nothing** in 54 fault schedules (no Open5GS NF crashed apart from the injected kills;
  UERANSIM gNB aborts are excluded as tool crashes). The liveness oracle (what a chaos/pod-kill harness checks) missed
  8 of 18 persistent R violations; those are the silent class (orphan SMF contexts after AMF crash, dangling AMF refs
  that a later UE action papers over).
- Pod-kill on these short procedures also hits SMF context loss easily (any SMF kill while sessions exist) — the
  dominant root cause here is coarse (F5a/F7 family), so random timing finds it too; the boundary campaign adds
  crash-point *specific* outcomes (e.g. `pdu.smf_sess_added` converges while `pdu.upf_sess_added` does not).
  With 1 seed and 12–27 schedules per campaign we make **no statistical claim** comparing scheduling strategies.
- Unique keys are (violated-conjunct set, NF, boundary) as in the paper; at the root-cause level the 18 persistent
  violations collapse to **2 classes** (RC1: SMF context loss not propagated to AMF/UE → R1/R4; RC2: AMF context loss
  not propagated to SMF → R2/R5), plus F4 (RC3) found by the targeted downtime+unreachable-UE recipe.

### F10 — Restart time per NF and lazy repair (reviewer items 3, 5)
`measure.py restart --reps 2` → `restart_times.csv` (container `StartedAt` → readiness log line, both VM clock):
NRF 0.07/0.15 s, SCP 0.15/0.13, AUSF 0.12/0.08, UDM 0.12/0.07, UDR 0.15/0.08, PCF 0.07/0.10, NSSF 0.08/0.07,
BSF 0.12/0.12, AMF (own NRF registration) 0.08/0.12, SMF (PFCP re-association) 0.46/0.17, gNB (NG Setup) 0.11/0.10 s;
**UPF 10.29/10.21 s** — the UPF process is up immediately but is usable only after the SMF's no-heartbeat timer notices
the restart and re-associates (in the downtime campaign 17.8 s for an immediate restart, 7.1 s after 10 s downtime).
OAI (F6): SMF 1.1 s, UPF 0.25 s.

`measure.py lazy` → `lazy.jsonl` (crash-restart, wait 30 s, then UE1 releases + re-establishes, UE2 deregisters →
auto re-registers → establishes):
- **SMF:** before: R1-dangling + R4 black-hole (F5a). After the UEs act, both get working sessions (DL probe OK) —
  service is repaired *only by UE action* — but the AMF still holds **3** SM-context entries vs SMF 2: one dead AMF
  entry leaks permanently (R1 persists).
- **AMF:** inconclusive — UERANSIM's gNB aborted on the AMF's SCTP loss (this script has no gNB watchdog).
Across campaigns, 10 of 18 persistent violations were cleared by the next UE action (`lazy_repair` column).

## At a glance (for the reviser)
- REAL testbed: Open5GS `e85748e` (+ pre-fix builds `d915126`, `48c0cc0`) + UERANSIM `4f45e18` (UAC-wait patch),
  11 NFs + MongoDB, 1–4 UEs, arm64 Colima VM; OAI CN5G v2.2.2 on a second VM.
- **Reproduced (positive controls, with logs):** #4877 at `d915126` (F1); #4892 mechanism at `48c0cc0`, 2/2 runs (F3).
  Fixes confirmed at `e85748e`. #4860 not reproducible on the 5G path (F2).
- **Candidate new violations at pinned HEAD (not reported upstream):** F4 (zombie sessions after interrupted
  release + UPF outage; minimized k=1 replay, non-convergent > 300 s), F7 (SMF crash after PFCP establishment →
  AMF dangling refs, same-PSI retries black-holed), F5a/F5b (SMF/AMF crash-restart leaves cross-NF state
  inconsistent indefinitely; arguably expected given TS 23.527 §6.1, but a silent R violation); OAI O-1/O-2/O-3 (F6, single runs).
- **Numbers:** 54 fault schedules (15 downtime + 27 boundary + 12 pod-kill), 18 persistent R violations,
  crash-only oracle 0/18, liveness oracle 10/18; non-persistent schedules converged by ≤ 19.8 s (downtime) /
  ≤ 37.8 s (boundary/pod-kill; the > Δ cases involve UE re-registration after an AMF crash + gNB-tool restart);
  measured N4 heartbeat give-up 8.1–8.5 s vs Δ_N4 = 18.5 s from source; schedule wall time median 80–134 s.
- **Not done / blocked:** free5GC (gtp5g kernel module unavailable in the Colima kernel); wire taps/shadow model,
  freezer gating, CRIU, DDMin, Kairos/CoreCrisis baselines; multiple seeds; 27/54 boundary schedules; Δ_full waits.

---

# Campaign 2 (2026-11-06, ~4 h wall time, 04:30–08:15 local) — round-2 review items

All data in `campaign2/` (JSONL + CSV + `logs/*.log.gz` + `pcap/*.pcap.gz`, decoded `*.ids.json` next to each pcap).
Harness changes are listed in `../../testbed/README.md` ("Campaign 2 additions"). Nothing here is projected.
Every Open5GS run is at pinned `e85748e` unless an image tag says otherwise. Nothing was reported upstream.

## C2.0 Methods (what changed vs. campaign 1)
- **Identity-level oracle (R1/R3 review "count-level" critique).** Each poll now also reads the AMF's `/ue-info`
  (SUPI, GUTI, NGAP ids, PSIs) and the SMF's `/pdu-info` (SUPI, PSI, UE IPv4, N3 TEIDs, state); both are JSON dumpers
  on the metrics port at `e85748e` (`src/amf/ue-info.c`, `src/smf/pdu-info.c`). `check_R_id` compares *bindings*
  (SUPI, PSI) → IP across AMF, SMF and UERANSIM: `R1id-dangling-AMF/UE`, `R2id-orphan-SMF-vs-AMF/UE`,
  `R6id-ip-mismatch`, `R6id-leak-ip`, `Rg-id-alias-ip` (one IP bound to two (SUPI,PSI)), `R5id-*`.
- **Wire capture per run.** `tcpdump` on the instance bridge from *before* the per-run NF reset (so every HTTP/2
  connection, incl. AMF↔SCP↔SMF h2c, is decodable). `c2/pcap_ids.py` (tshark 4.x in `r5g/tshark:1`) extracts
  smContextRef issuance (201 `Location`) per SMF incarnation and every later `/sm-contexts/{ref}/…` request with its
  status, PFCP SEIDs / UE IPs / causes / Recovery Time Stamps, NGAP + **null-ciphered NAS** (NEA0 is negotiated, so 5GMM
  /5GSM payloads decode), and GTP-U Error Indications. UPF-side session identities and smContextRef bindings are
  checked offline from the pcap (no UPF dumper exists).
- **Per-conjunct verdicts.** Window 72 s after restart (≥ 2 × 33.8 s); snapshots at 5.5/11 (SMF-restart R3 Δ_j/2Δ_j),
  26/36 (campaign-1 Δ_core/window, for comparison), 33.8/67.6 (UPF-restart Δ_j/2Δ_j; also used as the pair for NU/UE
  classes). `analyze_c2.py` classifies each conjunct ok/transient/persistent/late with its class (num/NU/UE).
  **Lazy repair v2** = violated at 67.6 s AND clean after next use AND every next-use action succeeded.
- **Throughput.** `inst.py` runs up to 8 independent Open5GS stacks side by side in the `recover5g` VM (8 vCPU; load
  average 3–4.5 during the campaign). Timing-sensitive conclusions (A4′, phase) were checked against the pcap/logs of
  each run rather than assumed from the trigger.
- **Superseded records** (kept, excluded): `a4/a4audit_superseded.jsonl` (first A4 attempt: AMF netem applied before the
  pre-state made registration fail / scrapes time out), `*_errors.jsonl` (a `None`-SUPI key bug in the identity readout
  during registration-boundary AMF crashes; fixed, schedules re-run).

## C2.1 Duplicate analysis of the candidates (R3 N1)
Upstream facts (read-only `gh api`, 2026-11-06; details and permalinks in `campaign2/source_facts.md` §1–2):
#4963 (= `fc26daab9b`, merged 2026-11-04) **is in `e85748e`** (compare: ahead 3 / behind 0), so `r5g/open5gs:48c0cc0`
= "without #4963". #4485, #4486, #4895, #4540, #4528, #4555 are **open/unmerged**. Patched images were built from
the PR diffs on top of `e85748e`: `e85748e-pr4485` (clean apply), `e85748e-pr4540` (one header hunk re-anchored),
`e85748e-pr4528amf` (AMF half only; its SMF half is already superseded upstream by `d322bedebe`, which is in e85748e),
`e85748e-pr4895` (fuzz 2). #4486 (5 hunks fail) and #4555 (1 hunk fails) were not built.

| Candidate | Runs (this campaign) | Result | Verdict |
|---|---|---|---|
| **F7** (SMF crash at `pdu.upf_sess_added`, netem 150 ms) | e85748e 5/5 seeds; **e85748e-pr4485 5/5 seeds** (`campaign2/F7_c2.csv`, `dup/`) | e85748e: 5/5 persistent `R1id-dangling-AMF` for both UEs at 33.8 and 67.6 s, next use `pdu-FAIL` for both UEs in 5/5. **#4485: 0/5** — R clean, next use `ul-ok` 5/5 | **Duplicate of PR #4485** (the PR's patch removes it in 5/5) |
| F7 without netem (m5) | e85748e 2, pr4485 2 | the kill (≈100 ms) lands after the procedure completes: UE keeps a dead PSI 1 while the restarted SMF hands the *same* IP to the other UE (`Rg-id-alias-ip` 10.45.0.2 bound to both UEs) — 4/4, also with #4485 | a different effective crash point (F5a family), not F7; F7 needs the widened window |
| **F5a** R1 part (SMF crash at steady state) | e85748e 5/5, pr4485 3/3 (`f5a/`) | persistent R1 (NU) + R4 in 8/8 until a UE acts; #4485 acts only on a 404 reply, so it cannot fire while UEs are silent | **Overlaps #4485** (same root cause, repaired by the PR only on next use; see C2.4 lazy probe: AMF entry fixed, UE-side stale PSI + IP alias remain) |
| **F4** (UE frozen + UPF outage > give-up) | e85748e 5/5, pr4540 2/2, pr4895 2/2, pr4528amf 2/2 (`f4/repro.jsonl`); without #4963 = campaign-1 F3 at 48c0cc0 2/2 | all 11 runs at e85748e(+PR) end with SMF 2 / AMF 2 / UPF 0 sessions, both UEs PS-ACTIVE on 10.45.0.2/.3, DL probe fails; every run logs `Skip restoration: not operational` ×2, `Service-Request: ACTIVATING FAILED` ×4 and **`[smf] ERROR: Unknown message [209] (gsm-sm.c:4033)` ×4** | **Overlaps the #4892/#4895 thread (same recipe), #4540 and #4528, but none of #4963/#4895/#4540/#4528(AMF half) removes it** → the SMF-FSM part (no handling of a UE-initiated release, 5GSM 209, in the releasing state) is **plausibly new** |
| **OAI O-1** (SMF crash, immediate restart) | v2.2.2 3/3; pinned SMF 9d8e866 + UPF 5a0a6d4 2/2; v2.2.2 SMF + UPF 5a0a6d4 2/2; **UPF 5a0a6d4 + PR #43: 0/3** (`campaign2/oai/oai_c2.csv`) | without #43 the UPF accepts the new association (Node ID FQDN `oai-smf`, new RTS, cause 1) and deletes nothing; with #43: `PFCP association with oai-smf already exists, deleting its PFCP sessions` / `Deleting 2 PFCP sessions of a replaced association`; the AMF/UE-side dangling release (`SM Context associated with this id 0x1 does not exit!`) remains in all runs | **Duplicate of OAI UPF #41** (UPF part; PR #43 fixes it); the AMF/UE dangling part is the OAI analog of RC1 |

F7 evidence (pcap + AMF log): at e85748e each T3580 retransmission is an UL NAS Transport with **request type 1
("initial request"), PSI 1**, carrying a PDU Session Establishment Request (0xc1); the AMF sends
`POST /sm-contexts/{1,2}/modify` (state 19, duplicated-PSI release to the *old* ref), gets **404** (20 such 404s per run
in `F7-e85748e-s0`) and answers the gNB with NGAP Error Indication (`[amf] ERROR: [1:0] Error Indication [state:19]
(nsmf-handler.c:1213)`); no DL NAS reaches the UE. With #4485: `[amf] WARNING: [imsi-…1:1] SMF 404 on
sm-contexts/1/modify [state:19] - releasing stranded AMF sess (nsmf-handler.c:1156)`, then a fresh create (refs 1, 2
re-issued by the restarted SMF) and 204s. Whether forwarding to the stale ref violates TS 24.501 §5.4.5.2.5 was **not
verified against the spec text**.

F4 NAS evidence (answers R1 Q2; `f4/pcap/repro_i4892_F4-e85748e-r1.pcap.gz`): while the UEs are frozen the SMF sends
PDU Session Release Command (0xd3, 5GSM cause #39 "reactivation requested") — lost. After unfreezing, the UE's
Service Request is answered by **Service Accept with PDU session status PSI(1) = active and PDU session reactivation
result PSI(1) = 0 (success)**, although the SMF answered the AMF with 403 `DEACTIVATED`. So the UE's PS-ACTIVE state is
what the core signals, not a UERANSIM artefact. The UE's later PDU Session Release Request (0xd1, carrying 5GSM cause #36) is answered only by
NGAP Error Indications; the SMF logs `Unknown message [209]`. No `SmContextStatusNotify` (AMF `sm-context-status`
callback) appears on the wire in the #4540 runs or at e85748e (pcap path list), i.e. #4540's notify path is not reached.

## C2.2 NEW candidate F11 — Open5GS smContextRef reuse after an SMF restart: a stale AMF reference acts on *another UE's* session (OAI #33 analog)
Source (pinned, `campaign2/source_facts.md` §3): smContextRef = slot index of `smf_sess_pool` (`src/smf/context.c:1763`),
the FIFO pool is re-initialised at start, and `smf_sess_find_by_sm_context_ref()` resolves `/sm-contexts/{ref}/…` by
index only (`context.c:2310`; no SUPI/PSI check in `smf-sm.c:551-611`, `nsmf-handler.c:707/725`).
Recipe (`testbed/c2/alias.py`, k=2, no netem): UE1/UE2 with PSI 1 (refs 1, 2) → SMF SIGKILL + immediate restart →
UE2 establishes PSI 2 (restarted SMF issues ref **1** and IP **10.45.0.2**, UE1's old IP) → UE1 deregisters (`dereg`)
or releases PSI 1 (`rel`). `campaign2/alias/alias.jsonl`, `alias_eval.csv` (pcap-derived).

| variant / image | runs | UE1's request hits ref 1 | UE2's PFCP session deleted | UE2 still PS-ACTIVE at UE |
|---|---|---|---|---|
| dereg / e85748e | 5 | 5/5 `POST sm-contexts/1/release → 204` | 5/5 | 5/5 |
| rel / e85748e | 3 | 3/3 `POST sm-contexts/1/modify → 200, 204` (later 400) | 3/3 (SMF keeps UE2 PSI 2 as `inactive`) | 3/3 |
| dereg / e85748e-pr4485 | 3 | 3/3 → 204 | 3/3 | 3/3 |
| rel / e85748e-pr4485 | 2 | 2/2 | 2/2 | 2/2 |

**13/13 reproduced.** Evidence (`ALIAS-dereg-e85748e-r1`): `23:26:45.316 [amf] INFO: [imsi-999700000000001:1] Release SM
context [204]` and in the same millisecond `[smf] INFO: Removed Session: UE IMSI:[imsi-999700000000002]
DNN:[internet:2] IPv4:[10.45.0.2]`; pcap: AMF→SCP→SMF `POST /nsmf-pdusession/v1/sm-contexts/1/release` (204) followed by
PFCP Session Deletion of UE2's SEID. `rel` variant: the SMF treats UE1's 5GSM release (PSI 1) as a release of UE2's PSI 2
(PFCP deletion), the returned release command reaches UE1 (`PSI mismatch in DL NAS Transport, ignoring`), UE1's T3582
retransmission hits `Unknown message [209]`. Identity oracle: `Rg-id-alias-ip 10.45.0.2 bound to (smf, UE2, 2), (ue,
UE1, 1), (ue, UE2, 2)` already before the trigger. **PR #4485 does not help** (the SMF answers 204, not 404).
Tracker search (read-only `gh search issues/prs` in open5gs/open5gs for "smContextRef", "SMF restart", "stale
smContextRef", "sm context ref reuse", "session index reuse"): no matching issue or PR. **Verdict: plausibly new for
Open5GS** (same class as the known OAI SMF #33). Caveat: DL/UL probes for UE2's PSI 2 are unreliable here because both
UEs' TUN devices share 10.45.0.2 in the single UE container; the verdict rests on the SMF log, the SMF dumper and PFCP.

## C2.3 A4′ audit around `ReleaseSMContext` (R2 round-1 Q1 / round-2 item 6)
`testbed/c2/a4audit.py`, k=1, UE deregistration, SMF SIGKILL + immediate restart triggered on the AMF's
`Deregistration request` log line; delays applied only after the pre-state (`netem_after_pre`) and removed 2 s after
the restart. 3 positions × 3 replays = **9 runs** (`campaign2/a4/a4audit.jsonl`, `a4audit_c2.csv`, path table
`a4/a4_paths.csv` derived from each pcap):

| position | how | first SCP→SMF attempt vs. restarted SMF's PFCP association | AMF-side outcome (pcap) | PFCP deletion on wire | R (count+id) | t_conv | next use |
|---|---|---|---|---|---|---|---|
| pre (request reaches the *restarted* SMF) | AMF egress +2000 ms | +1.64 / +1.64 / +1.73 s; first attempt on the pooled stale connection gets no response, the SCP retries immediately | **404** ×3 | 0 | clean at 33.8 and 67.6 s, 3/3 | 7.4, 7.4, 17.4 s | ok 3/3 |
| flight (request at the SCP / on the wire while the SMF is dead) | AMF+SCP +150 ms, kill +0.05 s | −0.28 / −0.09 / +0.002 s (no response), SCP retry ≈ +0.9–1.1 s | **404** ×3 | 0 | clean, 3/3 | 7.4, 7.4, 17.6 s | ok 3/3 |
| recv (old SMF has the request; its PFCP deletion/204 still queued) | AMF+SCP +150, SMF +600 ms, kill +0.45 s | −0.60 / −0.42 / −0.39 s (delivered to the old SMF, never answered), SCP retry ≈ +0.5–0.7 s | **404** ×3 | 0 (queued deletion lost with the process) | clean, 3/3 | 7.4, 17.6, 7.4 s | ok 3/3 |

Result: in all 9 runs the AMF follows the **same code path** (its release gets a 404 from the restarted SMF, because
the **SCP retries** a forward that failed on the dead connection) and R converges (SMF, UPF and AMF counts and identities
agree from 7–18 s on). So for this triple of crash points the three positions are α-equivalent at the AMF on Open5GS
**with SCP routing**; with direct (non-SCP) SBI the "flight"/"recv" positions would surface a transport error at the
AMF instead — not tested. Positions are verified by pcap timing only (the SMF's application-level receipt in "recv" is
inferred from delivery 0.4–0.6 s before the kill, not observed).

## C2.4 Lazy repair with a success requirement (R1 N1/N2) and the "3-vs-2" AMF entry
`testbed/c2/lazy_c2.py` (= campaign-1 `measure.py lazy`, SMF crash at steady state, k=2, +30 s; then UE1 releases PSI 1
and re-establishes, UE2 deregisters → re-registers → establishes), identity-level, pcap per run
(`campaign2/lazy/lazy_c2.jsonl`).
- **e85748e, 5/5 identical:** every UE action "succeeds" (UE1 gets PSI 2, UE2 re-registers and gets PSI 1), but at the
  end the AMF still holds **(UE1, PSI 1)** — the AMF forwarded UE1's release to the stale ref, got 404 and kept the
  entry — UE1 still shows PSI 1 PS-ACTIVE, and the restarted SMF gave UE1's PSI 2 the *same* IP 10.45.0.2
  (`R1id-dangling-AMF`, `R1id-dangling-UE`, `Rg-id-alias-ip 10.45.0.2 bound to (smf,UE1,2),(ue,UE1,1),(ue,UE1,2)`).
  UE2's path (deregistration) is repaired cleanly. **Lazy repair v2 = 0/5.** The campaign-1 "AMF 3 vs SMF 2" leak is
  therefore deterministic for the release path (5/5) and absent for the deregistration path.
- **e85748e-pr4485, 3/3:** the AMF entry is now cleaned (404 → stranded sess released) but UE1 keeps PSI 1 PS-ACTIVE
  with the IP that the SMF re-bound to PSI 2 (`R1id-dangling-UE`, `Rg-id-alias-ip`). Lazy repair v2 = 0/3. Whether a
  conformant UE would drop PSI 1 locally depends on signalling the AMF does not send here (no 5GSM reply reaches the UE);
  UE-side behaviour is UERANSIM's.
- Release-boundary and PDU-boundary crash points are covered by the boundary campaign (C2.10) with the same v2 rule
  (`lazy_repair_v2` column of `campaign2/boundary_c2.csv`).

## C2.5 Per-conjunct verdicts, window ≥ 2Δ_j, long horizon (R1 N4)
- Every v2 run observes 72 s after the restart and records per-conjunct verdicts at (Δ_j, 2Δ_j) — numeric classes:
  UPF restart 33.8/67.6 s, SMF-restart R3 5.5/11 s; NU/UE classes are judged at 33.8/67.6 s and after the next use.
  Columns `conjunct_verdicts`, `persistent_numeric|NU|UE` in every `campaign2/*_c2.csv`.
- **Long horizon, F4** (`f4/repro.jsonl`, tag `F4-e85748e-k1-long1600`, k=1): after unfreezing, 494 samples over
  **1,600.7 s** show a single state throughout — SMF 1, AMF 1, UPF 0 sessions, UE PS-ACTIVE 10.45.0.2, DL probe failing —
  and the next use (release + establish) leaves it unchanged (`R3-missing-UPF`, `R4-blackhole` at 1,615 s).
  **Periodic registration was not exercised:** the AMF log shows no Registration Request after the initial one (only one
  Service Request at +27 s, answered by `ACTIVATING FAILED [403]`), because UERANSIM's gNB never releases an idle RRC
  connection, so the UE stays CM-CONNECTED and T3512 (540 s in `amf.yaml`) never runs. So "time alone" does not repair
  F4 for ≥ 1,600 s (> 1,560 s); whether T3512-driven re-registration would is still untested.
- **The 3 runs re-violated at 36 s in campaign 1** (AMF crash at `pdu.amf_sess_added`, `pdu.ip_allocated`, `P-4`): re-run
  with the non-crashing gNB they are violated (`R5id-amf-lost-ue`) at 33.8 **and** 67.6 s (persistent, UE class); re-run
  with the original (aborting) gNB they are clean at 67.6 s, i.e. they converge late via the gNB-tool restart. Their
  outcome is therefore test-tool dependent (C2.6).

## C2.6 gNB confound (R1 N3): patched UERANSIM gNB, the 11 AMF schedules, and F5b after re-registration
- **Patch** (`testbed/docker/ueransim/gnb-sctp-survive.patch`, image `r5g/ueransim:4f45e18-p2`): the SCTP receiver
  thread no longer lets a socket error escape (it used to terminate the gNB), `receiveConnectionClose` no longer leaves a
  dangling client entry (use-after-free on the next send), send errors are caught, and on association loss the NGAP task
  keeps the AMF context, releases every UE context of that AMF locally (RRC Release → UE CM-IDLE, GTP context removed)
  and retries SCTP + NG Setup every 2 s. Check: AMF SIGKILL+restart → `r5g: NG association lost; released 1 UE
  context(s) locally` → `NG Setup procedure is successful` 2.0 s later, gNB process alive (instance 7 test).
  With it the UE follows the real-gNB path: idle → Service Request → `Service Reject [UE_IDENTITY_CANNOT_BE_DERIVED_
  FROM_NETWORK]` (#9) → initial registration (`AMFp2-B-reg-reg.complete`, UE log 23:53:50).
- **The 11 campaign-1 AMF schedules re-run with p2** (`campaign2/amf/amf_rerun_p2.jsonl`, `amf_rerun_c2.csv`;
  `gnb_tool_crash` = False in 11/11):

| schedule | campaign 1 (p1, watchdog) viol@26 / @36 | campaign 2 (p2) identity labels @33.8 = @67.6 | next use | after next use |
|---|---|---|---|---|
| B pdu.smf_sess_added | R5 / – | clean | ok/ok | clean |
| B reg.udm_done | – / – | clean | ok/ok | clean |
| B pdu.amf_sess_added (re-violated at 36 s in c1) | – / R5 | R5id (UE2) persistent | ok / pdu-FAIL | R5id |
| B reg.amf_ue_added | – / – | clean | ok/ok | clean |
| B rel.amf_sess_removed | R5 / R5 | R5id persistent | FAIL/FAIL | R2id-orphan-SMF-vs-UE |
| B pdu.ip_allocated (re-violated at 36 s in c1) | – / R5 | R5id persistent | ok / pdu-FAIL | R5id |
| B reg.complete | R5 / R5 | R5id persistent | FAIL/FAIL | R2id-orphan-SMF-vs-UE |
| B rel.upf_sess_removed | R2 R3 R4 / same | R2id-orphan-SMF-vs-AMF + R5id persistent (count: R2 R3 R4 R5) | re-register ok/ok | **R2id orphan ×2 + R6id-leak-ip ×2** |
| P-4 (re-violated at 36 s in c1) | – / R5 | R5id persistent | FAIL / ok | R5id |
| P-10 | R2 R3 R5 / same | R2id ×2, R5id, R6id-leak-ip persistent | FAIL/FAIL | R2id-orphan-SMF-vs-UE |
| P-11 | R5 / – | clean | ok/ok | clean |

  Reading: the three runs that were clean at 26 s and violated at 36 s in campaign 1 are **persistent through 67.6 s**
  with a gNB that does not crash (but converge with the aborting gNB — see the control below); R5 (AMF lost a UE that
  thinks it is registered) is the UE class — it repairs only when the UE next signals (Service Reject #9 → re-registration,
  observed), so it stays a classification, not a bug. What survives re-registration is the SMF/UPF side (next bullet).
  **Control with the original gNB** (`amf/amf_rerun_p1.jsonl`, same 11 specs, v2 harness): the gNB aborted in
  **11/11** (watchdog restart, as in campaign 1). Persistent at 67.6 s under *both* gNBs: `rel.amf_sess_removed` (R5),
  `reg.complete` (R5), `rel.upf_sess_removed` (R2 R3 R4; orphan SMF session + leaked IP after next use) and `P-10`
  (R2 R3 R5 R6). **gNB-dependent: the three campaign-1 "36 s" runs** (`pdu.amf_sess_added`, `pdu.ip_allocated`,
  `P-4`) are clean at 67.6 s with the restarting gNB (its restart re-attaches the UEs; late convergence after 36 s) but
  persistent (R5, UE class) with the surviving gNB, because the idle UE does not signal until it has traffic. So 3/11
  AMF outcomes are tool-dependent; 4/11 persist regardless of the gNB, and 4/11 converge under both.
- **F5b follow-up = candidate F12** (`testbed/c2/f5b.py`, `campaign2/amf/f5b.jsonl`, 5 runs, p2 gNB): 2 UEs with
  PSI 1 (10.45.0.2/.3) → AMF SIGKILL + restart → gNB re-does NG Setup → UEs power-cycled (initial registration, 0.0–0.4 s)
  → new PSI 1 (10.45.0.4/.5). **5/5:** the SMF logs `OLD Session Will Release [SUPI:imsi-…,PDU Session identity:1]
  (context.c:1845)` and removes the old session *locally* (`Removed Session … IPv4:[10.45.0.2]`), but the pcap shows
  **no PFCP Session Deletion** (4 establishments, 0 deletions per run) → at +72 s the UPF holds **4 sessions vs SMF 2**
  (`R3-orphan-UPF`, `R6-leak-UPF-ip` for 10.45.0.2/.3). Source: `smf_sess_add_by_sm_context()` calls `smf_sess_remove()`
  for an existing (SUPI, PSI) without a PFCP deletion (`src/smf/context.c:1843-1849` at e85748e). The SMF-side IPs
  return to the FIFO pool tail, so a collision with the stale UPF PDRs needs a pool wrap (not tested). Tracker search
  ("OLD Session Will Release", "PFCP session not deleted re-registration"): no match; related class: PR #4528 / issue
  #4427 (leaked sessions / IP-pool addresses). **Verdict: plausibly new** (leak survives UE re-registration; this is the
  "real leak" R1 asked about). In the boundary campaign, `amf dereg.amf_rx` (3/3 seeds) shows the same mechanism
  (`OLD Session Will Release` without PFCP deletion; `R3-orphan-UPF` + `R6-leak-UPF-ip` after the UEs re-register;
  0 PFCP deletions in the s0 pcap). Orphan *SMF* sessions with leaked IPs also persist after next use in the
  `B rel.upf_sess_removed` and `P-10` AMF re-runs (both gNBs).

## C2.7 Downtime classes and heartbeat phase (R2 N2)
Source (pinned; `campaign2/source_facts.md` §5): heartbeat period 11 s, re-armed **only** by a Heartbeat Response
(`lib/pfcp/handler.c:86-87`); a request is retransmitted at T1 = 2.5 s, 3 tries → give-up 7.5 s after the first
unanswered request, so **G(φ) = φ + 7.5 s ∈ (7.5, 18.5]** with φ = time from the kill to the next SMF heartbeat request.
A restarted UPF has no PFCP node for the SMF and drops its heartbeats (`src/upf/pfcp-path.c:131-153`, "Cannot find
PFCP-Node"); only the SMF initiates association (11 s retry, 2.5 s retransmissions). **Why campaign-1 phases clustered**:
the harness reached the fault a near-constant 20.7–39.4 s after the (re)association, and the period is deterministic
(φ = 0.93/0.97/1.25/4.56/1.37 s in five campaign-1 runs, matching the logs within 0.05–0.32 s).

Runs (`testbed/c2/phase.py`, `campaign2/phase/phase.jsonl`, `phase/phase_eval.csv`, `phase_c2.csv`): UPF SIGKILL at
steady state (k=2) after a seeded **uniform 0–11 s offset**, downtime d ∈ {0 (7 runs), 3 (6), 6 (10), 9 (3), 12 (3)} =
**29 runs** (three seeds of offsets; instances 6 and 1). φ is recovered from the SMF log (G − 7.5 − t_kill).
- φ now spans **0.08–9.94 s** (no clustering); the deterministic-period prediction `11 − ((t_kill − t_assoc) mod 11)`
  matches the measured φ within 0.34 s (median 0.22 s) in 29/29 runs.
- **Detection path is phase- and downtime-independent: give-up in 29/29** (`No Heartbeat from UPF` → sessions released
  with reactivation requested → re-association → the UPF's new RTS in its first Heartbeat → `Skip restoration: not
  operational`). No run detected the restart by RTS before give-up.
- **Effective-outage classes** (defined on d_eff, not d):
  - **A, d < G(φ)** (UPF back before give-up): d_eff = G(φ) ∈ (7.5, 18.5] s; UPF usable at **T_b = G − d** (measured
    1.5–15.3 s; e.g. d=3: 9.5–13.1 s). All d = 0, 3, 6 runs (23/23) are class A whatever φ — the "middle" downtimes behave
    exactly like d = 0.
  - **B, d > G(φ)** (UPF back after give-up): sessions already released during the outage (0 restorations skipped),
    T_b = wait for the next Association Setup (re)transmission, **0.2 and 1.1 s** measured (d=12 φ=4.57; d=9 φ=0.19).
  - For **7.5 < d < 18.5 s the class depends on φ** (d=9: 1 B + 2 A; d=12: 1 B + 2 A). Outside that band the class is
    phase-free (d ≤ 7.5 → A, d ≥ 18.5 → B). So the Open5GS UPF restart has phase-free classes only outside
    (7.5, 18.5) s; inside it the phase is a schedule choice.
- R: 27/29 clean at 33.8 and 67.6 s (convergence 2.0–19.5 s, inside Δ_j = 33.8 s). The 2 persistent runs
  (`PH-upf-d6-r3`, `PH-upf-d0-r6`: one UE PS-ACTIVE on 10.45.0.5 with matching SMF/UPF counts, DL and UL failing through
  67.6 s) are a **UERANSIM artefact**: after give-up both UEs re-request PSI 1 at once and one `nr-ue` process logs
  `TUN allocation failure [ioctl(TUNSETIFF) Device or resource busy]` (two UE processes racing for `uesimtunN` in the
  shared UE container). The same line explains the only other count-preserving black hole
  (`B2-pdu-pdu.n2_modify-upf-k2-s0`); these 3 runs carry `ue_tun_alloc_failure = True` in the CSVs and are excluded
  from the candidate counts. (The SMF lines `OLD Session Will Release` / `Session has already been removed` appear in all
  29 runs and are benign here.)

## C2.8 Allocator facts from pinned source (R2 N3) and OAI SMF #33
From `campaign2/source_facts.md` §3–4 (permalinks there):
- Open5GS `ogs_pool` (`lib/core/ogs-pool.h`): alloc takes `free[head]`, free puts at `free[tail]` → a **circular FIFO free
  queue**, initialised in array order and re-initialised at every process start.
  - **smContextRef / pduSessionRef** = `smf_sess_pool` slot index → after an SMF restart the first new session gets
    ref `1` again; lookup by index only → enables F11 (C2.2).
  - **UE IPv4**: subnet pool in address order, FIFO free queue (not first-fit) → a restarted SMF hands out 10.45.0.2
    again (observed in F11, lazy, F7-no-netem: `Rg-id-alias-ip`).
  - **SMF/UPF N4 SEIDs, UPF F-TEIDs, M-TMSI**: FIFO over a random permutation (`ogs_pool_random_id_generate`, fresh
    per process). **AMF-UE-NGAP-ID**: slot index, restarts at 1.
- OAI SMF at pinned `9d8e866`: smContextRef from `uint_generator` (`++uid`, reset to 0 at start, refs never freed) →
  **reset-counter class**, first ref after restart = 1. OAI SMF #33 is open; its fix PR #34 is unmerged (not in
  9d8e866 nor v2.2.2).
- **OAI #33 reproduced** (fork run in VM `recover5g-oai`, `campaign2/oai/`): at the pinned SMF `9d8e866` + UPF
  `5a0a6d4` **3/3**, at v2.2.2 **3/3**, UE-initiated-release variant 1/1. Evidence (`i33-pinned-r1`): the restarted
  SMF answers UE2's new PSI 2 with `201 …/sm-contexts/1` (22:57:48.091); UE1 deregisters and the AMF sends
  `…/sm-contexts/1/release` with its stale ref (22:57:53.690); the SMF logs `smf_ref 1, method release` and sends PFCP
  SessDelReq SEID 0x1 → **UE2's PDU session 2 is released**; UE2 still shows it active, traffic fails. In 7/7 runs UE2's
  new session also got 12.1.1.130, which UE1 still held (IP alias).
- Further OAI results (all with pcaps): O-2 (UPF restart) 3/3 — SMF neither restores nor releases, DL dead 84 s; new
  O-2 sub-finding 3/3 (plausibly new, GitHub searched, OAI GitLab not searched): the restarted UPF hands UP-SEID 0x1 to
  UE1's new session and UE1's retransmitted release of its old PSI deletes that new session. O-3 (SMF down 45 s) 3/3:
  19 SMF→UPF heartbeats, none UPF→SMF, new RTS after restart, nothing deleted. Side observation (not searched upstream):
  the OAI SMF stamps each heartbeat with its send time as Recovery Time Stamp (advances 10 s per beat,
  `smf_n4.cpp#L736-742` at 9d8e866). O-2/O-3 ran on v2.2.2 images only.

## C2.9 free5GC (second core, item 9) — n = 1 per fault
- gtp5g: kernel headers `linux-headers-6.8.0-117-generic` installed in the `recover5g` VM (apt source temporarily switched
  to the nchc ports mirror, then restored; backup `/etc/apt/ubuntu.sources.r5g-backup`), **gtp5g v0.9.14 (`3b9166f`) built and loaded**
  (`campaign2/free5gc/gtp5g_build.log`; `lsmod: gtp5g 147456`).
- free5GC **v4.0.1 release images** (arm64 manifests on Docker Hub; *not* the paper's pinned free5GC commits) with the
  free5gc-compose v4.0.1 configs (`testbed/free5gc/`, containers `f5g-*`, subnet 10.100.200.0/24), mongo 7.0, our
  UERANSIM 4f45e18 image; subscribers via the webui API. Registration, PDU session (10.60.0.1) and UE→N6 ping work.
- `free5gc/run_f5g.py` (`campaign2/free5gc/free5gc.jsonl`, logs, pcaps), 1 UE, SIGKILL + immediate restart:
  - **SMF restart:** UE keeps PSI 1; UL ping OK through +7.1 s, failing from +10.5 s to the end of the 72 s window. The UPF sends a
    Session Report, the new SMF answers `PFCP Session SEID[1] not found`, the UPF logs `rsp SEID is 0; no this session
    on remote; delete it on local` → UPF session gone while AMF and UE keep the session (R1 dangling + R4). The UE's
    release → AMF `Update SMContext error [pduSessionID: 1], Error[404, Not Found]`; UE stays PS-ACTIVE, UL still fails
    → **RC1 (F5a class) replicated on free5GC**.
  - **UPF restart:** no SMF reaction (the shipped smfcfg enables no PFCP heartbeat), UL fails from the first sample
    for 72 s (R4/R3); UE's release → UPF `handleSessionDeletionRequest: sess not found (lSeid:0x1)`, AMF gets 500;
    re-establishment afterwards failed (UE ended with no session).
  - Artefact: the UE config requests a second PSI on S-NSSAI 1/112233, which the subscriber lacks → repeated `403`
    CreateSmContext rejects in every run (unrelated to the fault).

## C2.10 Replication and the full boundary campaign (R1 N6, item 5)
**Per-candidate reproduction** (`campaign2/replication_c2.csv`, computed from the raw records by `testbed/c2/replication.py`):

| candidate | condition | reproduced |
|---|---|---|
| F4 | e85748e (k=2) / +#4540 / +#4895 / +#4528-AMF / k=1 1,600 s | 5/5 / 2/2 / 2/2 / 2/2 / 1/1 |
| F7 | e85748e netem 150 / +#4485 | 5/5 / **0/5** |
| F5a | e85748e / +#4485 | 5/5 / 3/3 (persistent until a UE acts) |
| F11 smContextRef alias (new) | dereg e85748e / rel e85748e / dereg +#4485 / rel +#4485 | 5/5 / 3/3 / 3/3 / 2/2 |
| F12 UPF orphan after re-registration (new) | AMF crash + re-registration, gNB p2 | 5/5 (+ 3/3 in boundary `amf dereg.amf_rx`) |
| lazy probe not repaired (v2 rule) | e85748e / +#4485 | 5/5 / 3/3 |
| OAI #33 | v2.2.2 (incl. rel variant) / pinned 9d8e866+5a0a6d4 | 4/4 / 3/3 |
| OAI O-1 | v2.2.2 / UPF 5a0a6d4 / pinned / UPF +PR #43 | 3/3 / 2/2 / 2/2 / **0/3** |
| OAI O-2, O-3 | v2.2.2 | 3/3, 3/3 |
| free5GC SMF / UPF restart | v4.0.1 | 1/1, 1/1 (n = 1) |

**Boundary campaign, complete: 54 schedules × seeds {0,1,2} = 162/162 executed, 162 fault fired, 0 harness errors**
(`campaign2/boundary_c2.csv`, `boundary/boundary_summary.txt`; 7 workers on instances 0,2–7; k=2, netem 150 ms,
72 s window, crash = SIGKILL + immediate start; AMF schedules use the campaign-1 gNB p1 + watchdog, `gnb_tool_crash` in
54/54 AMF runs — see C2.6 for the p2 comparison).
- **Persistent (any conjunct violated at its Δ_j and 2Δ_j): 54/162** — SMF 27/54, AMF 21/54, UPF 6/54 (1 of the 6 is the
  UERANSIM TUN artefact). No `late` verdict (clean at Δ_j, violated at 2Δ_j) and no numeric-class transient that
  outlived Δ_j: every non-persistent UPF run converged by 28.2 s (median 12.7 s, n = 48) < Δ_j = 33.8 s; SMF by 24.4 s
  (n = 27); AMF (p1 gNB) median 26.1 s, max 56.7 s — 12 AMF PDU-boundary runs converged after 33.8 s, all of them via the
  gNB-tool restart.
- **Determinism across seeds:** 17 schedules persistent in 3/3 seeds, 35 in 0/3, `upf pdu.smf_sess_added` 2/3,
  `upf pdu.n2_modify` 1/3 (the artefact). 20 unique keys (conjunct set, NF, boundary).
- **Per NF / schedule (persistent seeds / 3):** SMF — `pdu.ip_allocated`, `pdu.upf_sess_added` (F7), `pdu.n2_modify`
  (R1+R4), `rel.n2_released`, `rel.smf_sess_removed`, `rel.amf_sess_removed`, `rel.upf_sess_removed` (R1+R4),
  `dereg.sm_release`, `dereg.smf_sess_removed` all 3/3 (R1, NU); `pdu.smf_sess_added`, `dereg.amf_rx`,
  `dereg.ue_ctx_release` and all 5 registration boundaries 0/3. UPF — **`rel.upf_sess_removed` 3/3** (SMF released by
  give-up while the N1/N2 release was in flight: SMF 0, AMF 2, UEs PS-ACTIVE → R1+R4; next use fails) and
  `pdu.smf_sess_added` 2/3 (SMF session not at the UE, IP still installed: R2+R6); every other UPF boundary 0/3.
  AMF (UE class) — `reg.complete`, `rel.amf_sess_removed`, `rel.smf_sess_removed`, `rel.n2_released` (R5),
  `pdu.n2_modify` (R2 R4 R5), `rel.upf_sess_removed` (R2 R3 R4), `dereg.amf_rx` (R2 R6) all 3/3.
- **Oracles on the same 162 runs:** crash-only **0/54**; liveness fails in **36/54** persistent runs and in 0 clean runs;
  **18/54 persistent runs are liveness-silent** = 15 SMF NU runs that the next use repairs *with success* (lazy repair
  v2 → classified as NU design divergence, not bugs) + **3 AMF `dereg.amf_rx` runs** (orphan SMF session + leaked IP
  that survives the UEs' re-registration as `R3-orphan-UPF` + `R6-leak-UPF-ip` — the F12 mechanism).
  **After triage, the R-only candidates on this campaign are the 3 `dereg.amf_rx` runs (F12)**; everything else R flags
  is also visible to liveness or is classified (NU repaired / UE class).
- **Lazy repair:** campaign-1 rule (R clean after next use) 30/54; **v2 rule (and every next-use action succeeded)
  15/54** — the other 15 "repairs" were empty-but-consistent states after a failed next use (R1 N2 confirmed).
- **Count vs identity oracle** (`testbed/c2/oracle_compare.py`, 67.6 s snapshot): 54/162 violated under either. Conjuncts
  seen only by counts/probes in 20 runs (R4 ×13, R3+R4 ×3, R3 ×2, R6 ×2 — the identity readouts do not cover the UPF or
  the data plane); conjuncts seen only by identity in 5 runs (R5 ×3, R6 ×2). On these schedules identity checks add
  little beyond counts; they are decisive for F11 (alias, `Rg-id-alias-ip`) and for attributing which (SUPI, PSI)
  dangles (F7, lazy probe).
- **Statistics:** each condition was run identically 3 (boundary) or 5 (candidates) times; we report reproduction counts
  only, no confidence intervals.

## C2.11 What was not done / failures / caveats
- Not done: spec-text verification of TS 24.501 §5.4.5.2.5 for F7 (left open); periodic-registration repair of F4
  (UERANSIM keeps the UE connected, so T3512 never ran); TS 23.007 clause check; SCP restart and new-pod-IP faults;
  free5GC at the paper's pinned commits (release v4.0.1 used) and > 1 run per fault; O-2/O-3 at the pinned OAI commits
  or with #43; OAI GitLab search for the O-2 sub-finding; A4′ with direct (non-SCP) SBI.
- Tool artefacts found and flagged: UERANSIM `TUN allocation failure` (3 runs; flagged `ue_tun_alloc_failure`);
  UERANSIM gNB abort on SCTP loss (fixed by p2; p1 still used in the boundary AMF schedules, with the p2/p1 comparison in
  C2.6); single-container UEs make UL/DL probes ambiguous when two UEs hold the same IP (F11, F7 no-netem) — verdicts
  there rest on SMF logs, dumpers and PFCP.
- Harness incidents: identity readout crashed on an AMF UE context without SUPI (1 boundary + 1 AMF run, fixed and
  re-run; `*_errors.jsonl`); first A4 attempt invalid (netem before pre-state; `a4/a4audit_superseded.jsonl`); boundary
  workers were re-partitioned twice (skip-done), so a few in-progress schedules were restarted (their partial pcaps, if
  any, are under `pcap/aborted/`).
- Environment: up to 8 Open5GS stacks + free5GC in one 8-vCPU VM (load average ≤ 4.5); timing-sensitive conclusions
  (A4′ positions, phase) are taken from per-run pcaps/logs. gtp5g stays loaded in the `recover5g` VM kernel; the
  free5GC stack (`f5g-*`) and all `r5g*` instances were left running; VMs left running; `default` profile untouched.
- No upstream issue or PR was filed or commented on.

## At a glance — campaign 2
- **Duplicates:** F7 = Open5GS PR #4485 (fixes it 5/5 → 0/5); F5a R1 overlaps #4485 (fixed only on next use, UE-side
  stale PSI + IP alias remain); O-1 = OAI UPF #41 (PR #43: 3/3 → 0/3). **F4 overlaps the #4892/#4895/#4540/#4528
  threads but none of #4963/#4895/#4540/#4528(AMF) fixes it** (SMF `Unknown message [209]` in the releasing state;
  Service Accept reports PSI 1 active despite the SMF's 403) → plausibly new.
- **New candidates:** **F11** Open5GS smContextRef reuse after SMF restart → UE1's stale ref releases UE2's session,
  13/13 (not fixed by #4485; no upstream match found); **F12** SMF replaces an existing (SUPI, PSI) without PFCP
  deletion → orphan UPF sessions + leaked IPs after AMF crash + re-registration, 5/5 (+3/3 in boundary).
- **A4′:** 9/9 runs, same AMF path (404 via SCP retry) at all three positions; R converges.
- **Oracle fidelity:** identity-level oracle + per-run pcaps (SBI/PFCP/NGAP+NAS decoded) on every campaign-2 run.
- **Per-conjunct:** UPF-restart Δ_j = 33.8 s held in every convergent UPF run (max 28.2 s); F4 unchanged for 1,600 s;
  the three campaign-1 "36 s" AMF runs are gNB-dependent (converge with gNB restart, persist as UE class without).
- **Boundary:** 162/162 schedules (3 seeds); 54 persistent, 17 schedules 3/3 deterministic; crash-only 0; liveness-silent
  18 (15 NU repaired, 3 F12); lazy repair v2 15/54 vs v1 30/54.
- **Phase:** 29 runs, φ spread 0.08–9.94 s, prediction error ≤ 0.34 s; detection always by give-up; classes A
  (d < φ+7.5) / B; phase-dependent only for 7.5 < d < 18.5 s.
- **OAI #33 reproduced** at pinned 9d8e866 (3/3) and v2.2.2; **free5GC** v4.0.1 + gtp5g running, SMF restart → RC1 class.
