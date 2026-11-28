# Recover5G minimum reproduction package

This package executes the **orphan-session case and its repair** using the patched UERANSIM recovery behavior, runs the frozen fresh-validation protocol, and replays the completed 630-run campaign and other retained traces. `RELEASE-MAP.md` identifies the inputs, commands, filters and limitations for each manuscript result. The original first campaign is incomplete. OAI/free5GC traces require their separately documented environments for new execution, and the missing delay-sensitive recipes remain unresolved.

The package includes exact arm64 runtime images and the cached source-build image in `images/arm64-runtime-and-build.tar.gz`. Image IDs and complete installed package versions are under `manifests/`. Open5GS is `e85748ef3d798fa0b4435c80438e81c41bbe5e13`. UERANSIM is `4f45e18f80b0684f7d6e29f1fea0f579e9243d68` with the retained UAC-wait and gNB recovery patches. The repair diff is in `build/repair/`. All subscriber credentials are published synthetic UERANSIM test values.

## Requirements

An arm64 Linux Docker engine with Compose, SCTP and `/dev/net/tun`, Python 3.10 or newer, and a shared absolute workspace path. On this Mac, Colima provides the engine. Use a dedicated profile. Do not use the existing `recover5g` or `recover5g-oai` profiles. Commands specify the context and never switch the global default.

```sh
colima start r5g-reproduction --arch aarch64 --vm-type vz --cpu 4 --memory 8 --disk 35 --activate=false
colima ssh -p r5g-reproduction -- sudo modprobe sctp
python3 reproduce.py verify
python3 reproduce.py load --context colima-r5g-reproduction
python3 reproduce.py analyze --context colima-r5g-reproduction
python3 reproduce.py reproduce --context colima-r5g-reproduction --runs 5 --instance 7
```

The examples use this directory. Absolute script paths also work from another directory. `analyze` and `reproduce` create a new timestamped output directory. Analysis needs the decoder image but makes no testbed changes. Reproduction resets only its selected instance in the dedicated context. Four arms run separately: baseline fault, repaired fault, baseline no-fault, repaired no-fault. Each fault kills the AMF, restores registration, creates new sessions and observes at 34 and 68 seconds. Raw attempts, captures, logs, identity readouts, image IDs, collection results and scored CSVs are retained. The driver fails if any harness attempt fails, rather than silently retrying to reach the requested sample count.

The expected retained pattern is working new service with two extra UPF sessions on the baseline, cleanup of the old identities with the repair, and clean no-fault controls. A differing outcome is evidence to investigate, not an instruction to discard a run. Check `orphan_eval.csv`, `orphan_summary.csv`, and `orphan_ref_summary.json`, including errors and denominators.

## Build and validate

```sh
python3 reproduce.py build-repair --context colima-r5g-reproduction
python3 -m unittest discover -s testbed/tests -v
```

The offline repair build uses the pinned cached source-build image, verifies `/COMMIT`, applies the included diff and builds the patched binary. This is not a new independent operating-system build. `testbed/docker/` retains the upstream-source Dockerfiles and RAN patches for a network-enabled rebuild. Those historical Dockerfiles use moving Ubuntu package mirrors, so they are **not** the exact dependency reproduction path. The image archive and package inventories provide that path.

The deployed readout entry points are `r5g/observe.py` and `r5g/oracle.py`. The new `r5g/verdict.py` interface distinguishes clean, violated, unknown and changing proxy observations. It keeps the ideal relation unknown for unobserved bindings and scopes next-use outcomes to the tested procedure. `c2/pcap_ids.py` decodes packet identities and fails on decoding errors. `exp/wire_truth.py` is the retained automated reference, sharing AMF/SMF inputs with the checker. It is not human adjudication or fully independent ground truth.

The repair is a diagnostic intervention. Successful replay does not certify all delayed PFCP response paths or production readiness. Repeated-recovery measurements, model results and historical audit inputs are frozen under `evidence/archive-20261126/`. Current replay outputs are in `evidence/release-outputs-20261126/`. Reports inside the input archive can predate campaign completion and must not replace the canonical outputs.

## Fresh validation and expert adjudication

The November 26 extension preserves `oracle.check_R` for legacy replay. `check_R_current`
fixes the address-leak rule to count every active session address when one UE has multiple
PSIs. Fresh validation uses this version and freezes its hash before collecting holdout
results. Comparisons on older captures are retrospective, not a new holdout.

Build the small guest-clock reader using the pinned build image:

```sh
python3 reproduce.py build-clock --context colima-r5g-reproduction
python3 reproduce.py validation-run --context colima-r5g-reproduction --instance 1 --part 0 --parts 1 --out /absolute/new/cohort
python3 reproduce.py validate-cohort --input /absolute/new/cohort --out /absolute/new/cohort-manifest.json
python3 reproduce.py compare-checkers --input /absolute/new/cohort --out /absolute/new/comparison
python3 reproduce.py export-expert --input /absolute/new/cohort --out /absolute/new/expert-packet --private /absolute/private/key
python3 reproduce.py score-expert --input /absolute/returned-labels.csv --packet /absolute/new/expert-packet --private /absolute/private/key --predictions /absolute/private/key/frozen-predictions.csv --out /absolute/new/expert-scores.json
```

Only distribute `expert-packet`. The private key and predictions must not go to the expert
before labeling. No messages are sent by these commands. Blank or partial labels remain
pending or partial. Natural and constructed evidence are scored separately.

`validation/protocol.json` fixes 72 fresh trials and a separate set of 24 constructed
cases. `constructed-cases --out /absolute/new/constructed` creates evidence examples,
not device measurements. A trial receives at most one replacement after a technical
failure, never after a valid scientific outcome. Retain both attempts.

Clock records bracket each collection with guest monotonic, boot and wall clocks plus
host timestamps and round-trip uncertainty. Sampling gaps over five seconds, clock
steps beyond 0.5 seconds plus measured transport uncertainty, guest restart, and
insufficient guest exposure invalidate timing. Those are conservative instrumentation
limits, not bounds on network scheduling. Complete clock sampling does not prove
continuous state consistency. Historical records without this evidence remain historical.

The fixed-window and recovery policies share observations but have different alert
rules. Early alerts, endpoint persistence and next-use service outcomes are reported
separately. A later successful use does not erase the earlier state inconsistency.

## Replaying the final release

```sh
python3 /absolute/package/replay_release.py --context CONTEXT --out /absolute/new/archival-replay
python3 /absolute/package/replay_validation.py --out /absolute/new/validation-replay
python3 /absolute/package/render_validation.py --input /absolute/package/evidence/validation-20261126/results --out /absolute/new/validation-table
python3 /absolute/package/check_reduction.py --input /absolute/package/evidence/validation-20261126/results --context CONTEXT --out /absolute/new/reduction-replay
```

The archive replay and signature reconstruction need the pinned decoder image. Fresh validation replay and table generation use retained records without a running testbed. These commands require new output directories and preserve the frozen evidence. Reconstructed decisions are automated results, not expert adjudication.
