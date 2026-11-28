# Stage 4: OAI CN5G v2.2.2 + UERANSIM (second core)

Real runs from 2026-11-06. This is a separate Colima VM, so it does not disturb the Open5GS campaigns.

## Setup

```sh
colima start recover5g-oai --arch aarch64 --vm-type vz --cpu 4 --memory 8 --disk 40
docker context use colima-arm64native          # colima switches the global context; restore it
colima ssh -p recover5g-oai -- sudo modprobe sctp
export DOCKER_CONTEXT=colima-recover5g-oai     # run_oai.py sets this itself
python3 run_oai.py up                          # mysql + NRF/UDR/UDM/AUSF/AMF/SMF/UPF + UERANSIM gNB/UE container
python3 run_oai.py smoke --k 2
python3 run_oai.py fault --nf oai-smf --downtime 0  --window 45 --k 2 --tag smf-crash-d0
python3 run_oai.py fault --nf oai-upf --downtime 0  --window 45 --k 2 --tag upf-crash-d0
python3 run_oai.py fault --nf oai-smf --downtime 45 --window 45 --k 2 --tag smf-crash-d45
```

The `recover5g-oai` profile was left running.

## Images (all arm64; official multi-arch, Docker Hub)

| Image | Digest |
|---|---|
| oaisoftwarealliance/oai-nrf:v2.2.2 | sha256:b1e6b45e139d48fd797214ddccb3f80de3898da234455aadc3c231f001d99453 |
| oaisoftwarealliance/oai-udr:v2.2.2 | sha256:077c7c9b638c0da809ff03010888f8c3b6845a54b8d3339cb4dc93f00d4259d4 |
| oaisoftwarealliance/oai-udm:v2.2.2 | sha256:d1dab1494edec5091d2210b7bacebf83ae716b5229005bf3e34ea1ba16c14422 |
| oaisoftwarealliance/oai-ausf:v2.2.2 | sha256:6a9703cc39859bdbecf56d3ac6ee98a4f656b03d9e35bef50e3c9995b7cbd876 |
| oaisoftwarealliance/oai-amf:v2.2.2 | sha256:2935c9a8b4720aeb55367ca9aa038ff2c98c3cf557572ad41db1caa0bb6c58ab |
| oaisoftwarealliance/oai-smf:v2.2.2 | sha256:6f7a499255d05c292611065e13e7022ebe5c65a55e90a75b0448578f6fb1518b |
| oaisoftwarealliance/oai-upf:v2.2.2 | sha256:4ebdb0f7b5e4cab6880c0c95db6c92ea566906b7bbe311665bbc3f586781073c |
| mysql:8.0 | sha256:7dcddc01f13bab2f15cde676d44d01f61fc9f99fe7785e86196dfc07d358ae2b |
| r5g/ueransim:4f45e18-p1 | sha256:a986970af9d49f1e567162f4641d8d8a967845a9a98181c6db79785d266e2e71 (same image as the Open5GS testbed, copied with `docker save \| docker load`) |

These are release images (v2.2.2, 2026-10-30), **not** the paper's pinned HEAD commits (OAI SMF `9d8e866`, UPF `5a0a6d4`).

## Configs

The configs are `conf/basic_nrf_config.yaml` and `database/oai_db2.sql` from the GitHub mirror `OPENAIRINTERFACE/oai-cn5g-fed` at tag v2.2.1 (`3beb7e35`). gitlab.eurecom.fr returned HTTP 429. Changes from upstream:

- the log level is `info` instead of `debug`;
- **the AMF integrity order is NIA2, NIA1, NIA0.** With the upstream order (NIA0 first), the AMF selected NIA0, and UERANSIM rejected the Security Mode Command with "[IA0] cannot be accepted as the UE does not have an emergency";
- the images are pinned to v2.2.2 instead of `develop`;
- mysql 8.0 is used, with a `mysqladmin ping` healthcheck;
- `oai-ext-dn` is dropped;
- the IPs are static: 192.168.70.130–141.

The UE is `imsi-20895000000003{1,2}` with key `0C0A3460…535B` and OPc `63bfa50e…737d`, PLMN 208/95, TAC 0xa000, DNN `oai`, SST 1. The UPF runs simple-switch (no BPF and no kernel module). SBI uses HTTP/2 cleartext (`http_version: 2`), and NRF discovery is on.

## What works

- **Registration**, **PDU session establishment** (IPs 12.1.1.130/.131) and **UE→UPF ping round trip** all work. tcpdump on the gNB shows the ping carried as GTP-U in both directions (`.140:2152 <-> .134:2152`).
- A ping from inside the simple-switch UPF container to a UE IP does **not** work, because the UPF does not route packets from its own netns. The data-plane probe is therefore the UE-originated round trip, which exercises both UL and DL GTP-U.
- The first PDU session of the first UE usually took about 12 s. The first NAS attempt was dropped and then retransmitted on T3580.
- The core is ready (N4 association) about 1 s after start. The gNB's NG Setup succeeds on the first try.

## Restart time (`docker start` → readiness)

- SMF: 1.12 s and 1.11 s (`Received N4 ASSOCIATION SETUP RESPONSE`).
- UPF: 0.25 s (same marker on the SMF side).

## What is not done or not working

- No per-NF session gauges were found for OAI (unlike Open5GS `/metrics`). The view is assembled from UE state, data-plane probes and logs.
- The AMF prints a UE table every 20 s, but it carries no PDU-session column.
- Only a single run (one seed) per fault was done.
- No boundary-triggered crashes were run on OAI.
- No AMF, NRF or gNB faults were run on OAI.
