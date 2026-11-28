#!/bin/bash
# usage: relaunch_boundary.sh "<inst list>"  -- stop all boundary workers, then split the remaining schedules (all seeds)
cd /Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/testbed
pkill -f job_boundary2.sh; pkill -f boundary_c2.py; pkill -f job_boundary.sh; pkill -f job_inst0_after.sh; sleep 3
for f in /Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/results/real/campaign2/boundary/boundary_c2*.jsonl; do case $f in *errors*) ;; *) python3 c2/strip_errors.py $f ;; esac; done
SKIP=$(ls /Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/results/real/campaign2/boundary/boundary_c2*.jsonl | grep -v errors | paste -sd, -)
set -- $1; n=$#; i=0
for inst in "$@"; do
  nohup c2/job_boundary2.sh $inst $i/$n "$SKIP" >> /Users/xuanbachle/Workstation/MobiSys2027/papers/P02-recover5g/artifact/results/real/campaign2/console/boundary_i$inst.log 2>&1 &
  i=$((i+1)); sleep 20
done
