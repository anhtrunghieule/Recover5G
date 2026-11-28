#!/bin/bash
export DOCKER_CONTEXT=colima-recover5g R5G_INST=0 R5G_OUT=/Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/results/real/campaign2/dup
cd /Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/testbed
c2/loop_one.sh r5g/open5gs:e85748e F7-e85748e "0 1 2 3 4" F7.jsonl --proc pdu --nf smf --boundary pdu.upf_sess_added --netem 150
c2/loop_one.sh r5g/open5gs:e85748e-pr4485 F7-pr4485 "0 1 2 3 4" F7.jsonl --proc pdu --nf smf --boundary pdu.upf_sess_added --netem 150
