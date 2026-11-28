#!/bin/bash
export DOCKER_CONTEXT=colima-recover5g R5G_INST=5 R5G_OUT=/Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/results/real/campaign2/f5a
cd /Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/testbed
python3 campaign.py up >/dev/null 2>&1 || python3 campaign.py up
python3 campaign.py downtime --nfs smf --downtimes 0 --seeds 5 --name F5a --window 72
