#!/bin/bash
export DOCKER_CONTEXT=colima-recover5g R5G_INST=6 R5G_OUT=/Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/results/real/campaign2/alias
cd /Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/testbed
python3 c2/alias.py --variant dereg --runs 4 --start 2 --image r5g/open5gs:e85748e
python3 c2/alias.py --variant rel --runs 3 --image r5g/open5gs:e85748e
python3 c2/alias.py --variant dereg --runs 3 --image r5g/open5gs:e85748e-pr4485
python3 c2/alias.py --variant rel --runs 2 --image r5g/open5gs:e85748e-pr4485
