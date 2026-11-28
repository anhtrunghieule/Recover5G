# Recover5G release map, 26 November 2026

The manuscript is centered on the observable checker and the controlled causal cases. Reduction counts remain conditional analysis. The same-conjunct outcomes in the placement campaign do not establish unique causal mechanisms or completeness.

All paths below are relative to this package. Run commands from any directory by passing the absolute path to `reproduce.py` or `replay_release.py`. Package SHA-256 values are in `manifests/files.json`. The retained-input inventory is `evidence/archive-20261126/release-inputs.json`. Replay always copies the evidence into a new output directory. It never rewrites frozen evidence.

| Main-paper evidence | Inputs | Reproduction path | Unit and limitation |
|---|---|---|---|
| Issue-study selection and taxonomy | `evidence/archive-20261126/issues-audit/data/` | Inspect selection trail and regenerate with `paper/gen_macros.py` in a replay copy | Issues. Original screening and unavailable labels remain unresolved. Agreement does not validate selection. |
| Candidate ledger and obligations | `evidence/archive-20261126/consistency/` | Inspect dated clauses, preconditions and tracker snapshots | Candidate mechanisms. A criterion is not automatically a mandatory standard obligation. |
| Orphan case and repair | `retained/orphan/`, `build/repair/`, image manifests | Fresh: `reproduce.py reproduce --timing-v2 --context CONTEXT --runs 1 --out NEW`. Replay: stage `orphan` | Fresh sessions and repair/control arms. The packaged build is pinned arm64. |
| Identity reference and seeded defects | `evidence/archive-20261126/results/raw/idref/` | `testbed/exp/idref_eval.py INPUT --out NEW --tag TAG` with explicit `IDREF_DOCKER_CONTEXT` | Automated reconstruction, source-derived rules. Not independent expert truth. |
| Main placement comparison | `evidence/archive-20261126/results/raw/main/` | Replay stage `main` | 630 fresh sessions on a shared host. Common labels are outcome classes, not verified mechanism identity. |
| Delay sensitivity | `evidence/archive-20261126/results/raw/timing/` | Replay stage `timing` | Matched schedules. Sleep-overlapping attempts excluded by the archived host-sleep audit. These legacy clocks do not gain the new guest-clock guarantee. |
| Accumulation and capacity | `evidence/archive-20261126/accumulation/results/`, `results/raw/impact/` | `accumulation/scripts/score_growth.py`, replay stage `impact` | Chain-level outcomes. The small-capacity experiment is not a production exhaustion forecast. |
| Cross-core next-use controls | `results/raw/free5gc/` inside the archive, `free5gc/gtp5g-v0.9.14.tar.gz` | Replay the retained `f5g_eval.py` result. A fresh cross-core environment needs its stated kernel and images. | Identity-resolved next use. Literal PSI removal is different because a new session can reuse the PSI. |
| Downtime convention | `historical-artifact/results/real/campaign2/phase/` inside the archive | Replay stage `heartbeat` | 29 retained runs. Direct event ordering is available. Exact crash-to-ready outage is unknown. |
| New timing-valid cohort and matched baselines | `validation/protocol.json`, `evidence/validation-20261126/results/` | Fresh: `reproduce.py validation-run`. Replay: `replay_validation.py --out NEW` | Per run. Invalid attempts retained. Fixed endpoints and conditional numeric chains are separate. |
| Blinded independent assessment | `evidence/validation-20261126/expert-packet/` and separate `expert-private/` | `export-expert`, then `score-expert` after returned decisions | Human decisions pending. Constructed evidence remains distinct from natural traces. |
| Controlled two-UE/one-UE reduction | `evidence/validation-20261126/results/repair-check-ues*` | `check_reduction.py --input EVIDENCE/results --context CONTEXT --out NEW` | One parameter reduction with resolved old identities, replacement, deletion and working-service checks. Original technical failures remain retained. |
| Multi-session rule regression | `evidence/validation-20261126/results/multisession-control/` | Fresh: `reproduce.py control-multisession --context CONTEXT --out NEW` | Two targeted known-defect controls, not an independent accuracy estimate. |

## Commands

```sh
python3 /absolute/package/reproduce.py verify
python3 /absolute/package/replay_release.py --context colima-r5g-reproduction --out /absolute/new/replay
```

The second command needs the pinned decoder image when a decode cache is missing. Use `reproduce.py load --context CONTEXT` to load the supplied images into a dedicated Docker context first. No command changes the default Docker context.

