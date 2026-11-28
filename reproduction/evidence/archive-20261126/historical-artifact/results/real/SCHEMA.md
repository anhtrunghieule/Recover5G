# Schema of `results/real/`

Every file here comes from a real run on the container testbed (`artifact/testbed/`, see its README). Nothing is simulated.

| File | Producer | Content |
|---|---|---|
| `SUMMARY.md` | hand-written from the files below | findings, with evidence excerpts and replay steps |
| `provenance.json` | `docker image inspect` | image IDs, the `/COMMIT` file inside each image, VM facts |
| `repro.jsonl` | `testbed/repro.py` | one JSON object per issue-reproduction run (`scenario` ∈ i4877, i4860, i4892) |
| `downtime.jsonl` / `.csv` | `campaign.py downtime` | steady-state faults on upf/smf/amf/nrf/gnb with downtime 0/10/30 s |
| `boundary.jsonl` / `.csv` | `campaign.py boundary` | crash of AMF/SMF/UPF at a resource-boundary log line of reg/pdu/rel/dereg |
| `podkill.jsonl` / `.csv` | `campaign.py podkill` | random NF crash at a uniform random offset of 0–2 s into the procedure (chaos baseline) |
| `restart_times.csv` | `testbed/measure.py restart` | `rep, nf, ready_marker, restart_to_ready_s`, from container `StartedAt` to the readiness log line, both on the VM clock |
| `lazy.jsonl` | `testbed/measure.py lazy` | R before and after UE actions following an SMF or AMF crash-restart |
| `downtime_superseded.jsonl`, `boundary_superseded.jsonl` | runner | records replaced because of harness artifacts (liveness wait too short; gNB-tool abort without watchdog), kept for transparency |
| `oai/` | stage-4 fork | OAI CN5G v2.2.2 runs (`FINDINGS-oai.md`, `oai.jsonl`, `oai_faults.csv`, `logs/`) |
| `summary.json` | `testbed/analyze.py` | per-campaign aggregates (see below) |
| `campaigns_console.log` | `run_campaigns.sh` | console trace with one line per schedule |
| `logs/<id>.log.gz` | runner / repro | NF logs (ANSI stripped in the repro logs) from schedule start, plus the tail of the UE logs |

## `repro.jsonl` fields

- `scenario`, `image`, `k` (number of UEs), `hold_s` (how long the peer NF was kept down).
- `t_*_utc`: fault timestamps in UTC.
- `series*`: time series of NF gauges. Each sample is `t` (s since the fault) plus the fields below:
  - `amf_ue` = `fivegs_amffunction_rm_registeredsubnbr`;
  - `amf_sess` = `amf_session`;
  - `ran_ue`;
  - `smf_ue` = `ues_active`;
  - `smf_sess` = `fivegs_smffunction_sm_sessionnbr`;
  - `pfcp_sess` = SMF `pfcp_sessions_active`;
  - `upf_sess` = `fivegs_upffunction_upf_sessionnbr`;
  - `ue_sessions`, the PS-ACTIVE sessions UERANSIM reports;
  - `dl_ok`, the downlink ping from the UPF's N6 side to each UE IP.
- `null` means the NF's metrics endpoint was unreachable (NF down). In the first i4892 pre-fix run, all metrics are `null` while the UE container was paused. In that run the scraper still ran inside the UE container; it was moved to the `r5g-probe` container afterwards.
- `*_evidence`: matching NF log lines.
- `R_violations_*`: the output of `oracle.check_R`.

## Campaign CSV columns (`analyze.py`)

