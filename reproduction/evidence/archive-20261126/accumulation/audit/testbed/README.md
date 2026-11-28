# Recover5G real testbed (Open5GS + UERANSIM in Docker)

This directory holds the dynamic harness that turns the paper's projected (†) results into measurements.
Status, what works and what does not are listed at the end, and `../results/real/SUMMARY.md` has the findings.

## Host and VM

| Item | Value |
|---|---|
| Host | macOS arm64 (Apple M5 Max, 18 CPUs, 64 GB) |
| VM | Colima profile **`recover5g`**: aarch64, `vz`, 8 vCPU, 16 GiB, 80 GiB disk |
| Docker context | `colima-recover5g` (the harness sets `DOCKER_CONTEXT=colima-recover5g` itself; the global current context is left at whatever it was) |
| VM kernel | 6.8.0-117-generic; `sctp` module loads (`colima ssh -p recover5g -- sudo modprobe sctp`) |

```sh
colima start recover5g --arch aarch64 --vm-type vz --cpu 8 --memory 16 --disk 80
export DOCKER_CONTEXT=colima-recover5g
```

The pre-existing `default` Colima profile is x86_64 (emulated) and is not used.

## Images (built from source; no usable arm64 prebuilt images were found)

`gradiant/open5gs:2.7.6` and `gradiant/ueransim:3.2.7` are amd64-only, and openverso images were not found.
Everything is therefore built from source at pinned commits. The download comes from the GitHub tarball and the Ubuntu
packages from the `free.nchc.org.tw` ports mirror (`ports.ubuntu.com` ran at about 50 KB/s from this network).

