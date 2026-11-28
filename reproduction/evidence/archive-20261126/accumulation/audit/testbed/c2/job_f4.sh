#!/bin/bash
export DOCKER_CONTEXT=colima-recover5g R5G_INST=1 R5G_OUT=/Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/results/real/campaign2/f4
cd /Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/testbed
for r in 1 2 3 4 5; do echo "== $(date +%T) e85748e r$r"; python3 repro.py i4892 --image r5g/open5gs:e85748e --k 2 --hold 30 --after 75 --pcap --tag F4-e85748e-r$r | grep -E '"R_violations_final"|next_use' -A3 | head -20; done
for img in pr4540 pr4895; do for r in 1 2; do echo "== $(date +%T) $img r$r"; python3 repro.py i4892 --image r5g/open5gs:e85748e-$img --k 2 --hold 30 --after 75 --pcap --tag F4-$img-r$r | grep -E '"R_violations_final"' -A3 | head -8; done; done
echo "== $(date +%T) long horizon"; python3 repro.py i4892 --image r5g/open5gs:e85748e --k 1 --hold 30 --after 1600 --pcap --tag F4-e85748e-k1-long1600 | grep -E '"R_violations_final"' -A3
