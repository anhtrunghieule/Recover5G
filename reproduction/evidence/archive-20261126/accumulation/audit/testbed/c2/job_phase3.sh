#!/bin/bash
export DOCKER_CONTEXT=colima-recover5g R5G_INST=1 R5G_OUT=/Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/results/real/campaign2/phase
cd /Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/testbed
python3 campaign.py up >/dev/null 2>&1
python3 c2/phase.py --downtimes 0,6 --reps 4 --rstart 6 --seed 23
