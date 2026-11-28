# Codebook for labelling 5G-core GitHub issues (restart / peer-failure state bugs)

Study: open-source 5G/4G cores (Open5GS, free5GC, OAI CN5G, SD-Core/OMEC). We want bugs where
cross-NF state becomes wrong or fails to converge after an NF or peer failure event.

## include ∈ {yes, maybe, no}
- **yes** iff BOTH: (1) the bug appears after an NF or peer restart / crash / heartbeat loss /
  outage-unreachability / association re-setup (PFCP, SCTP/NGAP, S1AP, GTP path) / restoration
  (peers include AMF, SMF, UPF, NRF, PCF, UDM, UDR, AUSF, gNB/eNB, and EPC MME/SGW/PGW; a peer
  signalling lost state via GTP-U Error Indication or NG Reset also counts as a peer-failure event);
  AND (2) it concerns cross-NF state (UE/session contexts, identifiers, IP/TEID/SEID allocations,
  associations, registrations/subscriptions) or convergence back to service.
- **no**: malformed/adversarial-input crashes without a peer failure (fuzzing territory),
  build/config/usage questions, feature requests, docs, UE-only failures, bugs unrelated to a
  failure/restart event (e.g. ordinary handover bug, normal-path crash) — even if they mention
  restart in passing ("I restarted and it still doesn't work" for a config problem is NO).
- **maybe**: genuinely unclear after reading the full thread (e.g. failure event is ambiguous,
  or it is unclear whether it is a code bug vs misconfiguration).

## For include=yes rows only (leave blank for maybe/no):
root_cause ∈ {lost-allocation-state, identifier-reuse-aliasing, missing-cleanup-on-peer-failure,
stale-restoration, unadvanced-recovery-timestamp, association-handling, other}
- lost-allocation-state: an NF loses its allocation/bookkeeping (IP pool, TEID/SEID/ID allocators,
  UE context store) across restart, so it re-allocates conflicting values or cannot reconcile with peers.
- identifier-reuse-aliasing: an identifier (TEID, SEID, UE IP, NGAP/S1AP UE ID, SUPI-keyed context…)
  is reused so two entities/contexts alias.
- missing-cleanup-on-peer-failure: when a peer fails/disconnects/is declared dead, the surviving NF
  does not release (or mis-releases) the state tied to that peer (sessions, UE contexts, PDRs, timers).
- stale-restoration: on recovery/reconnection the NF keeps or restores stale state that conflicts
  with the peer's fresh state (e.g. re-associates but keeps pre-restart sessions; restores from DB/cache
  inconsistent with reality; stale NF profile/registration at NRF).
- unadvanced-recovery-timestamp: Recovery Time Stamp (PFCP/GTP) not advanced/compared, so a restart
  is not detected.
- association-handling: bugs in setting up / releasing / re-setting-up / heartbeating an association
  itself (PFCP association, SCTP/NGAP/S1AP association, NRF registration/heartbeat), e.g. never
  re-associates, duplicate association, wrong handling of association release.
- other: none of the above (write the reason in the rationale).

symptom (primary, choose ONE) ∈ {orphan, dangling, alias, leak-exhaustion, black-hole, non-convergence, crash}
- orphan: state left behind in an NF with no live counterpart (e.g. UPF sessions with no SMF session).
- dangling: an NF keeps a reference to a peer/context that no longer exists and acts on it later.
- alias: two entities share one identifier/state (traffic/signalling goes to the wrong context).
- leak-exhaustion: resources leak and eventually exhaust (pools, memory, IDs) → later failures.
- black-hole: user-plane traffic silently dropped while control plane believes things are fine.
- non-convergence: the system does not return to service after recovery — registration / PDU session
  establishment / re-association keeps failing, NF stuck, endless retries, observable outage.
- crash: an NF process crashes / asserts / aborts / segfaults.

silent ∈ {yes, no}: yes iff NFs stay up AND no error reaches the operator at the time the state is
  corrupted (corruption is only discovered later or by inspection). A crash is never silent; an
  explicit error log/rejection or observable failure seen at that time → no.
crash_only_detects ∈ {yes, no}: yes iff an NF process crash/abort is the visible symptom (an oracle
  that only watches for NF crashes would catch it).
persistent_failure_detects ∈ {yes, no}: would a Kairos-style oracle — NF crash OR persistent service
  unavailability / request failure observed by the UE or test driver *within the test* (e.g.
  registration or PDU session establishment fails and keeps failing, UE data plane persistently
  down when probed) — detect it? no if the effect is only internal state (stale/orphan entries, slow
  leak not exhausting within a short test, wrong context that still lets the test's UE succeed),
  only transient (recovers on retry), or needs many cycles / long time / other UEs not in the test
  to become visible.

rationale: 1–2 sentences, concrete (what failed, what event, why these labels). Note "thread:"
facts that only appear in comments when they change the label.
