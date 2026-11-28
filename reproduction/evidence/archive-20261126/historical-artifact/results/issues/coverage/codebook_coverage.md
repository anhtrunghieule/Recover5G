# Coverage-map codebook (fault model of the Recover5G tool)

Context: Recover5G is a testing tool for open 5G cores that injects NF failures and checks
cross-NF state invariants. For each issue (a confirmed restart/peer-failure state bug), decide
what failure scenario is needed to trigger it and whether the tool's fault model covers it.
Label from the FULL thread (body + comments). Never invent facts; when the thread is silent,
pick the most plausible value and say "inferred" in the rationale.

Fields:
- trigger ∈ {immediate-restart, crash-stop-downtime, gnb-restart/NG-reset/SCTP-loss, nrf-restart,
  association-resetup, network-partition/unreachability-without-crash, other}
  * immediate-restart: an NF is killed and restarted quickly; restart is detected via PFCP/GTP
    Recovery Time Stamp, re-registration, or reconnection.
  * crash-stop-downtime: a peer is down/unreachable long enough for heartbeat give-up / path
    failure declaration (e.g. 'docker stop upf, wait, docker start'; 'UPF stopped, SMF declares it dead').
  * gnb-restart/NG-reset/SCTP-loss: gNB/eNB (RAN) restart or disconnect, NG Reset / S1 Reset,
    SCTP association loss on N2/S1.
  * nrf-restart: NRF restart / NRF heartbeat loss / NRF outage is the trigger.
  * association-resetup: (PFCP) association release + re-setup without a process crash.
  * network-partition/unreachability-without-crash: peer process stays up but is unreachable or
    unresponsive (iptables drop, overload, hung peer, dropped responses).
  * other: anything else (e.g. GTP-U Error Indication from a peer, UE-triggered, config change).
- failed_entity ∈ {AMF, SMF, UPF, PCF, UDM, AUSF, NRF, gNB, UDR, other}: the entity that fails /
  restarts / becomes unreachable (EPC: map MME→other, SGW-C/PGW-C→other, SGW-U/PGW-U→other; say which
  in the rationale). If several, the primary one.
- n_faults_needed ∈ {1, >1}: number of distinct failure injections needed (e.g. two NFs restarted,
  or the same NF restarted repeatedly before the bug shows → >1).
- n_ues_needed ∈ {1, 2, >2/pool-pressure}: UEs needed to expose the bug (>2/pool-pressure if it
  needs many UEs, load, or pool exhaustion / many sessions; 2 if it needs a second UE to collide/alias).
- in_original_fault_model ∈ {yes, no}: yes iff failed entity ∈ {AMF, SMF, UPF, PCF, UDM, AUSF},
  a single crash suffices (n_faults_needed = 1), AND an immediate restart (no prolonged downtime /
  heartbeat give-up needed, no partition) triggers it. (UE count does not matter for this field.)
- in_extended_fault_model ∈ {yes, no}: the original model plus: downtime classes d ∈ {0, <heartbeat
  give-up, >give-up} for the crashable set, gNB restart / NG Reset / SCTP loss, and NRF restart.
  Still single fault. yes if the original model covers it or one of these additions does
  (an unreachable-but-alive peer is NOT covered unless crash-stop with downtime reproduces the same
  effect — say so in the rationale if you judge that it does). EPC entities (MME/SGW/PGW) are outside
  both models unless the same bug is shown for a 5GC NF.
- needs_timer_phase ∈ {yes, no}: whether the outcome depends on heartbeat/association timer phase or
  expiry (e.g. bug only appears if downtime exceeds heartbeat give-up, or races with a timer).
- rationale: 1–2 concrete sentences.
