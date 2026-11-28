# Issue-mining study: queries, protocol, and threats

**Run date:** 2026-11-05 (searches executed 2026-11-05/06 UTC via the authenticated GitHub REST search API, `gh api -X GET search/issues`).
**Scripts:** `artifact/scripts/mine_issues.py` (search + caching), `artifact/scripts/summarize_issues.py` (counts).
**Re-run:** `python3 mine_issues.py search` reuses the cached raw responses in `raw/` (delete `raw/search_*.json` to re-query live; counts will drift as issues are filed and closed).

## Repositories
open5gs/open5gs, free5gc/free5gc, openairinterface/oai-cn5g-{amf,smf,upf,fed}, omec-project/{upf,amf,smf}.
All 9 exist, are not archived, and have issues enabled (checked 2026-11-05). openairinterface/oai-cn5g-fed and omec-project/amf returned (almost) no relevant hits.
Note that OAI CN5G's primary tracker is GitLab (gitlab.eurecom.fr); only the GitHub mirrors' issue trackers were mined, so OAI is under-represented.

## Query construction
For every repository, one query per term group, prefixed with `repo:<r> is:issue` (issues only; pull requests excluded). Up to 3 pages x 100 results per query, ~2.2 s between calls (search API: 30 req/min).
Primary term groups (as specified): `restart`; `recovery OR restoration`; `heartbeat`; `"PFCP association" OR "association setup"`; `crash reconnect OR crash re-register`; `"pool exhausted" OR "IP is used" OR "already in use"`; `stale OR orphan OR leak`; `"Recovery Time Stamp" OR recoveryTime`; `"NF restart" OR "UPF restart" OR "SMF restart" OR "AMF restart" OR "gNB restart"`.
Supplementary term groups (added after the first pass to widen recall, tagged `supp_*`): `reboot OR rebooted OR killed`; `"goes down" OR "went down" OR "comes back" OR "came back"`; `"Error Indication"`; `"NG Reset" OR "SCTP reconnect" OR "SCTP association"`; `failover OR redundancy OR "high availability"`.
Caveat: GitHub search treats whitespace as AND with OR binding inside the group; `crash reconnect OR crash re-register` is therefore interpreted by GitHub's own precedence rules.

## Funnel
| Stage | Count |
|---|---:|
| Queries issued | 126 (81 primary + 45 supplementary) |
| Raw hits (sum of total_count, with overlap) | 1721 (1435 from primary terms) |
| Deduplicated candidate issues (`candidates.csv`) | 1086 |
| Bodies read and labeled (`labels_manual.csv`) | 146 |
| Included (`include=yes`) | 38 |
| Maybe (excluded from counts) | 16 |
| Excluded after reading body | 92 |

