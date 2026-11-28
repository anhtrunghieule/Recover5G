#!/bin/bash
# Campaign 2: regenerate every CSV / decoded-pcap summary under results/real/campaign2 from the raw JSONL and pcaps.
set -u
cd "$(dirname "$0")/.."
R=../results/real/campaign2
export DOCKER_CONTEXT=${DOCKER_CONTEXT:-colima-recover5g}
python3 c2/analyze_c2.py $R/F7_c2.csv $R/dup/F7.jsonl
python3 c2/analyze_c2.py $R/F5a_c2.csv $R/f5a/F5a.jsonl
python3 c2/analyze_c2.py $R/a4audit_c2.csv $R/a4/a4audit.jsonl
python3 c2/analyze_c2.py $R/phase_c2.csv $R/phase/phase.jsonl
python3 c2/analyze_c2.py $R/amf_rerun_c2.csv $R/amf/amf_rerun_p2.jsonl $R/amf/amf_rerun_p1.jsonl
python3 c2/analyze_c2.py $R/boundary_c2.csv $(ls $R/boundary/boundary_c2*.jsonl | grep -v errors)
python3 c2/boundary_summary.py $R/boundary_c2.csv > $R/boundary/boundary_summary.txt
python3 c2/alias_eval.py >/dev/null
python3 c2/replication.py >/dev/null
python3 c2/phase_eval.py >/dev/null
for f in $R/a4/pcap/*.pcap.gz $R/dup/pcap/*.pcap.gz $R/f4/pcap/*.pcap.gz $R/f5a/pcap/*.pcap.gz $R/lazy/pcap/*.pcap.gz $R/amf/pcap/F5B*.pcap.gz; do
  [ -f "${f%.gz}.ids.json" ] || python3 c2/pcap_ids.py "$f" > /dev/null 2>&1
done
echo done