| Image | Source | Commit |
|---|---|---|
| `r5g/open5gs:e85748e` | `docker/open5gs/Dockerfile` | open5gs `e85748ef3d798fa0b4435c80438e81c41bbe5e13` (2026-11-05, the paper's pinned commit) |
| `r5g/open5gs:48c0cc0` | `docker/open5gs/Dockerfile.commit` | open5gs `48c0cc03740f1c36e5d868c94d21774a86bd8512` (parent of the #4892 fix `fc26daab9b`) |
| `r5g/ueransim:4f45e18` | `docker/ueransim/Dockerfile` | UERANSIM `4f45e18f80b0684f7d6e29f1fea0f579e9243d68` (2026-10-14, HEAD) |
| `mongo:7.0` | Docker Hub | digest in `../results/real/provenance.json` |

```sh
cd docker
docker build -t r5g/open5gs:e85748e open5gs
docker build -t r5g/ueransim:4f45e18 ueransim
docker build --target build -t r5g/open5gs-build:base open5gs          # cached
docker build -f open5gs/Dockerfile.commit --build-arg OPEN5GS_COMMIT=48c0cc03740f1c36e5d868c94d21774a86bd8512 \
  -t r5g/open5gs:48c0cc0 open5gs
```

Image IDs are recorded in `../results/real/provenance.json`.

## Topology

`docker-compose.yml` defines one bridge network, `172.22.0.0/24`. Each Open5GS NF keeps the last octet of its default
`127.0.0.x` address: NRF .10, SCP .200, AUSF .11, UDM .12, UDR .20, PCF .13, NSSF .14, BSF .15, SMF .4, AMF .5, UPF .7.
MongoDB is at .100, the gNB at .50 and the UE container at .51.

- The configs in `config/open5gs/` are the upstream `configs/open5gs/*.yaml.in` at `e85748e`, with addresses rewritten, logging to stderr at INFO, and IPv6 pools removed.
- **SBI is cleartext HTTP/2 (h2c).** The default configs have no `tls:` section, so the scheme is `http`.
- **SCP routing is on.** Each NF's `sbi.client` names the SCP, `http://172.22.0.200:7777`, and has no `delegated` block. That means AUTO delegation: NF-to-NF requests and NRF discovery go through the SCP.
- The UE pool is `10.45.0.0/16`, and the UPF creates `ogstun`.
- The UE container runs `sleep infinity`. The harness starts one `nr-ue -c /cfg/ue.yaml -i imsi-99970000000000N` per UE when that UE should "power on" (initial registration). It then drives PDU session establishment and release and deregistration with `nr-cli`. The UE config has `sessions: []`, so no session is set up automatically.
- Subscribers `imsi-999700000000001..8` (K/OPc are the UERANSIM defaults) are inserted with `mongosh` (`r5g/testbed.py`).

## Harness (`r5g/`, stdlib Python + docker CLI)

| Module | Role |
|---|---|
| `dock.py` | docker / compose subprocess wrappers |
| `testbed.py` | deploy, provision, readiness checks, optional `tc netem` |
| `workload.py` | UE power on/off, `nr-cli` (`ps-establish`, `ps-release`, `deregister`, `status`, `ps-list`) |
| `observe.py` | Prometheus `/metrics` of AMF/SMF/UPF, UE-side view, DL/UL ping probes, log-derived UPF session IPs |
| `oracle.py` | the R checks (R1 dangling, R2 orphan, R3 N4 bijection, R4 black-hole, R5 registration, R6 leak, R_g alias, non-convergence) plus the crash-only oracle |
| `inject.py` | log-triggered faults (a streaming `docker logs -f` that fires on a boundary log line): crash-restart, crash with downtime, `docker stop`/start, `docker pause` |
| `runner.py` | one schedule: reset, pre-state, armed fault, procedure for k UEs (seeded order and stagger), restart, R polled every 2 s up to Δ+10 s (convergence time), verdict at Δ=26 s, crash and liveness oracles, next-use (lazy repair) probe, logs saved |
| `campaign.py` | CLI: `up`, `smoke`, `boundary`, `podkill`, `downtime`, `one` |

Other scripts:

| Script | Role |
|---|---|
| `repro.py` | issue reproductions `i4877`, `i4860`, `i4892`, each with a time series, evidence lines and saved logs |
| `measure.py` | per-NF restart time on the VM clock (container `StartedAt` to readiness line), plus lazy-repair probes after an SMF or AMF crash |
| `analyze.py` | campaign JSONL → CSV + `summary.json` |
| `run_campaigns.sh` | the exact campaign sequence that was run |
| `oai/` | stage-4 OAI CN5G v2.2.2 testbed on a separate Colima profile (`recover5g-oai`); see `oai/README-oai.md` |

## Commands that were run (2026-11-06)

```sh
export DOCKER_CONTEXT=colima-recover5g
python3 campaign.py up && python3 campaign.py smoke --k 4            # stage 1
python3 repro.py i4877 --image r5g/open5gs:e85748e  --k 2 --hold 60   # post-fix control
python3 repro.py i4877 --image r5g/open5gs:pre4877  --k 2 --hold 60 --tag pre4877-d915126
python3 repro.py i4860 --image r5g/open5gs:e85748e  --k 2 --hold 50
python3 repro.py i4892 --image r5g/open5gs:48c0cc0  --k 2 --hold 30 --after 60   # x2
python3 repro.py i4892 --image r5g/open5gs:e85748e  --k 2 --hold 30 --after 60
python3 repro.py i4892 --image r5g/open5gs:e85748e  --k 1 --hold 30 --after 300
./run_campaigns.sh                                                   # downtime, boundary, podkill
python3 analyze.py
python3 measure.py restart --reps 3; python3 measure.py lazy
```

## What works

- Stage 1. All 11 Open5GS 5GC NFs and MongoDB come up with a provisioned subscriber, along with the UERANSIM gNB and UEs. NG Setup, registration and PDU session establishment work for 1–4 UEs. Ping runs UE↔UPF in both directions (`uesimtunN` ↔ `ogstun`).
- Smoke test with 4 UEs: all registered, all got sessions (10.45.0.2–5), R is clean, and UL and DL pings succeed.
- Deploy takes 3–33 s. The fast per-schedule reset (kill and start every NF and the gNB) takes about 6 s. A full schedule takes 70–135 s of wall time.
- Log-triggered crash injection works. With `netem 150 ms` on every NF's egress, the windows between procedure steps widen to about 150–300 ms, against a `docker kill` latency of about 100 ms. The effective crash point is recorded as the victim's last log line.

## What does not work, or differs from the paper's design

- **No SBI or PFCP wire taps and no shadow model.** The projection comes from Prometheus gauges (counts), UERANSIM state, data-plane pings and log lines. R1/R2/R3/R5 are therefore *count-level* checks, which are sound for detecting mismatches but blind to swaps that preserve counts. The paper's per-reference attribution is not implemented.
- **No cgroup-freezer gating at a message.** Crash points are realised by a log-line trigger plus netem widening. A crash can land one step after the intended boundary, so the effective point (`victim_last_line`) is recorded. `docker pause` is used only as the "UE unreachable" fault in the #4892 recipe.
- **UERANSIM quirks.**
  - `nr-cli` has no `register` command, so registration happens when the `nr-ue` process starts.
  - `deregister normal` is followed by automatic re-registration.
  - A NAS request is sometimes dropped by a UAC/RRC synchronisation timeout ("No response from RRC from UAC checks"), and the UE only retransmits on T3580/T3582 (16 s). Patching the wait from 100 to 2000 ms reduced this but did not remove it. Waits in the harness are therefore at least 25 s.
  - UERANSIM lacks PDU session modification and handover.
  - UERANSIM's `nr-gnb` can abort ("terminate called recursively") when the AMF's SCTP association drops during a procedure. The runner then restarts the gNB and sets `gnb_tool_crash=true`.
- **Not implemented:** CRIU stale-state restore, SBI delay/duplication faults, DDMin minimisation (minimisation was done by hand for F4), free5GC (its go-upf needs the gtp5g kernel module, which the Colima kernel lacks), and the Kairos and CoreCrisis baselines.
- The `restart_ready_s` value in `downtime.csv` uses the host clock against VM log timestamps with a generic marker. It is unreliable for AMF, NRF and gNB, which show about 0.01 s. Use `restart_times.csv` from `measure.py`, which uses the VM clock only.
- One seed per cell in the downtime and boundary campaigns: these are counts of observed behaviour, not statistics.

## State at the end of the session

The Colima profiles **`recover5g`** (Open5GS testbed) and **`recover5g-oai`** (OAI testbed) were left **running**. The global Docker context was restored to `colima-arm64native`; every command here sets `DOCKER_CONTEXT` explicitly. To stop them: `colima stop recover5g; colima stop recover5g-oai`.

## Campaign 2 additions (2026-11-06)

Raw data: `../results/real/campaign2/` (see the "Campaign 2" section of `../results/real/SUMMARY.md`).

| Item | What |
|---|---|
| `inst.py` | generates independent testbed instances `inst/<N>/` (containers `r5g<N>-*`, subnet `172.(22+N).0.0/24`); select with `R5G_INST=N` (0 = the campaign-1 testbed). Up to 8 Open5GS stacks ran side by side in the 8-vCPU VM (load average 3–4.5). |
| `R5G_OUT` | output directory of `campaign.py` / `repro.py` / `c2/*.py` (campaign 2 writes under `results/real/campaign2/<subdir>`) |
| `r5g/capture.py` | per-schedule pcap of the instance bridge (`tcpdump` in a `--net host` container, started before the NF reset so every HTTP/2 connection is decodable; MongoDB and metrics traffic filtered) |
| `r5g/observe.py` `amf_ue_info()` / `smf_pdu_info()` | identity readouts from Open5GS's JSON dumpers on the metrics port (AMF `/ue-info`: SUPI, GUTI, NGAP ids, PSIs; SMF `/pdu-info`: SUPI, PSI, UE IPv4, N3 TEIDs, state) |
| `r5g/oracle.py` `check_R_id()` | identity-level conjuncts (labels `R1id-*`, `R2id-*`, `R5id-*`, `R6id-*`, `Rg-id-alias-ip`) next to the count-level ones |
| `r5g/runner.py` | 72 s window (≥ 2 × 33.8 s), snapshots at 5.5/11/26/33.8/36/67.6/72 s, `next_use_all_ok`, custom triggers (`trigger`, `trigger_delay`), per-NF netem (`netem_per_nf`, `netem_after_pre`) |
| `c2/pcap_ids.py` | tshark (`r5g/tshark:1`) decode: SBI sm-context requests paired with status/Location, smContextRef issuance per SMF incarnation, PFCP SEIDs/UE IPs/causes/RTS, NGAP + null-ciphered NAS, GTP-U Error Indications |
| `c2/analyze_c2.py`, `c2/make_all.sh` | per-conjunct verdicts at Δ_j / 2Δ_j → `results/real/campaign2/*_c2.csv` |
| `c2/boundary_c2.py`, `c2/relaunch_boundary.sh` | 54 boundary schedules × 3 seeds, partitioned over instances, skip-done |
| `c2/alias.py`, `c2/alias_eval.py` | Open5GS smContextRef reuse after an SMF restart (OAI #33 analog) |
| `c2/a4audit.py` | SMF crash before / during / after the AMF's ReleaseSMContext |
| `c2/lazy_c2.py`, `c2/f5b.py`, `c2/amf_rerun.py`, `c2/phase.py`, `c2/phase_eval.py` | lazy-repair replication, AMF-crash re-registration orphan check, the 11 AMF schedules re-run, heartbeat-phase runs |
| `docker/open5gs/Dockerfile.patched`, `patches/` | e85748e + upstream PR diffs (#4485, #4540 rebased, #4528 AMF half, #4895) |
| `docker/ueransim/Dockerfile.p2`, `gnb-sctp-survive.patch` | `r5g/ueransim:4f45e18-p2`: the gNB survives AMF SCTP loss (no abort, fixes a dangling SCTP client entry, releases UE contexts locally with RRC Release, retries SCTP + NG Setup every 2 s) |
| `free5gc/` | free5GC v4.0.1 release images (arm64) + gtp5g v0.9.14 built in the VM (kernel headers installed from the nchc mirror; the VM apt source was temporarily switched to that mirror and restored afterwards; backup at `/etc/apt/ubuntu.sources.r5g-backup`) |
| `oai/run_oai_c2.py` etc. | OAI campaign 2 (pinned SMF 9d8e866 / UPF 5a0a6d4 images built in the OAI VM, PR #43 image) |
