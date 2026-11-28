#!/bin/sh
# Regenerates every artifact output and the manuscript's generated/ files (round 3: campaign 2 integrated).
# REAL, static: issues (cached raw responses; delete raw/search_*.json to re-query live),
#   re-label agreement, reporter/fix/coverage extras, OAI GitLab mining (cached),
#   timers and source facts (raw files at pinned commits), per-fault Delta matrix,
#   reduction counts (analytic) and the two-UE cutoff model check.
# REAL, dynamic: results/real/ is written by the testbed harness (artifact/testbed/); render.py only reads it,
#   plus results/findings/findings_c2.csv (curated index: ids, wording, upstream status; reproduction counts are derived
#   by render_c2.py from results/real/campaign2/). results/findings/candidates.csv is the superseded campaign-1 index.
set -e
cd "$(dirname "$0")/scripts"
python3 summarize_issues.py
python3 relabel_kappa.py > /dev/null
python3 timer_facts.py > /dev/null
python3 compute_delta.py
python3 delta_matrix.py > /dev/null
python3 reduction.py > /dev/null
python3 cutoff_check.py > /dev/null
python3 render.py
