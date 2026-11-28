#!/bin/bash
cd "/Users/xuanbachle/Workstation/Mobisys/Recover5G/experiments/revision-20261125-claude/testbed"; export DOCKER_CONTEXT=colima-r5g-claude-ran F5G_OUT="/Users/xuanbachle/Workstation/Mobisys/Recover5G/experiments/revision-20261125-claude/results/raw/free5gc"
while pgrep -f "exp/job_orphan_oai[.]sh" >/dev/null; do sleep 10; done
docker compose -f "/Users/xuanbachle/Workstation/Mobisys/Recover5G/experiments/revision-20261125-claude/oai-ran/docker-compose.oai-ran.yml" down -t 1 >/dev/null 2>&1
R5G_INST=5 python3 -c "import sys; sys.path.insert(0,'.'); from r5g import testbed; testbed.down()" >/dev/null 2>&1
echo "=== $(date) free5GC control start"
python3 exp/f5g_control.py --nf none --runs 5
python3 exp/f5g_control.py --nf smf,upf,amf --runs 3
echo "=== $(date) free5GC chain done"
