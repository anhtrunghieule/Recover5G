#!/bin/bash
# Orphan-session replication matrix. Usage: job_orphan.sh <inst> <open5gs image> <label>
set -u
cd "/Users/xuanbachle/Workstation/Mobisys/Recover5G/experiments/revision-20261125-claude/testbed"; . "/Users/xuanbachle/Workstation/Mobisys/Recover5G/experiments/revision-20261125-claude/env.sh"
export R5G_INST=$1 R5G_OUT="/Users/xuanbachle/Workstation/Mobisys/Recover5G/experiments/revision-20261125-claude/results/raw/orphan"
IMG=$2; L=$3
UERANSIM_IMAGE=r5g/ueransim:4f45e18-p2 python3 exp/orphan_repl.py --image $IMG --fault amf  --runs 5 --tag $L-p2
UERANSIM_IMAGE=r5g/ueransim:4f45e18-p2 python3 exp/orphan_repl.py --image $IMG --fault none --runs 3 --tag $L-p2-nofault
UERANSIM_IMAGE=r5g/ueransim:4f45e18-p1 python3 exp/orphan_repl.py --image $IMG --fault amf  --runs 5 --tag $L-p1
