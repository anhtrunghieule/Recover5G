# Campaign 2 — source facts and upstream PRs (read from pinned source, 2026-11-06)

Pinned Open5GS: `e85748ef3d798fa0b4435c80438e81c41bbe5e13` (permalink base
`https://github.com/open5gs/open5gs/blob/e85748ef3d798fa0b4435c80438e81c41bbe5e13/`, abbreviated `O5/`).
All line numbers were read from the tarball of that commit. PR metadata comes from `gh api` (read-only) on 2026-11-06.

## 1. Upstream PRs (open5gs/open5gs)

| PR | State (2026-11-06) | Created / merged | Head SHA (merge SHA) | Files | In e85748e? |
|---|---|---|---|---|---|
| #4485 "amf: clean up stranded sess on 404 from SMF sm-contexts modify" (MrBrownieCGN) | **open**, 2 commits | 2026-04-25 / – | `6fda4531` | `src/amf/nsmf-handler.c` +66 | **No** (unmerged) |
| #4486 "SMF/MME/AMF: operator-facing admin endpoints for stranded-context recovery" | **open**, 7 commits | 2026-04-25 / – | `df6a77bc` | 26 files (admin handlers in amf/smf/mme) | **No** |
| #4895 "smf: restore only the sessions the UE still has after a UPF restart" | **open**, 1 commit | 2026-10-20 / – | `5e786861` | `src/smf/pfcp-sm.c` +44 | **No** (superseded in part by #4963) |
| #4963 "smf: Restore only operational sessions after UPF restart" (acetcom) | **merged** | 2026-11-04 / 2026-11-04 | `1359a5c0` (merge `fc26daab9b7d5d7b6d053cefa3e47f259db1c9a9`) | `src/smf/pfcp-sm.c` +19 | **Yes** — `compare/fc26daab...e85748e` = `ahead 3, behind 0`. **#4963 == fc26daab9b**, so `r5g/open5gs:48c0cc0` (its parent) is "without #4963" and `e85748e` is "with #4963". |
| #4540 "[SMF] Send SmContextStatusNotify on all 5GC release paths" | **open**, 1 commit | 2026-05-08 / – | `be6ec5aa` | `src/smf/{gsm-sm.c,pfcp-sm.c,sbi-path.c,sbi-path.h}` | **No** |
| #4528 "[AMF/SMF] Fix N1N2MessageTransfer race that leaks PDU sessions and IP-pool addresses" (fixes #4427) | **open**, 2 commits | 2026-05-06 / – | `fd0ed28d` | `src/amf/{amf-sm.c,namf-handler.c,namf-handler.h}`, `src/smf/{gsm-sm.c,namf-handler.c}` | **No**, but its SMF half is **superseded** by upstream `d322bedebe` "[SMF] Release SM context when AMF rejects establishment" (2026-08-14), an ancestor of e85748e (`O5/src/smf/namf-handler.c` L64–89 now releases the SM context locally on a non-2xx N1N2 answer during establishment). The AMF half (400→404 for a missing UE context) is not in e85748e (`O5/src/amf/amf-sm.c` L204–207 still answers 400 "No N1N2MessageTransferReqData"). |
| #4555 "smf: gracefully preserve session state on 5xx N1N2MessageTransfer responses" | **open** | 2026-05-10 / – | `9b9e2e53` | `src/smf/namf-handler.c` | **No** (1 of 4 hunks fails on e85748e; not built) |

