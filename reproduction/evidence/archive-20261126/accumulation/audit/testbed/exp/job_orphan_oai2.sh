#!/bin/bash
# Second OAI batch: identical recipe, capture filter excludes the RF-simulator sample stream (TCP 4043).
cd "/Users/xuanbachle/Workstation/Mobisys/Recover5G/experiments/revision-20261125-claude/testbed"; while pgrep -f "exp/job_f5g[.]sh" >/dev/null; do sleep 10; done
export DOCKER_CONTEXT=colima-r5g-claude-ran R5G_INST=5 R5G_OUT="/Users/xuanbachle/Workstation/Mobisys/Recover5G/experiments/revision-20261125-claude/results/raw/orphan-oai"
export R5G_CAP_FILTER="not port 27017 and not port 9090 and not tcp port 4043"
docker compose -f "/Users/xuanbachle/Workstation/Mobisys/Recover5G/experiments/revision-20261125-claude/testbed/free5gc/docker-compose.yml" down -v -t 1 >/dev/null 2>&1
python3 exp/orphan_oai.py --image r5g/open5gs:e85748e           --fault amf  --runs 5 --tag base
python3 exp/orphan_oai.py --image r5g/open5gs:e85748e-f12repair --fault amf  --runs 5 --tag repair
python3 exp/orphan_oai.py --image r5g/open5gs:e85748e-f12repair --fault none --runs 3 --tag repair-nofault
python3 exp/orphan_oai.py --image r5g/open5gs:e85748e           --fault none --runs 3 --tag base-nofault
echo "=== $(date) oai batch 2 done"