| Column | Meaning |
|---|---|
| `id` | schedule id (`B-<proc>-<boundary>-<nf>-k<k>-s<seed>`, `D-<nf>-<mode>-d<downtime>-k<k>-s<seed>`, `P-<n>`) |
| `proc` | procedure under test: `reg` (power on → initial registration), `pdu` (PDU session establishment), `rel` (release), `dereg` (deregistration, which UERANSIM follows with re-registration), `idle` (steady state, downtime campaign) |
| `nf`, `mode`, `downtime` | fault target, fault kind (`crash` = SIGKILL then start after `downtime` s) |
| `boundary` | trigger name (regex in `r5g/runner.py:BOUNDARIES`). The fault fires on the first matching log line after the procedure starts |
| `t_offset` | pod-kill offset (s) from procedure start |
| `netem_ms` | egress delay on every core NF, used to widen the windows between steps |
| `fault_fired`, `fault_at_s` | whether and when (s after procedure start) the fault fired |
| `restart_ready_s` | `docker start` → readiness marker: SMF/UPF "PFCP associated", AMF "NF registered", gNB "NG Setup procedure is successful" |
| `gnb_tool_crash` | UERANSIM's `nr-gnb` aborted ("terminate called recursively") when the AMF's SCTP association dropped. The harness restarted the gNB, emulating NG re-setup by a real gNB. Two early AMF-target boundary runs that hit this before the watchdog existed are in `boundary_superseded.jsonl` |
| `victim_last_line` | the victim's last log line before the kill, i.e. the effective crash point |
| `ever_violated` | some R conjunct failed in at least one 3 s poll after the restart |
| `viol_at_delta` | conjuncts violated at the first poll ≥ Δ_core = 26 s after the restart |
| `viol_end` | conjuncts violated at the end of the window (36 s) |
| `first_poll_s` | time of the first R poll after restart (for runs before the readiness-thread fix — downtime and boundary campaigns — UPF-target runs only started polling after SMF re-association, so `t_conv` there is an upper bound "converged by") |
| `t_conv` | first poll time after which every later poll in the window is clean (convergence time; resolution = poll interval 3 s, lower-bounded by `first_poll_s`) |
| `late_convergence` | violated at Δ but clean at window end, i.e. Δ under-estimated convergence |
| `R_detects` | violated at both Δ and window end (persistent violation) |
| `crash_oracle`, `crash_detects` | the crash-only oracle: an NF we did not kill is down, or `Assertion`/`FATAL` appears in AMF/SMF/UPF logs |
| `liveness_ok`, `liveness_detects` | the pod-kill baseline's oracle: all NFs up and every UE can use its session or obtain a new one |
| `next_use` | per-UE result of the next-use step (`ul-ok`, `pdu-ok`, `re-register-ok`, `*-FAIL`) |
| `viol_after_next_use` | R re-checked 3 s after the next use |
| `lazy_repair` | violated at window end but clean after next use, i.e. repair happens only when the UE acts |
| `error` | harness failure (the schedule is excluded from the aggregates) |
| `wall_s` | wall-clock time of the schedule |

## R conjunct labels (`r5g/oracle.py`)

`R1-dangling` (AMF sessions > SMF), `R1-dangling-UE` (UE PS-ACTIVE > SMF), `R2-orphan-SMF` (SMF > AMF), `R2-orphan-SMF-vs-UE`, `R3-orphan-UPF` / `R3-missing-UPF` (UPF ≠ SMF sessions), `R4-blackhole` (PS-ACTIVE but the DL probe fails), `R5-amf-lost-ue` / `R5-stale-amf-ue` (AMF registered count ≠ UEs RM-REGISTERED), `R6-leak-UPF-ip`, `Rg-alias`, and `NONCONV` (NF metrics unreachable).

Except R4, the R6 IP list and Rg, the checks compare **counts**. Unequal counts prove a violation, but swaps that preserve the counts are missed.

## `summary.json`

Per campaign:
- `schedules`, `harness_errors`, `fault_fired`;
- `R_violations_persistent` and the unique keys (violated-conjunct set, NF, boundary);
- `schedules_to_first_violation` (1-based, in execution order);
- crash and liveness oracle detections, and how many R violations each oracle misses;
- `late_convergence_after_delta`, `lazy_repair`;
- the convergence-time distribution of transient-only runs;
- `restart_ready_s_by_nf`.

