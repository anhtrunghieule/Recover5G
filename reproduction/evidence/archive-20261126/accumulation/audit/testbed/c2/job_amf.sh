#!/bin/bash
export DOCKER_CONTEXT=colima-recover5g R5G_INST=7 R5G_OUT=/Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/results/real/campaign2/amf UERANSIM_IMAGE=r5g/ueransim:4f45e18-p2
cd /Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/testbed
python3 c2/amf_rerun.py --reps 1
python3 c2/f5b.py --runs 5
