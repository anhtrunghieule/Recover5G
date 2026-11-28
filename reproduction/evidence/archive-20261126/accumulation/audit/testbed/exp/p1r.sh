#!/bin/bash
# Stock-gNB condition with a harness gNB restart. Usage: p1r.sh <inst> <image> <label> [marker]
cd "/Users/xuanbachle/Workstation/Mobisys/Recover5G/experiments/revision-20261125-claude/testbed"; . "/Users/xuanbachle/Workstation/Mobisys/Recover5G/experiments/revision-20261125-claude/env.sh"; export R5G_INST=$1 R5G_OUT="/Users/xuanbachle/Workstation/Mobisys/Recover5G/experiments/revision-20261125-claude/results/raw/orphan"
UERANSIM_IMAGE=r5g/ueransim:4f45e18-p1 python3 exp/orphan_repl.py --image $2 --fault amf --runs 5 --tag $3-p1r --restart-gnb
