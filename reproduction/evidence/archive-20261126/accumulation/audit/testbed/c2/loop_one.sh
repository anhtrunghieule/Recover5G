#!/bin/bash
# usage: loop_one.sh <image> <idprefix> <seeds> <name> <campaign.py one args...>
img=$1; pre=$2; seeds=$3; name=$4; shift 4
cd "$(dirname "$0")/.."
python3 campaign.py up --image "$img" >/dev/null 2>&1 || python3 campaign.py up --image "$img"
for s in $seeds; do
  echo "== $(date +%T) $pre-s$s"
  python3 campaign.py one --id "$pre-s$s" --seed $s --name "$name" "$@" 2>&1 | python3 -c "
import sys,json; t=sys.stdin.read(); i=t.find('{')
try:
  r=json.loads(t[i:]); print({k:r.get(k) for k in ['fault_fired','viol_end','final_detail_id','next_use','next_use_all_ok','vid_after_next_use','wall_s']})
except Exception as e: print('ERR', t[-1500:])"
done
