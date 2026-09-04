# Machine Evolved overnight adaptive-QD experiment: data index

This file identifies the preserved data and records why experiment actions were taken. It does not provide an evaluation or recommendation.

## Experiment identity

- Experiment: `overnight-adaptive-qd-2026-09-04`
- Branch: `codex/overnight-adaptive-qd-2026-09-04`
- Required starting commit: `9ebf67add6087d7a6ae30764d1ee6e29b9608029`
- T0: `2026-09-03T18:37:35Z`
- Hard deadline: `2026-09-04T04:37:35Z`
- Machine: Apple M3 Pro, 5 performance cores, 6 efficiency cores, 19.3 GB RAM
- Evaluator workers: 8
- Process configuration: LaunchAgent `ProcessType=Interactive`, training launched with `taskpolicy -a`, observed owned processes moved out of Darwin background priority with `taskpolicy -B`
- Final supervisor state at `2026-09-04T04:37:40.169203Z`: `deadline_reached`, reason `hard_deadline`, no active route

## Frozen primary contract

Primary optimizer comparisons used gravity -100, population 192, `max-horizontal-distance-v1`, 3,600 ticks, 60 Hz control, 120 Hz physics, 20 solver iterations, the existing target-angle servo, three existing morphologies, nominal/slick/rough domains, `half-min-plus-geometric-mean-v1`, and the existing 8x8 airborne-fraction/rotation-participation archive.

## Historical input data

The preserved historical -100 archive ended at 295,362 candidate evaluations and 886,123 domain simulations. Its recorded best robust fitness was 3,067.627554 at evaluation 168,978; 48 archive cells were occupied.

- Historical snapshot: `review-data/three-route-snapshot-2026-09-03/raw-snapshot/`
- Snapshot checksums: `review-data/three-route-snapshot-2026-09-03/raw-snapshot/SHA256SUMS`
- Historical audit: `historical-audit.md`

## Action record and reasons

- Four mutation-policy routes were prepared to compare fixed mixed, small-only, adaptive four-arm, and historical-archive continuation while keeping the primary contract fixed.
- Screening used matched 55,000-candidate caps and byte-matched starting banks so policy was the varied factor.
- Small-only was not advanced after both screening banks recorded lower accepted-best, final-QD, and QD-AUC values than fixed mixed.
- Fixed mixed and adaptive four-arm were advanced to matched 90,000-candidate runs because their screening measurements were closer and the adaptive route recorded accepted-best gains on the screening banks.
- Fixed mixed was used for the first two historical-archive continuation blocks. The one permitted switch to adaptive four-arm occurred after block 2 met the predeclared flatness condition: no champion improvement, no new occupied cell, and 0.400% additional QD.
- Seven isolated holdout cases were run because the experiment plan required measurement under nominal, gravity, mass, and friction perturbations.
- The first holdout summaries were excluded and rerun because the original summarizer read the evolved final archive instead of the originally selected candidate IDs.
- Gravity was selected as the extra R5 room variable because gravity -101 had the lowest recorded median retention in the seven-case holdout and 9 of 12 candidates recorded less than 50% retention.
- R3 and R5 were compared at approximately matched domain-simulation counts and wall time because R5 evaluates five domains per candidate while R3 evaluates three.
- The first confirmation launch set was excluded because the generated configs omitted the fixed policy's random-injection and large-mutation fields. Corrected routes were rebuilt from the untouched candidate and RNG banks; no evolved invalid checkpoint was reused.
- The experiment stopped at the predeclared hard deadline.

## Matched development screening measurements