## Screening protocol
1. All 1086 candidates were passed through two automatic flags: (a) a regex pre-filter over title+body (code blocks and log lines stripped) for a restart/peer-failure phrase near an NF name (e.g. "after the UPF restart", "restart smf", "heartbeat timeout", "re-association", "Recovery Time Stamp", "session restoration", "stale/orphan ... session/context/IP"); (b) a title-keyword sweep (restart, recover, heartbeat, associat, reconnect, stale, orphan, leak, exhaust, reuse, ...), plus the top-200 issues by a coarse keyword score. The union of flagged issues (471) was screened manually by title; obviously out-of-scope titles (malformed-input/fuzzing crashes, build/config questions, feature requests, documentation) were dropped. The remaining ~615 unflagged candidates were **not** individually inspected (a recall threat). Helper scripts: `artifact/scripts/screening/{strong.py,screen.py,sweep2.py}` (scratch helpers; paths are hard-coded).
2. For the 146 remaining issues the body text (as returned by the search API and cached in `raw/search_*.json`; we read the first 400-900 characters with code blocks removed, and more where needed) was read and labeled.
3. **Inclusion:** the bug manifests after an NF/peer (AMF/SMF/UPF/NRF/PCF/UDM/UDR/gNB, or the EPC counterparts MME/SGW/PGW, or a peer endpoint signalling lost state via GTP-U Error Indication / NG Reset) restart, crash, heartbeat loss, unreachability/outage, association re-setup or restoration, AND it concerns cross-NF state (contexts, sessions, identifiers, allocations, associations, registrations) or convergence. **Exclusion:** build/config/usage questions, feature requests, docs, crashes on malformed or adversarial input without an NF failure (iFinder/fuzzing territory), and UE-only failures. When unsure: `maybe` (not counted).
4. Labels: `nf_restarted`, `root_cause` in {lost-allocation-state, identifier-reuse-aliasing, missing-cleanup-on-peer-failure, stale-restoration, unadvanced-recovery-timestamp, association-handling, other} (with `root_cause_detail` for `other`), `symptom` in {orphan, dangling, alias, leak-exhaustion, black-hole, non-convergence, crash} (primary) plus `secondary_symptom`, `interface`. Derived: `silent` = primary symptom in {orphan, dangling, alias, leak-exhaustion, black-hole} (NF stays up, no error at the time of corruption); `crash_only_oracle_detects` = primary symptom is `crash`; status `closed/completed` = GitHub `state_reason == completed` (a proxy for "fixed"; not verified against commits).
5. All motivating issues were hit by the searches and are labeled: Open5GS #4892, #4877, #4860, #4833, #4427; OAI SMF #33; OAI UPF #41; free5GC #1112, #1243 (no direct fetch was needed).

