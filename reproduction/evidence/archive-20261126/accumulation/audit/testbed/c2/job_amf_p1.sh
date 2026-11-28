#!/bin/bash
# control: the same 11 AMF schedules with the campaign-1 gNB image (p1, aborts on SCTP loss; harness watchdog restarts it)
export DOCKER_CONTEXT=colima-recover5g R5G_INST=7 R5G_OUT=/Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/results/real/campaign2/amf UERANSIM_IMAGE=r5g/ueransim:4f45e18-p1
cd /Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/testbed
while pgrep -f "c2/f5b.py|c2/amf_rerun.py --reps 1$" >/dev/null || pgrep -f "c2/job_amf.sh" >/dev/null; do sleep 15; done
python3 campaign.py up >/dev/null 2>&1
python3 c2/amf_rerun.py --reps 1 --tag p1
