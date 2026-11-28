#!/bin/bash
# usage: job_boundary2.sh <inst> <part> <skip-files>
export DOCKER_CONTEXT=colima-recover5g R5G_INST=$1 R5G_OUT=/Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/results/real/campaign2/boundary
cd /Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/testbed
python3 campaign.py up >/dev/null 2>&1 || python3 campaign.py up
python3 c2/boundary_c2.py --seeds 0,1,2 --part $2 --skip "$3" --name boundary_c2_i$1