Mechanisms (from the diffs):
- **#4485**: in `amf_nsmf_pdusession_handle_update_sm_context()`, before the `SmContextUpdateError` check, a `404` answer to `sm-contexts/{ref}/modify` is treated as authoritative: for `SERVICE_REQUEST` the AMF `AMF_SESS_CLEAR(sess)` (removes the AMF sess) and still sends Service Accept when all sessions answered; `PATH_SWITCH_REQUEST` keeps the old error path; **every other state (including state 19 = `AMF_UPDATE_SM_CONTEXT_DUPLICATED_PDU_SESSION_ID`, the F7 retry path) → `AMF_SESS_CLEAR(sess)`, return OK**. It acts *only on 404*: if the stale ref resolves to a live session of another UE in the restarted SMF (see §3 alias), no 404 is returned and the patch does nothing.
- **#4486**: admin HTTP endpoints to list/release stranded contexts by hand (operator tooling, no automatic repair).
- **#4895**: adds `restoration_wanted()` — skip restoration if the session is not operational (same as #4963) **or** if a later session of the same UE/PSI replaced it ("Skip restoration: session replaced"). Release of the skipped sessions is untouched ("continues as today").
- **#4963 / fc26daab**: in `pfcp_restoration()` skip sessions not in `smf_gsm_state_operational` (`"[%s:%d] Skip restoration: not operational"`, `O5/src/smf/pfcp-sm.c` ~L480–497). The F4 log line is exactly this string.
- **#4540**: helper `smf_sbi_try_send_sm_context_status_notify_before_release()`; called at entry of `smf_gsm_state_session_will_release` and `smf_gsm_state_exception`, and on the two `SMF_TIMER_PFCP_NO_DELETION_RESPONSE` paths in `pfcp-sm.c`, so the AMF gets `SmContextStatusNotify(RELEASED)` on releases that bypass the FSM's own notify. Relevant to F4 only if the stuck session ever reaches one of those states (in F4 it stays in a releasing state waiting for N1/N2, so #4540 is not expected to fire — to be tested).
- **#4528 (AMF half)**: AMF answers N1N2MessageTransfer for an unknown UE with 404 instead of 400; SMF half (local release) — already upstream via `d322bedebe`.

## 2. Patch files and images

Saved under `artifact/testbed/docker/open5gs/patches/` (`https://github.com/open5gs/open5gs/pull/N.diff`, fetched 2026-11-06),
dry-run with GNU patch 2.7 inside `r5g/open5gs-build:base` against the e85748e tree:

| File | Applies to e85748e? | Notes |
|---|---|---|
| `pr4485.diff` | **clean** (1 hunk, offset +111) | used as-is |
| `pr4486.diff` | **no** (5 hunks fail: amf-sm.c, mme-context.c/.h, mme-init.c, smf-sm.c) | not built (operator endpoints only; no automatic repair) |
| `pr4540.diff` | 1 hunk fails (`sbi-path.h`: context line `void smf_sbi_send_pdu_session_created_data` became `bool ...` upstream) | **`pr4540-rebased.diff`**: same code, only the header prototype re-anchored after `smf_sbi_send_sm_context_status_notify()`; other hunks verified to land in `smf_gsm_state_session_will_release`, `smf_gsm_state_exception` and both `SMF_TIMER_PFCP_NO_DELETION_RESPONSE` cases |
| `pr4528.diff` | SMF `namf-handler.c` hunk fails (code already replaced upstream by `d322bedebe`) | **`pr4528-amf-only.diff`** = the three `src/amf/*` file diffs only (SMF half superseded upstream) |
| `pr4895.diff` | applies (fuzz 2) on top of #4963 | adds the "session replaced" skip |
| `pr4555.diff` | 1 of 4 hunks fails | not built |

`artifact/testbed/docker/open5gs/Dockerfile.patched` (FROM `r5g/open5gs-build:base`, e85748e tarball, `ARG PATCHES` applied in
order with `patch -p1`, each name appended to `/COMMIT`, `ninja -j4` under `nice`):

```sh
cd artifact/testbed/docker/open5gs
docker build -f Dockerfile.patched --build-arg PATCHES="pr4485.diff" -t r5g/open5gs:e85748e-pr4485 .
```

Built images (DOCKER_CONTEXT=colima-recover5g): see the "Image status" table at the end of this file.

## 3. Allocators at e85748e

