#!/bin/bash
export DOCKER_CONTEXT=colima-recover5g R5G_INST=5 R5G_OUT=/Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/results/real/campaign2/a4
cd /Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/testbed
true
python3 c2/a4audit.py --reps 3
