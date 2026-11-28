#!/bin/bash
export DOCKER_CONTEXT=colima-recover5g R5G_INST=6 R5G_OUT=/Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/results/real/campaign2/phase
cd /Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/testbed
while pgrep -f "c2/phase.py --downtimes 0,3,6,12 --reps 3" >/dev/null; do sleep 15; done
python3 c2/phase.py --downtimes 3,6,9 --reps 3 --rstart 3 --seed 11
