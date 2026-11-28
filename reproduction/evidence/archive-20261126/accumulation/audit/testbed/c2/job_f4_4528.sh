#!/bin/bash
export DOCKER_CONTEXT=colima-recover5g R5G_INST=6 R5G_OUT=/Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/results/real/campaign2/f4
cd /Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/testbed
while pgrep -f "c2/phase.py --downtimes 3,6,9" >/dev/null; do sleep 15; done
for r in 1 2; do python3 repro.py i4892 --image r5g/open5gs:e85748e-pr4528amf --k 2 --hold 30 --after 75 --pcap --tag F4-pr4528amf-r$r | grep -A3 '"R_violations_final"'; done