## `campaign2/` (round-2 campaign, 2026-11-06)

| Path | Producer | Content |
|---|---|---|
| `source_facts.md` | source reading at pinned commits + read-only `gh api` | upstream PR status, patch applicability, allocator disciplines, OAI smContextRef, Open5GS PFCP timers |
| `dup/F7.jsonl`, `F7_c2.csv` | `campaign.py one` (v2 runner) | F7 replays at e85748e and e85748e-pr4485 (with/without netem) |
| `f5a/F5a.jsonl`, `F5a_c2.csv` | `campaign.py downtime` / inline | steady-state SMF crash, e85748e and pr4485 |
| `f4/repro.jsonl` | `repro.py i4892 --pcap` | F4 replays (e85748e, pr4540, pr4895, pr4528amf) and the 1,600 s long-horizon replay |
| `alias/alias.jsonl`, `alias/alias_eval.csv` | `c2/alias.py`, `c2/alias_eval.py` | F11 smContextRef reuse (per-run pcap-derived ref/PFCP evidence) |
| `a4/a4audit.jsonl`, `a4audit_c2.csv`, `a4/a4_paths.csv` | `c2/a4audit.py` | A4′ audit (positions pre/flight/recv × 3) and the AMF-side path per run |
| `lazy/lazy_c2.jsonl` | `c2/lazy_c2.py` | lazy-repair replication with identity snapshots before/after UE actions |
| `amf/amf_rerun_p2.jsonl`, `amf/amf_rerun_p1.jsonl`, `amf_rerun_c2.csv`, `amf/f5b.jsonl` | `c2/amf_rerun.py`, `c2/f5b.py` | the 11 campaign-1 AMF schedules with the patched gNB (p2) and the original gNB (p1, control); AMF crash + re-registration orphan check |
| `phase/phase.jsonl`, `phase_c2.csv`, `phase/phase_eval.csv` | `c2/phase.py`, `c2/phase_eval.py` | UPF crash after a random 0–11 s offset, downtime 0/3/6/9/12 s; heartbeat phase φ, give-up, T_b, detection path |
| `boundary/boundary_c2*.jsonl`, `boundary_c2.csv` | `c2/boundary_c2.py` | 54 boundary schedules × seeds 0–2 (one file per worker; ids are unique across files) |
| `free5gc/` | `testbed/free5gc/run_f5g.py` | free5GC v4.0.1 SMF/UPF restart runs, gtp5g build log |
| `oai/` | `testbed/oai/run_oai_c2.py` (+ `decode_c2.py`, `summarize_c2.py`) | OAI O-1/O-2/O-3/#33 replays at v2.2.2 and pinned commits, PR #43 image |
| `console/` | job scripts | console traces |
| `smoke/` | `campaign.py one` | first v2-harness smoke run (F7 schedule on instance 1), kept for provenance |
| `replication_c2.csv` | `testbed/c2/replication.py` | per-candidate reproduction counts |
| `*/pcap/*.pcap.gz`, `*.ids.json` | `r5g/capture.py`, `c2/pcap_ids.py` | per-run capture of the instance bridge; decoded SBI/PFCP/NGAP+NAS/GTP-U identities |

v2 runner fields (in addition to the campaign-1 ones): `series[].vid` (identity labels), `series[].amf_id/smf_id`
(dumper readouts), `snap` (labels at 5.5/11/26/33.8/36/67.6/72 s), `final_detail_id`, `t_conv_all`,
`vid_after_next_use`, `next_use_all_ok`, `pcap`. CSV (`analyze_c2.py`): `viol_<t>` (count ∪ identity labels),
`conjunct_verdicts` (`Rx:persistent|transient|late(num|NU|UE)`), `persistent_*`, `lazy_repair_v1` (campaign-1 rule),
`lazy_repair_v2` (violated at 67.6 s, clean after next use, every next-use action succeeded).