| Bank | Route | Candidates | Domain simulations | Motion-gated best | Motion-gated top-5 mean | Final QD | Candidate-evaluation QD AUC | Replay parity | Motion pass | Rolling signatures |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 240903 | fixed mixed | 55,004 | 165,045 | 2,687.130 | 2,505.403 | 63,762.949 | 3,041,176,254.513 | 12/12 | 10/12 | 0 |
| 240903 | small only | 55,004 | 165,064 | 2,235.717 | 1,964.532 | 43,305.259 | 2,088,393,232.935 | 12/12 | 10/12 | 0 |
| 240903 | adaptive four-arm | 55,001 | 165,019 | 2,638.357 | 2,352.350 | 61,346.723 | 2,890,909,353.795 | 12/12 | 10/12 | 0 |
| 240904 | adaptive four-arm | 55,001 | 165,079 | 2,619.601 | 2,338.580 | 64,837.788 | 3,095,247,288.859 | 12/12 | 10/12 | 0 |
| 240904 | small only | 55,002 | 165,051 | 1,943.029 | 1,859.594 | 47,771.450 | 2,316,116,292.362 | 12/12 | 11/12 | 0 |
| 240904 | fixed mixed | 55,001 | 165,027 | 2,599.049 | 2,491.529 | 66,611.777 | 3,115,536,134.215 | 12/12 | 10/12 | 0 |

## Successive-halving measurements

| Bank | Route | Candidates | Domain simulations | Motion-gated best | Motion-gated top-5 mean | Final QD | Candidate-evaluation QD AUC | Replay parity | Motion pass | Rolling signatures |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 240905 | fixed mixed | 90,010 | 270,050 | 2,670.840 | 2,437.787 | 66,542.192 | 5,260,514,853.176 | 12/12 | 9/12 | 0 |
| 240905 | adaptive four-arm | 90,004 | 270,046 | 2,891.743 | 2,595.790 | 64,650.207 | 5,014,974,289.101 | 12/12 | 11/12 | 0 |
| 240906 | adaptive four-arm | 90,006 | 270,055 | 2,805.755 | 2,406.926 | 60,461.429 | 4,829,288,906.300 | 12/12 | 11/12 | 0 |
| 240906 | fixed mixed | 90,005 | 270,033 | 2,538.878 | 2,501.152 | 65,009.695 | 5,157,072,006.702 | 12/12 | 11/12 | 0 |

## Historical-archive continuation measurements

| Block | Policy | End candidates | Domain simulations | Block wall time | Motion-gated best | Motion-gated top-5 mean | Final QD | Cells | Motion pass |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | fixed mixed | 350,000 | 1,050,070 | 1,131.730 s | 3,067.628 | 2,697.482 | 79,215.844 | 48 | 10/12 |
| 2 | fixed mixed | 400,001 | 1,200,026 | 1,009.595 s | 3,067.628 | 2,697.482 | 79,532.589 | 48 | 11/12 |
| 3 | adaptive four-arm | 450,001 | 1,350,043 | 1,042.124 s | 3,067.628 | 2,719.382 | 79,813.297 | 48 | 11/12 |

Each block recorded 12/12 nominal replay parity and zero rolling signatures.

## Untouched confirmation measurements

| Bank | Room | Candidates | Domain simulations | Wall time | Motion-gated best | Motion-gated top-5 mean | Final QD | Domain-simulation QD AUC | Cells | Selection motion | Holdout motion | All-case-valid |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 240907 | R3 control | 50,010 | 150,080 | 1,083.379 s | 2,814.839 | 2,464.697 | 65,522.871 | 8,280,013,281.233 | 44 | 11/12 | 57/84 | 0/12 |
| 240907 | R5 | 30,001 | 150,085 | 1,111.226 s | 1,957.506 | 1,906.429 | 51,081.618 | 6,583,571,003.921 | 43 | 10/12 | 53/84 | 2/12 |
| 240908 | R5 | 30,001 | 150,089 | 1,090.344 s | 2,013.384 | 1,937.791 | 47,251.521 | 6,233,121,094.026 | 36 | 9/12 | 58/84 | 0/12 |
| 240908 | R3 control | 50,001 | 150,044 | 1,028.391 s | 2,800.465 | 2,637.899 | 64,089.997 | 8,163,903,439.013 | 39 | 12/12 | 60/84 | 1/12 |

