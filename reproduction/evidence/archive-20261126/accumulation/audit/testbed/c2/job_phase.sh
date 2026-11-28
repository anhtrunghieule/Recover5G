#!/bin/bash
export DOCKER_CONTEXT=colima-recover5g R5G_INST=6 R5G_OUT=/Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/results/real/campaign2/phase
cd /Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/testbed
while pgrep -f job_alias.sh >/dev/null; do sleep 15; done
python3 campaign.py up >/dev/null 2>&1 || python3 campaign.py up
python3 c2/phase.py --downtimes 0,3,6,12 --reps 3
