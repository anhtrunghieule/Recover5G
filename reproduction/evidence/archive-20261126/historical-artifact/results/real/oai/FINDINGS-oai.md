# OAI CN5G v2.2.2: real fault runs (stage 4, 2026-11-06)

Each fault was run once (k = 2 UEs with active sessions). Δ_OAI = 40 s (`results/timers/delta.csv`). The raw data is in `oai.jsonl` and `oai_faults.csv`, and the logs are in `logs/*.log.gz`. These are candidates and have not been reported upstream.

## O-1: SMF crash and restart, downtime 0 (`smf-crash-d0`)

The SMF is killed at 18:59:36 UTC and is ready again 1.12 s later. It re-associates with the UPF, and the UPF logs no session deletion:

```
18:59:37.727 [upf_n4] Handle SX ASSOCIATION SETUP REQUEST / Associated with CP function oai-smf
```

- All SM contexts are lost in the SMF, yet the UPF keeps both sessions.
- Both UEs keep PS-ACTIVE, and GTP-U forwarding works in every sample over 48 s, which is longer than Δ_OAI. The UPF sessions are now orphaned (R3) and the AMF/UE refs are dangling (R1). They forward traffic with no SMF control (TS 23.527 §4.4.2 / O2).
- On the UE's next use (PDU release), the SMF logs `[smf_app] [warning] SM Context associated with this id 0x1 does not exit!` (and the same for 0x2). The release does not complete within the observed window.

## O-2: UPF crash and restart, downtime 0 (`upf-crash-d0`)

The UPF is killed at 19:01:40 and is ready again 0.25 s later. At 19:01:40.925 the SMF logs "Received N4 ASSOCIATION SETUP RESPONSE".

- No restoration and no release happen. The SMF, AMF and UEs keep 2 PS-ACTIVE sessions.
- **The data plane fails for both UEs in every sample for 47 s**, longer than Δ_OAI. This is R4 black-hole plus R3 missing UPF sessions (O1/§4.3.2 restoration not performed).
- A UE-initiated release is processed by the SMF (`PDU Session Release (UE-Initiated)`, N4 deletion sent), but the UE still showed the dead PSI 1 about 8 s later.

## O-3: SMF crash with 45 s downtime (`smf-crash-d45`)

The SMF is killed at 19:03:30.

- During the 45 s outage, **the UPF sends no heartbeat** to the SMF. The only heartbeat lines are `Received SX HEARTBEAT REQUEST` (SMF→UPF), and none appear between 19:03:30 and 19:04:16. So TS 23.527 §4.4.3.1 cleanup cannot trigger. This matches `timers.csv`: the UPF→SMF heartbeat runs only if the SMF PFCP Node ID is IPv4, and here it is the FQDN `oai-smf`.
- The sessions keep forwarding for 45 s of outage plus 48 s after the restart.
- The SMF re-associates at 19:04:16.888 without any session deletion, which is the same outcome as O-1.

The O-1 and O-3 interpretation assumes that the restarted SMF advertises a new Recovery Time Stamp in its Association Setup. That is likely, because it is a new process, but it was not decoded from the wire.
