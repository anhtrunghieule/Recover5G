#!/bin/bash
# chain.sh <inst> <wait-pattern> <cmd...>: wait until no process matches the pattern, then run the commands in order.
cd "/Users/xuanbachle/Workstation/Mobisys/Recover5G/experiments/revision-20261125-claude/testbed"; . "/Users/xuanbachle/Workstation/Mobisys/Recover5G/experiments/revision-20261125-claude/env.sh"; export R5G_INST=$1; PAT=$2; shift 2
while pgrep -f "$PAT" >/dev/null; do sleep 10; done
for c in "$@"; do echo "=== $(date) inst $R5G_INST: $c"; eval "$c"; done
echo "=== $(date) inst $R5G_INST: chain done"