## Threats to validity
- **Single labeler.** One person (the author of this artifact) screened and labeled every issue; no inter-rater agreement was measured. Root-cause labels in particular are judgement calls made from issue text, not from code or fixes. A second labeler and Cohen's kappa are planned.
- **Body excerpts.** Most labels are based on the first several hundred characters of the body plus title; some issues may be mislabeled where the key detail is deeper in the thread or in attachments.
- **Recall.** Keyword search misses issues that never use the query terms; GitHub mirrors of OAI hold few issues; SD-Core issues are spread across many repos (only upf/amf/smf mined). The supplementary pass raised the candidate count from 972 to 1086 but contributed only 2 included issues (free5GC #216, Open5GS #1928), suggesting diminishing returns but not saturation.
- **Selection bias toward 2026.** 21 of 38 included issues were filed in 2026, a period in which tool-assisted reporters filed many detailed state bugs; this inflates recency and may reflect reporter behaviour rather than code quality.
- **EPC issues.** Open5GS ships EPC NFs; 5 included issues concern EPC (SGW/MME/PGW) restart/peer-failure state and are kept but marked `core_gen=EPC`.
- **Not reproduced.** No issue was reproduced for this study; labels describe the reports as written.

## Per-query hit counts
| repo | tag | total_count | retrieved | query |
|---|---|---:|---:|---|
| open5gs/open5gs | restart | 240 | 240 | `repo:open5gs/open5gs is:issue restart` |
| open5gs/open5gs | recovery | 47 | 47 | `repo:open5gs/open5gs is:issue recovery OR restoration` |
| open5gs/open5gs | heartbeat | 131 | 131 | `repo:open5gs/open5gs is:issue heartbeat` |
| open5gs/open5gs | pfcp_assoc | 62 | 62 | `repo:open5gs/open5gs is:issue "PFCP association" OR "association setup"` |
| open5gs/open5gs | crash_reconnect | 35 | 35 | `repo:open5gs/open5gs is:issue crash reconnect OR crash re-register` |
| open5gs/open5gs | pool | 92 | 92 | `repo:open5gs/open5gs is:issue "pool exhausted" OR "IP is used" OR "already in use"` |
| open5gs/open5gs | stale | 140 | 140 | `repo:open5gs/open5gs is:issue stale OR orphan OR leak` |
| open5gs/open5gs | recovery_ts | 9 | 9 | `repo:open5gs/open5gs is:issue "Recovery Time Stamp" OR recoveryTime` |
| open5gs/open5gs | nf_restart | 73 | 73 | `repo:open5gs/open5gs is:issue "NF restart" OR "UPF restart" OR "SMF restart" OR "AMF restart" OR "gNB restart"` |
| open5gs/open5gs | supp_reboot | 97 | 97 | `repo:open5gs/open5gs is:issue reboot OR rebooted OR killed` |
| open5gs/open5gs | supp_down | 28 | 28 | `repo:open5gs/open5gs is:issue "goes down" OR "went down" OR "comes back" OR "came back"` |
| open5gs/open5gs | supp_errind | 65 | 65 | `repo:open5gs/open5gs is:issue "Error Indication"` |
| open5gs/open5gs | supp_ngreset | 30 | 30 | `repo:open5gs/open5gs is:issue "NG Reset" OR "SCTP reconnect" OR "SCTP association"` |
| open5gs/open5gs | supp_failover | 11 | 11 | `repo:open5gs/open5gs is:issue failover OR redundancy OR "high availability"` |
| free5gc/free5gc | restart | 71 | 71 | `repo:free5gc/free5gc is:issue restart` |
| free5gc/free5gc | recovery | 81 | 81 | `repo:free5gc/free5gc is:issue recovery OR restoration` |
| free5gc/free5gc | heartbeat | 27 | 27 | `repo:free5gc/free5gc is:issue heartbeat` |
| free5gc/free5gc | pfcp_assoc | 69 | 69 | `repo:free5gc/free5gc is:issue "PFCP association" OR "association setup"` |
| free5gc/free5gc | crash_reconnect | 11 | 11 | `repo:free5gc/free5gc is:issue crash reconnect OR crash re-register` |
| free5gc/free5gc | pool | 18 | 18 | `repo:free5gc/free5gc is:issue "pool exhausted" OR "IP is used" OR "already in use"` |
| free5gc/free5gc | stale | 68 | 68 | `repo:free5gc/free5gc is:issue stale OR orphan OR leak` |
| free5gc/free5gc | recovery_ts | 4 | 4 | `repo:free5gc/free5gc is:issue "Recovery Time Stamp" OR recoveryTime` |
| free5gc/free5gc | nf_restart | 34 | 34 | `repo:free5gc/free5gc is:issue "NF restart" OR "UPF restart" OR "SMF restart" OR "AMF restart" OR "gNB restart"` |
| free5gc/free5gc | supp_reboot | 20 | 20 | `repo:free5gc/free5gc is:issue reboot OR rebooted OR killed` |
| free5gc/free5gc | supp_down | 4 | 4 | `repo:free5gc/free5gc is:issue "goes down" OR "went down" OR "comes back" OR "came back"` |
| free5gc/free5gc | supp_errind | 3 | 3 | `repo:free5gc/free5gc is:issue "Error Indication"` |
| free5gc/free5gc | supp_ngreset | 12 | 12 | `repo:free5gc/free5gc is:issue "NG Reset" OR "SCTP reconnect" OR "SCTP association"` |
| free5gc/free5gc | supp_failover | 1 | 1 | `repo:free5gc/free5gc is:issue failover OR redundancy OR "high availability"` |
| openairinterface/oai-cn5g-amf | restart | 6 | 6 | `repo:openairinterface/oai-cn5g-amf is:issue restart` |
| openairinterface/oai-cn5g-amf | recovery | 4 | 4 | `repo:openairinterface/oai-cn5g-amf is:issue recovery OR restoration` |
| openairinterface/oai-cn5g-amf | heartbeat | 0 | 0 | `repo:openairinterface/oai-cn5g-amf is:issue heartbeat` |
| openairinterface/oai-cn5g-amf | pfcp_assoc | 2 | 2 | `repo:openairinterface/oai-cn5g-amf is:issue "PFCP association" OR "association setup"` |
| openairinterface/oai-cn5g-amf | crash_reconnect | 1 | 1 | `repo:openairinterface/oai-cn5g-amf is:issue crash reconnect OR crash re-register` |
| openairinterface/oai-cn5g-amf | pool | 2 | 2 | `repo:openairinterface/oai-cn5g-amf is:issue "pool exhausted" OR "IP is used" OR "already in use"` |
| openairinterface/oai-cn5g-amf | stale | 3 | 3 | `repo:openairinterface/oai-cn5g-amf is:issue stale OR orphan OR leak` |
| openairinterface/oai-cn5g-amf | recovery_ts | 0 | 0 | `repo:openairinterface/oai-cn5g-amf is:issue "Recovery Time Stamp" OR recoveryTime` |
| openairinterface/oai-cn5g-amf | nf_restart | 4 | 4 | `repo:openairinterface/oai-cn5g-amf is:issue "NF restart" OR "UPF restart" OR "SMF restart" OR "AMF restart" OR "gNB restart"` |
| openairinterface/oai-cn5g-amf | supp_reboot | 0 | 0 | `repo:openairinterface/oai-cn5g-amf is:issue reboot OR rebooted OR killed` |
| openairinterface/oai-cn5g-amf | supp_down | 2 | 2 | `repo:openairinterface/oai-cn5g-amf is:issue "goes down" OR "went down" OR "comes back" OR "came back"` |
| openairinterface/oai-cn5g-amf | supp_errind | 3 | 3 | `repo:openairinterface/oai-cn5g-amf is:issue "Error Indication"` |
| openairinterface/oai-cn5g-amf | supp_ngreset | 5 | 5 | `repo:openairinterface/oai-cn5g-amf is:issue "NG Reset" OR "SCTP reconnect" OR "SCTP association"` |
| openairinterface/oai-cn5g-amf | supp_failover | 0 | 0 | `repo:openairinterface/oai-cn5g-amf is:issue failover OR redundancy OR "high availability"` |
| openairinterface/oai-cn5g-smf | restart | 2 | 2 | `repo:openairinterface/oai-cn5g-smf is:issue restart` |
| openairinterface/oai-cn5g-smf | recovery | 0 | 0 | `repo:openairinterface/oai-cn5g-smf is:issue recovery OR restoration` |
| openairinterface/oai-cn5g-smf | heartbeat | 1 | 1 | `repo:openairinterface/oai-cn5g-smf is:issue heartbeat` |
| openairinterface/oai-cn5g-smf | pfcp_assoc | 2 | 2 | `repo:openairinterface/oai-cn5g-smf is:issue "PFCP association" OR "association setup"` |
| openairinterface/oai-cn5g-smf | crash_reconnect | 0 | 0 | `repo:openairinterface/oai-cn5g-smf is:issue crash reconnect OR crash re-register` |
| openairinterface/oai-cn5g-smf | pool | 2 | 2 | `repo:openairinterface/oai-cn5g-smf is:issue "pool exhausted" OR "IP is used" OR "already in use"` |
| openairinterface/oai-cn5g-smf | stale | 5 | 5 | `repo:openairinterface/oai-cn5g-smf is:issue stale OR orphan OR leak` |
| openairinterface/oai-cn5g-smf | recovery_ts | 1 | 1 | `repo:openairinterface/oai-cn5g-smf is:issue "Recovery Time Stamp" OR recoveryTime` |
| openairinterface/oai-cn5g-smf | nf_restart | 1 | 1 | `repo:openairinterface/oai-cn5g-smf is:issue "NF restart" OR "UPF restart" OR "SMF restart" OR "AMF restart" OR "gNB restart"` |
| openairinterface/oai-cn5g-smf | supp_reboot | 0 | 0 | `repo:openairinterface/oai-cn5g-smf is:issue reboot OR rebooted OR killed` |
| openairinterface/oai-cn5g-smf | supp_down | 1 | 1 | `repo:openairinterface/oai-cn5g-smf is:issue "goes down" OR "went down" OR "comes back" OR "came back"` |
| openairinterface/oai-cn5g-smf | supp_errind | 0 | 0 | `repo:openairinterface/oai-cn5g-smf is:issue "Error Indication"` |
| openairinterface/oai-cn5g-smf | supp_ngreset | 0 | 0 | `repo:openairinterface/oai-cn5g-smf is:issue "NG Reset" OR "SCTP reconnect" OR "SCTP association"` |
| openairinterface/oai-cn5g-smf | supp_failover | 0 | 0 | `repo:openairinterface/oai-cn5g-smf is:issue failover OR redundancy OR "high availability"` |
| openairinterface/oai-cn5g-upf | restart | 9 | 9 | `repo:openairinterface/oai-cn5g-upf is:issue restart` |
| openairinterface/oai-cn5g-upf | recovery | 2 | 2 | `repo:openairinterface/oai-cn5g-upf is:issue recovery OR restoration` |
| openairinterface/oai-cn5g-upf | heartbeat | 2 | 2 | `repo:openairinterface/oai-cn5g-upf is:issue heartbeat` |
| openairinterface/oai-cn5g-upf | pfcp_assoc | 3 | 3 | `repo:openairinterface/oai-cn5g-upf is:issue "PFCP association" OR "association setup"` |
| openairinterface/oai-cn5g-upf | crash_reconnect | 0 | 0 | `repo:openairinterface/oai-cn5g-upf is:issue crash reconnect OR crash re-register` |
| openairinterface/oai-cn5g-upf | pool | 0 | 0 | `repo:openairinterface/oai-cn5g-upf is:issue "pool exhausted" OR "IP is used" OR "already in use"` |
| openairinterface/oai-cn5g-upf | stale | 9 | 9 | `repo:openairinterface/oai-cn5g-upf is:issue stale OR orphan OR leak` |
| openairinterface/oai-cn5g-upf | recovery_ts | 0 | 0 | `repo:openairinterface/oai-cn5g-upf is:issue "Recovery Time Stamp" OR recoveryTime` |
| openairinterface/oai-cn5g-upf | nf_restart | 8 | 8 | `repo:openairinterface/oai-cn5g-upf is:issue "NF restart" OR "UPF restart" OR "SMF restart" OR "AMF restart" OR "gNB restart"` |
| openairinterface/oai-cn5g-upf | supp_reboot | 1 | 1 | `repo:openairinterface/oai-cn5g-upf is:issue reboot OR rebooted OR killed` |
| openairinterface/oai-cn5g-upf | supp_down | 0 | 0 | `repo:openairinterface/oai-cn5g-upf is:issue "goes down" OR "went down" OR "comes back" OR "came back"` |
| openairinterface/oai-cn5g-upf | supp_errind | 1 | 1 | `repo:openairinterface/oai-cn5g-upf is:issue "Error Indication"` |
| openairinterface/oai-cn5g-upf | supp_ngreset | 0 | 0 | `repo:openairinterface/oai-cn5g-upf is:issue "NG Reset" OR "SCTP reconnect" OR "SCTP association"` |
| openairinterface/oai-cn5g-upf | supp_failover | 0 | 0 | `repo:openairinterface/oai-cn5g-upf is:issue failover OR redundancy OR "high availability"` |
| openairinterface/oai-cn5g-fed | restart | 0 | 0 | `repo:openairinterface/oai-cn5g-fed is:issue restart` |
| openairinterface/oai-cn5g-fed | recovery | 0 | 0 | `repo:openairinterface/oai-cn5g-fed is:issue recovery OR restoration` |
| openairinterface/oai-cn5g-fed | heartbeat | 0 | 0 | `repo:openairinterface/oai-cn5g-fed is:issue heartbeat` |
| openairinterface/oai-cn5g-fed | pfcp_assoc | 0 | 0 | `repo:openairinterface/oai-cn5g-fed is:issue "PFCP association" OR "association setup"` |
| openairinterface/oai-cn5g-fed | crash_reconnect | 0 | 0 | `repo:openairinterface/oai-cn5g-fed is:issue crash reconnect OR crash re-register` |
| openairinterface/oai-cn5g-fed | pool | 0 | 0 | `repo:openairinterface/oai-cn5g-fed is:issue "pool exhausted" OR "IP is used" OR "already in use"` |
| openairinterface/oai-cn5g-fed | stale | 1 | 1 | `repo:openairinterface/oai-cn5g-fed is:issue stale OR orphan OR leak` |
| openairinterface/oai-cn5g-fed | recovery_ts | 0 | 0 | `repo:openairinterface/oai-cn5g-fed is:issue "Recovery Time Stamp" OR recoveryTime` |
| openairinterface/oai-cn5g-fed | nf_restart | 0 | 0 | `repo:openairinterface/oai-cn5g-fed is:issue "NF restart" OR "UPF restart" OR "SMF restart" OR "AMF restart" OR "gNB restart"` |
| openairinterface/oai-cn5g-fed | supp_reboot | 0 | 0 | `repo:openairinterface/oai-cn5g-fed is:issue reboot OR rebooted OR killed` |
| openairinterface/oai-cn5g-fed | supp_down | 0 | 0 | `repo:openairinterface/oai-cn5g-fed is:issue "goes down" OR "went down" OR "comes back" OR "came back"` |
| openairinterface/oai-cn5g-fed | supp_errind | 0 | 0 | `repo:openairinterface/oai-cn5g-fed is:issue "Error Indication"` |
| openairinterface/oai-cn5g-fed | supp_ngreset | 0 | 0 | `repo:openairinterface/oai-cn5g-fed is:issue "NG Reset" OR "SCTP reconnect" OR "SCTP association"` |
| openairinterface/oai-cn5g-fed | supp_failover | 0 | 0 | `repo:openairinterface/oai-cn5g-fed is:issue failover OR redundancy OR "high availability"` |
| omec-project/upf | restart | 16 | 16 | `repo:omec-project/upf is:issue restart` |
| omec-project/upf | recovery | 11 | 11 | `repo:omec-project/upf is:issue recovery OR restoration` |
| omec-project/upf | heartbeat | 12 | 12 | `repo:omec-project/upf is:issue heartbeat` |
| omec-project/upf | pfcp_assoc | 15 | 15 | `repo:omec-project/upf is:issue "PFCP association" OR "association setup"` |
| omec-project/upf | crash_reconnect | 0 | 0 | `repo:omec-project/upf is:issue crash reconnect OR crash re-register` |
| omec-project/upf | pool | 3 | 3 | `repo:omec-project/upf is:issue "pool exhausted" OR "IP is used" OR "already in use"` |
| omec-project/upf | stale | 70 | 70 | `repo:omec-project/upf is:issue stale OR orphan OR leak` |
| omec-project/upf | recovery_ts | 2 | 2 | `repo:omec-project/upf is:issue "Recovery Time Stamp" OR recoveryTime` |
| omec-project/upf | nf_restart | 6 | 6 | `repo:omec-project/upf is:issue "NF restart" OR "UPF restart" OR "SMF restart" OR "AMF restart" OR "gNB restart"` |
| omec-project/upf | supp_reboot | 0 | 0 | `repo:omec-project/upf is:issue reboot OR rebooted OR killed` |
| omec-project/upf | supp_down | 0 | 0 | `repo:omec-project/upf is:issue "goes down" OR "went down" OR "comes back" OR "came back"` |
| omec-project/upf | supp_errind | 1 | 1 | `repo:omec-project/upf is:issue "Error Indication"` |
| omec-project/upf | supp_ngreset | 0 | 0 | `repo:omec-project/upf is:issue "NG Reset" OR "SCTP reconnect" OR "SCTP association"` |
| omec-project/upf | supp_failover | 0 | 0 | `repo:omec-project/upf is:issue failover OR redundancy OR "high availability"` |
| omec-project/amf | restart | 1 | 1 | `repo:omec-project/amf is:issue restart` |
| omec-project/amf | recovery | 0 | 0 | `repo:omec-project/amf is:issue recovery OR restoration` |
| omec-project/amf | heartbeat | 0 | 0 | `repo:omec-project/amf is:issue heartbeat` |
| omec-project/amf | pfcp_assoc | 0 | 0 | `repo:omec-project/amf is:issue "PFCP association" OR "association setup"` |
| omec-project/amf | crash_reconnect | 0 | 0 | `repo:omec-project/amf is:issue crash reconnect OR crash re-register` |
| omec-project/amf | pool | 0 | 0 | `repo:omec-project/amf is:issue "pool exhausted" OR "IP is used" OR "already in use"` |
| omec-project/amf | stale | 1 | 1 | `repo:omec-project/amf is:issue stale OR orphan OR leak` |
| omec-project/amf | recovery_ts | 0 | 0 | `repo:omec-project/amf is:issue "Recovery Time Stamp" OR recoveryTime` |
| omec-project/amf | nf_restart | 1 | 1 | `repo:omec-project/amf is:issue "NF restart" OR "UPF restart" OR "SMF restart" OR "AMF restart" OR "gNB restart"` |
| omec-project/amf | supp_reboot | 0 | 0 | `repo:omec-project/amf is:issue reboot OR rebooted OR killed` |
| omec-project/amf | supp_down | 0 | 0 | `repo:omec-project/amf is:issue "goes down" OR "went down" OR "comes back" OR "came back"` |
| omec-project/amf | supp_errind | 0 | 0 | `repo:omec-project/amf is:issue "Error Indication"` |
| omec-project/amf | supp_ngreset | 1 | 1 | `repo:omec-project/amf is:issue "NG Reset" OR "SCTP reconnect" OR "SCTP association"` |
| omec-project/amf | supp_failover | 0 | 0 | `repo:omec-project/amf is:issue failover OR redundancy OR "high availability"` |
| omec-project/smf | restart | 2 | 2 | `repo:omec-project/smf is:issue restart` |
| omec-project/smf | recovery | 2 | 2 | `repo:omec-project/smf is:issue recovery OR restoration` |
| omec-project/smf | heartbeat | 1 | 1 | `repo:omec-project/smf is:issue heartbeat` |
| omec-project/smf | pfcp_assoc | 3 | 3 | `repo:omec-project/smf is:issue "PFCP association" OR "association setup"` |
| omec-project/smf | crash_reconnect | 0 | 0 | `repo:omec-project/smf is:issue crash reconnect OR crash re-register` |
| omec-project/smf | pool | 0 | 0 | `repo:omec-project/smf is:issue "pool exhausted" OR "IP is used" OR "already in use"` |
| omec-project/smf | stale | 5 | 5 | `repo:omec-project/smf is:issue stale OR orphan OR leak` |
| omec-project/smf | recovery_ts | 0 | 0 | `repo:omec-project/smf is:issue "Recovery Time Stamp" OR recoveryTime` |
| omec-project/smf | nf_restart | 2 | 2 | `repo:omec-project/smf is:issue "NF restart" OR "UPF restart" OR "SMF restart" OR "AMF restart" OR "gNB restart"` |
| omec-project/smf | supp_reboot | 0 | 0 | `repo:omec-project/smf is:issue reboot OR rebooted OR killed` |
| omec-project/smf | supp_down | 0 | 0 | `repo:omec-project/smf is:issue "goes down" OR "went down" OR "comes back" OR "came back"` |
| omec-project/smf | supp_errind | 0 | 0 | `repo:omec-project/smf is:issue "Error Indication"` |
| omec-project/smf | supp_ngreset | 0 | 0 | `repo:omec-project/smf is:issue "NG Reset" OR "SCTP reconnect" OR "SCTP association"` |
| omec-project/smf | supp_failover | 0 | 0 | `repo:omec-project/smf is:issue failover OR redundancy OR "high availability"` |
