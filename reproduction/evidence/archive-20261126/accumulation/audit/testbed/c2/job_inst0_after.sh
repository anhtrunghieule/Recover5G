#!/bin/bash
# after the F7 job: F7 without netem (m5), 2 per image; then boundary seed 2 on instance 0
cd /Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/testbed
while pgrep -f job_f7.sh >/dev/null; do sleep 15; done
export DOCKER_CONTEXT=colima-recover5g R5G_INST=0 R5G_OUT=/Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/results/real/campaign2/dup
c2/loop_one.sh r5g/open5gs:e85748e F7nonetem-e85748e "0 1" F7.jsonl --proc pdu --nf smf --boundary pdu.upf_sess_added --netem 0
c2/loop_one.sh r5g/open5gs:e85748e-pr4485 F7nonetem-pr4485 "0 1" F7.jsonl --proc pdu --nf smf --boundary pdu.upf_sess_added --netem 0
export R5G_OUT=/Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/results/real/campaign2/boundary
python3 campaign.py up >/dev/null 2>&1
python3 c2/boundary_c2.py --seeds 2 --part 0/1 --name boundary_c2_s2