`ogs_pool` (`O5/lib/core/ogs-pool.h`): `ogs_pool_alloc` (L132) takes `free[head]`, `head=(head+1)%size`; `ogs_pool_free` (L143)
puts the node at `free[tail]`, `tail=(tail+1)%size`. The free list is a **circular FIFO queue**, initialised in array order
(`ogs_pool_init`, `free[i]=&array[i]`, head=tail=0). `ogs_pool_index` (L152) = slot index + 1. `ogs_pool_random_id_generate`
(L186) fills an `ogs_pool_id_t` pool's array with a random permutation of 1..size (`ogs_random32()` = `getrandom()`, fresh per
process, `O5/lib/core/ogs-rand.c` L40–52). All pools live in process memory: a restart re-initialises them (head=0).

| Identifier | Allocation (pinned source) | Discipline | After restart |
|---|---|---|---|
| **smContextRef** (and `pduSessionRef`, charging id) | `sess->index = ogs_pool_index(&smf_sess_pool, sess)` `O5/src/smf/context.c#L1749`; `sess->sm_context_ref = ogs_msprintf("%d", sess->index)` `#L1763`; lookup `smf_sess_find_by_sm_context_ref()` → `smf_sess_find(atoll(ref))` → `ogs_pool_find(&smf_sess_pool, index)` `#L2299-L2314` | slot index of the FIFO-queue pool (size `pool.sess` = `max.ue × 4` = 1024×4 = **4096**, `O5/lib/app/ogs-config.c#L67`, `OGS_MAX_NUM_OF_SESS 4`) | **first session after an SMF restart gets ref "1", then "2", …** — exactly the refs the AMF still holds from the previous incarnation |
| SMF N4 SEID / N4 TEID | `ogs_pool_alloc(&smf_n4_seid_pool, ...)` `O5/src/smf/context.c#L1753`; pool `ogs_pool_random_id_generate(&smf_n4_seid_pool)` `#L94` | FIFO queue over a random permutation of 1..4096 | new random permutation per process |
| UPF N4 SEID | `ogs_pool_init(&upf_n4_seid_pool)` + `ogs_pool_random_id_generate` `O5/src/upf/context.c#L51-L52`; alloc `#L202` | same | new permutation |
| UPF F-TEID (PDR) | `ogs_pfcp_pdr_teid_pool` + `ogs_pool_random_id_generate` `O5/lib/pfcp/context.c#L68-L69` | same | new permutation |
| **UE IPv4** | subnet pool array filled in address order (`ue_ip = &subnet->pool.array[poolindex]`, start+inc, skipping network/gateway) `O5/lib/pfcp/context.c#L2572-L2604`; `ogs_pfcp_ue_ip_alloc()` → `ogs_pool_alloc(&subnet->pool, &ue_ip)` `#L2654`; free → tail `#L2665-L2678` | **FIFO free queue in address order** (not first-fit: a freed address is reused only after the rest of the pool has been handed out) | head resets: **a restarted SMF hands out 10.45.0.2, .3, … again** |
| AMF-UE-NGAP-ID | `ran_ue->amf_ue_ngap_id = ran_ue->index` (ran_ue_pool slot index) `O5/src/amf/context.c#L1479` | FIFO queue slot index (size max.ue = 1024) | restarts at 1 |
| 5G-GUTI M-TMSI | `ogs_pool_random_id_generate(&m_tmsi_pool)` (size 2×max.ue) `O5/src/amf/context.c#L67-L68`; mapping in `amf_m_tmsi_alloc()` | FIFO over random permutation | new permutation (old GUTIs unknown → UE must re-register) |