The final confirmation holdout contains 336 candidate-ID-bound replays: four routes, twelve candidates, and seven isolated cases. All 336 reproduced configured fitness within absolute `1e-4` / relative `1e-8`; 228 passed the recorded jump-aware numerical motion gate and zero matched the recorded rolling-signature predicate.

## Selected output artifacts

The experiment process exported two compact controllers and duplicate deterministic replays:

- `winner-controller.json`: route `room-R3-240909`, creature `dc2b008c-9505-432a-a253-29506560c59c`, recorded training robust fitness `3152.3614591203545`
- `robust-alternative-controller.json`: route `confirm2-R5-240907`, creature `17621a5f-1a5d-459a-b2f4-d21300d18337`, recorded training robust fitness `1912.052172269925`, recorded worst holdout fitness `1157.787598`, 7/7 recorded holdout motion passes
- Duplicate replay hashes: `duplicate-replay-hashes.json`
- Numerical movement data: `winner-motion-analysis.json`, `robust-alternative-motion-analysis.json`
- Text-form movement samples: `winner-motion-dossier.txt`, `robust-alternative-motion-dossier.txt`

These labels record the experiment process's selections. The underlying candidate, replay, metric, and holdout data are included for external evaluation.

## Raw-data locations

- Route definitions: `route-configs/`
- Route summaries: `route-summaries/` and `route-summary-index.json`
- Attempts, checkpoints, archives, evaluation histories, and trajectories: `attempts/`
- Immutable population banks and hashes: `population-banks/` and `population-bank-hashes.json`
- Development, baseline, and confirmation validations: `validations/` and `baseline-validation/`
- Holdout inputs and results: `holdouts/`, `holdout-results.json`, `final-holdout-results.json`, `room-holdout-R3-results.json`, `room-holdout-R5-results.json`
- Progress histories: `metrics.jsonl`, `manual-pre-fix-metrics.jsonl`, and attempt-level trainer logs/configs
- Action and failure records: `decisions.jsonl`, `failures.jsonl`, `heartbeats.jsonl`, `orchestrator-state.json`, `epoch.json`, `launchd.log`
- Comparisons: `comparisons/`, `comparison-by-evaluations.html`, `comparison-by-domain-simulations.html`, `comparison-by-wall-time.html`
- Deterministic final replays: `final-replays/`
- Complete-file checksums: `RAW-DATA-SHA256SUMS`

## Recorded failures and invalid data

- Early process-identity reconciliation and below-cap completion-classification defects were fixed. The active route was recovered from its checkpoint.
- Two obsolete keepalive jobs attempted to launch against occupied port 9999. They did not evaluate candidates and were removed.
- The first population-holdout summaries referenced evolved final archives rather than the original selected IDs. Those summaries were excluded; corrected candidate-ID-bound runs are preserved separately.
- The first confirmation configs omitted two emitter rates and the large-mutation configuration. The resulting completed R3 route and partial R5 route are preserved under their invalid-attempt status and were not reused by corrected confirmation routes.
- Recorded compute for those invalid confirmation attempts was 50,005 R3 candidates / 150,061 simulations plus 17,759 R5 candidates / 88,848 simulations.

## Verification record

- Final tests: 52 trainer, 31 script, and 31 supervisor tests; 114 passed and 0 failed.
- JSON parse audit: 2,926 files.
- JSONL parse audit: 5 files and 1,724 nonblank records.
- Required named outputs verified nonempty: 19.
- Recorded zero-byte files: 0.
- Recorded task-owned temporary directories: 0.
- At final closeout: LaunchAgent inactive, task-owned plist absent, orchestration heartbeat paused, port 9999 had no listener, Trainer process count 0, ShellWorker process count 0.

The complete preserved experiment tree is published as ordinary files on `codex/overnight-adaptive-qd-2026-09-04`. Compressed archives are not used in the current branch tree.
