#!/bin/sh
# Real campaigns run on 2026-11-06 (Open5GS e85748e, UERANSIM 4f45e18-p1). Sequential; each is resumable.
set -x
cd "$(dirname "$0")"
export DOCKER_CONTEXT=${DOCKER_CONTEXT:-colima-recover5g}
# python3 campaign.py up   (testbed already up; runner.reset() restarts every NF per schedule)
# (1) downtime dimension + gNB/NRF faults at steady state (2 UEs with sessions)
python3 campaign.py downtime --nfs upf,smf,amf,nrf,gnb --downtimes 0,10,30 --k 2 --seeds 1 --window 36 --poll 3
# (2) systematic boundary campaign: crash AMF/SMF/UPF at each resource boundary of 4 procedures, k=2
python3 campaign.py boundary --procs reg,pdu,rel,dereg --nfs amf,smf,upf --ks 2 --seeds 1 --netem 150 --window 36 --poll 3 --budget 2600
# (3) random pod-kill baseline on the same workloads
python3 campaign.py podkill --runs 12 --ks 2 --netem 150 --window 36 --poll 3 --budget 1500