**Can a stale AMF ref alias another UE's session? Yes, by source reading.**
- Dispatch: `O5/src/smf/smf-sm.c#L551-L576`: for `POST sm-contexts/{ref}/modify|release`, `sess = smf_sess_find_by_sm_context_ref(component[1])`; 404 only if the slot is empty; otherwise the event goes to that session's FSM (`#L603-L611`). No SUPI is in the URI, and nothing compares the request with the session's SUPI.
- `/release`: `smf_nsmf_handle_release_sm_context()` (`O5/src/smf/nsmf-handler.c#L1170-L1224`) only copies location/cause; `gsm-sm.c` (operational state, `#L1267-L1306`) then moves to `smf_gsm_state_wait_pfcp_deletion` with `OGS_PFCP_DELETE_TRIGGER_AMF_RELEASE_SM_CONTEXT` → PFCP deletion of whatever session sits in that slot.
- `/modify` with an N1 SM message: `smf_nsmf_handle_update_sm_context()` reads the 5GSM header only for the PTI (`sess->pti = gsm_header->procedure_transaction_identity`, `O5/src/smf/nsmf-handler.c#L707`) and forwards it to the session (`nas_5gs_send_to_gsm(sess, ...)`, `#L725`). The **5GSM PDU session identity is never compared with `sess->psi`** (grep: no `pdu_session_identity` read in `src/smf/`; it is only written in `gsm-build.c`). So a UE1 PDU Session Release Request sent through a stale ref is processed on the aliased session of UE2.
- AMF side, `PDU Session Establishment Request` for a PSI that already has an AMF sess with `sm_context_ref` (e.g., a T3580 retransmission after an SMF restart): `O5/src/amf/gmm-handler.c#L1293-L1311` reuses the sess; `#L1690-L1704` sends `UpdateSMContext(release, cause REL_DUE_TO_DUPLICATE_SESSION_ID)` to the **old ref** with state 19 (`AMF_UPDATE_SM_CONTEXT_DUPLICATED_PDU_SESSION_ID`, `O5/src/amf/sbi-path.h#L74`); only on a 2xx does it create a new SM context (`O5/src/amf/nsmf-handler.c#L745-L789`, "Issue #3710"). On a 404 the generic error path logs `[%d:%d] Error Indication [state:%d]` (`#L1213`) and sends NGAP Error Indication; the AMF sess and its dead ref are kept (F7's `Error Indication [state:19]`). Hence: after an SMF restart, (a) if slot `ref` is empty in the new SMF → 404 loop (F7; #4485 removes the AMF sess on that 404, so the next retransmission creates a fresh context); (b) if slot `ref` has been reused by another UE's session → the "duplicate-PSI release" **releases that other UE's session** and then creates a new one for this UE. (b) is not covered by #4485.
- TS 24.501 §5.4.5.2.5 text (AMF handling of UL NAS TRANSPORT with request type "initial request" and an existing PDU session routing context): **not verified** here (spec text not fetched). Open5GS's own behaviour (release via old SMF, then create) is documented above; whether forwarding to a dead ref is a spec violation is left open.

## 4. OAI SMF (pinned `9d8e866e972a6a64a9ce3bf6ebd77a9e126f0716`, 2026-11-04)

- `smf_app::generate_smf_context_ref()` → `sm_context_ref_generator.get_uid()`
  (`https://github.com/openairinterface/oai-cn5g-smf/blob/9d8e866e972a6a64a9ce3bf6ebd77a9e126f0716/src/smf_app/smf_app.cpp#L182-L189`),
  member `oai::utils::uint_generator<uint32_t> sm_context_ref_generator` (`src/smf_app/smf_app.hpp#L70`), used at
  `smf_app.cpp#L1225-L1230` ("Step 8. Generate a SMF context Id and store ... (SM_Context_ID, (supi, pdu_session_id))").
- `uint_generator` (common-src submodule `085dce7d1f7eca4e1801eee075f4c5e98fcf20c0`, `utils/uint_generator.hpp#L59-L98`):
  `uid_generator = 0` in the constructor; `get_uid()` returns `++uid_generator`, skipping values still in `uid_generated`.
  `free_uid()` is never called for SM context refs. **Discipline: monotonically increasing counter, reset to 0 on every start
  (reset-counter class).** First ref after a restart = 1.
- Lookup: `handle_pdu_session_release_sm_context_request()` (`smf_app.cpp#L1339-L1378`) maps `scid → (supi, pdu_session_id)`
  via `scid2smf_context` and acts on that UE; no check that the requester's context matches.
- **OAI SMF issue #33** (GitHub, open, 2026-10-28, jihoon-seo): "A restarted SMF reuses SM context references, so an old
  reference from the AMF releases another UE's PDU session" — same mechanism as above, with a 4-step recipe (attach A, B;
  restart SMF (+UPF, see UPF #41); re-attach A → gets `sm-contexts/1`; stop B → AMF releases `sm-contexts/1` → A's session
  released, A keeps its IP). Fix PR **#34** "fix(smf): do not reuse SM context references after a restart" (head `f9d465b2`)
  is **open/unmerged** → not in `9d8e866` and not in `v2.2.2` (tag `b237407314`; `9d8e866` is 9 commits ahead of v2.2.2).
  So #33 is reproducible-in-principle at both the pinned commit and the v2.2.2 images.
- OAI UPF #41 (open) / PR #43 "fix(upf): delete old PFCP sessions on a new association setup" (open, unmerged).

## 5. Open5GS PFCP timers at e85748e (defaults; the testbed configs set no `time:` section)

Values (`O5/lib/app/ogs-config.c`): message duration `10 s` (`#L469`); `N1 = 3` (`#L388`), `T1 = 10/(3+1) = 2.5 s` (`#L389-L394`);
`association_interval = max(3 s, client_wait 10 s + 1 s) = 11 s` (`#L404-L407`); `no_heartbeat_duration = max(10 s, 11 s) = 11 s`
(`#L409-L412`).

Mechanics:
1. Entering `associated` (SMF `O5/src/smf/pfcp-sm.c#L188-L201`, UPF `O5/src/upf/pfcp-sm.c#L167-L180`): start `t_no_heartbeat`
   (11 s) **and** send one Heartbeat Request immediately.
2. `t_no_heartbeat` expiry (SMF `#L396-L401`): send a Heartbeat Request. The timer is **not** restarted on send.
3. The timer is restarted **only on a Heartbeat Response** (`O5/lib/pfcp/handler.c#L86-L87`). A received Heartbeat
   *Request* does not touch it; no other message re-arms it. So each side's requests go out at
   `t_assoc + r + k·(11 + r)` (`r` = HB RTT; ≈ ms without netem).
4. A Heartbeat Request is retransmitted by the xact layer at `T1` (2.5 s) while `--response_rcount > 0`
   (`O5/lib/pfcp/xact.c#L630-L645`): sends at 0, 2.5, 5.0; give-up (`node_timeout` → `SMF_EVT_N4_NO_HEARTBEAT`) at **7.5 s**.
5. SMF on give-up (`O5/src/smf/pfcp-sm.c#L425-L440`): `reselect_upf()` — for 5GC sessions on that node
   `smf_trigger_session_release(..., OGS_PFCP_DELETE_TRIGGER_SMF_INITIATED)` (`#L590-L597`) — then `will_associate`, whose
   ENTRY sends an Association Setup Request at once and re-sends it every `association_interval` = 11 s (`#L80-L108`), each
   one itself retransmitted at 2.5 s/5.0 s.
6. Recovery Time Stamp: compared **only in Heartbeat Request/Response handlers** (`O5/lib/pfcp/handler.c#L36-L47`, `#L73-L84`),
   setting `restoration_required`; association setup does not compare it.
7. Only the SMF initiates association in this testbed: `t_association` exists only for configured peers
   (`try_to_associate`, `O5/src/smf/pfcp-path.c#L64-L76`; UPF `O5/src/upf/pfcp-path.c#L25-L39`), and `upf.yaml` has an empty
   `pfcp.client`. **A restarted UPF has no node for the SMF and drops any non-association PFCP message from it**
   (`"Cannot find PFCP-Node"`, `goto cleanup`, `O5/src/upf/pfcp-path.c#L131-L153`), so it does **not** answer the SMF's
   heartbeats.

Derivations (φ = time from the fault to the next Heartbeat Request of the surviving side, φ ∈ (0, 11 + r]):
- (a) **Heartbeat give-up after a kill**: `G(φ) = φ + 7.5 s`, range (7.5, 18.5] s. Checked against campaign-1 logs
  (association time `t_a`, give-up `g`): requests fall exactly on `t_a + 11k` and `g = t_a + 11k + 7.5 − (0.05…0.32) s`
  (5 runs: `repro_i4892_pre4892-48c0cc0` k=3, `-run2` k=3, `postfix-e85748e` k=2, `postfix-e85748e-k1-long` k=4,
  `repro_i4877_pre4877` UPF side k=3). The small negative residual is consistent with timer-wheel granularity.
- (b) **UPF usable time after a UPF restart with downtime d** (from `docker start`): because the restarted UPF ignores the
  SMF's heartbeats, the SMF **always** detects the restart through give-up, never through an RTS before give-up, for every d.
  - d < G(φ): `T_b = φ + 7.5 − d (+ assoc RTT)`; the give-up releases the 5GC sessions (`reselect_upf`) and the SMF
    re-associates immediately (UPF already up). For d≈0: T_b ∈ (7.5, 18.5] s (campaign 1: 17.8 s → φ≈10.3; measure.py
    10.2–10.3 s → φ≈2.7–2.8).
  - d > G(φ): the SMF is in `will_associate`; T_b = wait until the next Association Setup transmission that reaches the
    UPF: ≤ 2.5 s if the start falls within 5 s after a retry (retransmissions at +2.5/+5.0), otherwise until the next retry
    (≤ 6 s; 11-s period). Campaign 1 d=30: 1.19 s.
  - After re-association the UPF's ENTRY heartbeat carries its new RTS → SMF sets `restoration_required`, re-associates
    (it has `t_association`) and runs `pfcp_restoration()` for sessions still operational (#4963 skips the rest).
  - Effective outage seen by the SMF: `d_eff = max(d, φ + 7.5)` (+ retry wait when d > φ + 7.5). The detection path is
    phase-**independent** (always give-up) in this configuration; only its timing depends on φ. With a UPF that has the SMF
    as `pfcp.client` (UPF-initiated association), a restarted UPF would associate itself and the SMF could learn the RTS
    before give-up — a different region; not the testbed configuration.
- (c) **Why the inferred phases cluster in [0.8, 4.5] s**: φ = 11 − ((t_fault − t_a) mod 11) is fixed by the time elapsed
  between the (re)association at deploy/reset and the fault. The harness reaches the fault after a near-constant setup
  (deploy/reset → readiness polling → UE power-on/registration with fixed sleeps → PDU sessions → fault): in the five runs
  above `t_fault − t_a` = 32.07, 32.04, 20.75, 39.44, 31.63 s, i.e. φ = 0.93, 0.97, 1.25, 4.56, 1.37 s. The heartbeat period
  is deterministic (re-armed only on responses, ≈11 s), so a near-constant setup time maps to a near-constant phase; the
  phase is not uniformly distributed, and nothing else re-arms the timer. To sample φ uniformly, add a random delay in
  [0, 11) s before the fault (or trigger the fault on the `PFCP` heartbeat send, which needs debug logs or a pcap trigger).

## Image status (DOCKER_CONTEXT=colima-recover5g)

| Tag | Patches | Status |
|---|---|---|
| `r5g/open5gs:e85748e-pr4485` | pr4485.diff | built, `sha256:3ad71d2f8623…`; `/COMMIT` = e85748e + `patch:pr4485.diff` |
| `r5g/open5gs:e85748e-pr4540` | pr4540-rebased.diff | built, `sha256:67b5035c4c58…` |
| `r5g/open5gs:e85748e-pr4528amf` | pr4528-amf-only.diff | built, `sha256:42b1351ac1f1…` |
| `r5g/open5gs:e85748e-pr4895` | pr4895.diff | built, `sha256:65bb12c41413…` |

All four compile at e85748e; none has been run yet (no behavioural claim is made here). Not built: #4486 (5 hunks fail),
#4555 (1 hunk fails).
