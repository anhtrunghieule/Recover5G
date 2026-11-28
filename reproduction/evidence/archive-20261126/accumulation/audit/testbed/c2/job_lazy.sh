#!/bin/bash
export DOCKER_CONTEXT=colima-recover5g R5G_INST=4 R5G_OUT=/Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/results/real/campaign2/lazy
cd /Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/testbed
python3 c2/lazy_c2.py --runs 5
