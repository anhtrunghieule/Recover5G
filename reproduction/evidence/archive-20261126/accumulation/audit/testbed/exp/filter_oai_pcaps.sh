#!/bin/bash
# Drop the RF-simulator sample stream (TCP 4043 between OAI UE and gNB) from the OAI-run captures.
# Everything else (PFCP, SBI, NGAP, GTP-U) is kept. Originals are replaced; sizes are logged.
D="$1"; export DOCKER_CONTEXT=${DOCKER_CONTEXT:-colima-r5g-claude-ran}
for f in "$D"/*.pcap.gz; do
  b=$(basename "$f" .pcap.gz)
  [ -f "$D/$b.filtered" ] && continue
  before=$(stat -f %z "$f")
  docker run --rm -v "$D":/p r5g/open5gs:e85748e sh -c "gunzip -c /p/$b.pcap.gz | tcpdump -r - -w /p/$b.small.pcap 'not tcp port 4043' 2>/dev/null && gzip -f /p/$b.small.pcap" || { echo "FAILED $b"; continue; }
  mv "$D/$b.small.pcap.gz" "$f"; rm -f "$D/$b.pcap.ids.json" "$D/$b.pcap.gtp.json"; touch "$D/$b.filtered"
  echo "$b $before -> $(stat -f %z "$f") bytes"
done