`evidence/release-outputs-20261126/` contains the canonical replay outputs used by the revised manuscript. Generated reports inside `archive-20261126/` are retained snapshots and may predate completed campaigns. Regenerate them with `replay_release.py` before treating them as current. The canonical macro files carry a per-value source map. `inventory_release.py --archive REPLAY/archive --out NEW.json` joins retained attempts to the headline selection rules, including pilots, sleep exclusions, replacements and the exact scored result. “Scored” there means included in an automated result, not independently adjudicated.

The archive's fields named `deadline_miss` or `miss1` retain their historical machine-readable names. In the main campaign they mean a discrepancy at the first fixed window. They are not evidence of a numeric deadline crossing. The gNB-abort sensitivity metric keeps every trial in its denominator and counts only persistent runs without an abort as events. It is not a conditional proportion among the non-abort subset.

To rebuild the fresh packet-activity guard, run `annotate_validation.py --input EVIDENCE/results/natural-combined --context CONTEXT --out NEW`, where EVIDENCE is `evidence/validation-20261126`. The guard uses packet activity, not reference verdicts. `replay_validation.py` replays the archived raw and guarded views and exports new blank expert packets. Send assessors only `expert-packet/`. Keep the separate prediction keys out of their assessment material. Do not fill human labels from scripts or expected construction outcomes.

Some historical reruns reused filenames. The JSONL attempt rows survive, but an earlier attempt's original capture may have been overwritten. The release manifest marks these cases. Fresh validation uses a unique capture path for each attempt.

The 1,489-snapshot historical readout audit is a different cohort from the sleep-filtered validation set. It must not be relabeled as current independent validation. Earlier ZIP snapshots and reports in the manuscript workspace predate the corrections in this release and remain historical records.

The fresh clock guard measures observation exposure and collection intervals. It does not prove continuous recovery. A collection overlapping a claimed threshold is uncertain. Missing identity mapping and untested next-use procedures remain unknown. The original unexplained deadline overrun remains unresolved.

Human setup, adjudication and maintenance time have not been measured. Automated command durations and summed machine time must not be presented as person-hours or total adoption cost.

To regenerate the fresh comparison table and its manuscript values, run `render_validation.py --input EVIDENCE/results --out NEW`. It emits the table, a per-method summary, identity-versus-recovery differences and `macros_validation.tex/json`. Table rows have different alert targets. Their totals are not an independently adjudicated accuracy ranking.

The fresh attempt manifest uses `scored` for inclusion in all five automated comparisons, including unknown outcomes. `expert_scored` remains zero until returned labels are adjudicated. Thus technical eligibility, automated inclusion and independent validation are separate statuses.

## Prospective version update

`build/maintenance/` pins Open5GS `5378c0698c604bd16e0287eadab069bc51e7fb5f`, 84 commits after the evaluated revision. The source tarball, Dockerfile and cached dependency versions accompany the release. Build in the dedicated context after loading the supplied base images:

```sh
docker --context CONTEXT build --network=none -t r5g/maintenance:5378c06 /absolute/package/build/maintenance
DOCKER_CONTEXT=CONTEXT R5G_INST=7 python3 /absolute/package/testbed/inst.py gen 7
DOCKER_CONTEXT=CONTEXT R5G_INST=7 R5G_OUT=/absolute/new/maintenance UERANSIM_IMAGE=r5g/ueransim:4f45e18-p2 python3 /absolute/package/testbed/exp/orphan_repl.py --tag maintenance-control --image r5g/maintenance:5378c06 --fault none --runs 1 --timing-v2
DOCKER_CONTEXT=CONTEXT R5G_INST=7 R5G_OUT=/absolute/new/maintenance UERANSIM_IMAGE=r5g/ueransim:4f45e18-p2 python3 /absolute/package/testbed/exp/orphan_repl.py --tag maintenance-amf --image r5g/maintenance:5378c06 --fault amf --runs 1 --timing-v2
```

The two distinct tags append separate attempts in one new result directory. The guest-clock binary must first be built with `reproduce.py build-clock`. `results/maintenance/installed-provenance.json` in the fresh evidence records the built image ID, installed commit and NF binary hashes. Automated build and execution durations are in `results/followup-effort.json`. These narrow compatibility controls do not validate all triggers or timer paths. Human porting and diagnosis time remain unmeasured.
