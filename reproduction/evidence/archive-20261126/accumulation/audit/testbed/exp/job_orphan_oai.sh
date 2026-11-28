#!/bin/bash
cd "/Users/xuanbachle/Workstation/Mobisys/Recover5G/experiments/revision-20261125-claude/testbed"; export DOCKER_CONTEXT=colima-r5g-claude-ran R5G_INST=5 R5G_OUT="/Users/xuanbachle/Workstation/Mobisys/Recover5G/experiments/revision-20261125-claude/results/raw/orphan-oai"
python3 exp/orphan_oai.py --image r5g/open5gs:e85748e           --fault amf  --runs 5 --tag base
python3 exp/orphan_oai.py --image r5g/open5gs:e85748e-f12repair --fault amf  --runs 5 --tag repair
python3 exp/orphan_oai.py --image r5g/open5gs:e85748e-f12repair --fault none --runs 3 --tag repair-nofault
python3 exp/orphan_oai.py --image r5g/open5gs:e85748e           --fault none --runs 3 --tag base-nofault
echo "=== $(date) oai chain done"
