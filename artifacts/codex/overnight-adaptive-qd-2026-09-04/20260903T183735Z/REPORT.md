# Machine Evolved overnight adaptive-QD experiment

Status: **complete**. The supervisor reached the immutable hard deadline without extending it; all final claims below use only accepted evidence.

## Experiment identity

- Experiment: `overnight-adaptive-qd-2026-09-04`
- Branch: `codex/overnight-adaptive-qd-2026-09-04`
- Required starting commit: `9ebf67add6087d7a6ae30764d1ee6e29b9608029`
- T0: `2026-09-03T18:37:35Z`
- Hard deadline: `2026-09-04T04:37:35Z`
- Machine: Apple M3 Pro, 5 performance cores, 6 efficiency cores, 19.3 GB RAM
- Training policy: exactly eight evaluator workers, LaunchAgent `ProcessType=Interactive`, training launched with `taskpolicy -a`, live processes explicitly moved out of Darwin background priority with `taskpolicy -B`

The macOS “App Background Activity” classification identifies the persistent LaunchAgent lifecycle. It is not evidence that the evaluator is confined to efficiency cores. Sustained aggregate usage of the owned evaluator process group at about 759–806% CPU exceeds the six efficiency cores' aggregate capacity and therefore proves performance-core participation. macOS provides no supported hard performance-core affinity API, so eight runnable workers may also use available efficiency cores.

## Frozen primary contract

All primary optimizer comparisons use gravity -100, population 192, `max-horizontal-distance-v1`, 3,600 ticks, 60 Hz control, 120 Hz physics, 20 solver iterations, the existing target-angle servo, three existing morphologies, nominal/slick/rough domains, `half-min-plus-geometric-mean-v1`, and the existing 8x8 airborne-fraction/rotation-participation archive. No primary route changes physics, morphology, controller architecture, descriptors, objective, or training room.

## Measurements: historical audit

The strongest preserved historical -100 archive ended at 295,362 candidate evaluations and 886,123 domain simulations. Its best robust fitness was 3,067.627554 at evaluation 168,978; 48 archive cells were occupied. The source record is directly readable at `review-data/three-route-snapshot-2026-09-03/raw-snapshot/runs/original-gravity-100/config.json`; all snapshot files are bound by `review-data/three-route-snapshot-2026-09-03/raw-snapshot/SHA256SUMS` (manifest SHA-256 `e23f2a4e219054d0bf1103f3ec56e4e49c42f6a9c412cbbda997b6813f52fbdb`).

Historical generator attribution was audited from the archived trainer records and is recorded in `historical-audit.md`.

## Code changes

- Added config-gated four-arm sliding-window UCB selection. Old configs retain their fixed route.
- Added raw QD score and insertion/outcome/emitter telemetry with checkpoint-resumable selector state.
- Added deterministic comparison reports by candidate evaluations, domain simulations, and measurement wall time.
- Hardened supervisor cap validation, checkpoint recovery, process/port ownership, immutable attempt retention, final metric capture, clean completion classification, and automatic removal of Darwin background priority from every newly observed owned process identity.
- Added deterministic replay selection and jump-aware validation summaries.
- Added opt-in isolated single-domain population robustness preparation, candidate-ID-bound result attribution, and exact replay export. Legacy behavior remains unchanged; seven focused regressions pass.

## Measurements: matched development screening

All routes used the same 55,000-candidate cap and exact byte-matched starting banks. Accepted best and top-five values below exclude selected replay candidates failing the frozen jump-aware motion gate.

| Bank | Route | Candidates | Domain simulations | Accepted best | Accepted top-5 mean | Final QD | Candidate-evaluation QD AUC | Replay parity | Motion pass | Rolling signatures |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 240903 | fixed mixed | 55,004 | 165,045 | 2,687.130 | 2,505.403 | 63,762.949 | 3,041,176,254.513 | 12/12 | 10/12 | 0 |
| 240903 | small only | 55,004 | 165,064 | 2,235.717 | 1,964.532 | 43,305.259 | 2,088,393,232.935 | 12/12 | 10/12 | 0 |
| 240903 | adaptive four-arm | 55,001 | 165,019 | 2,638.357 | 2,352.350 | 61,346.723 | 2,890,909,353.795 | 12/12 | 10/12 | 0 |
| 240904 | adaptive four-arm | 55,001 | 165,079 | 2,619.601 | 2,338.580 | 64,837.788 | 3,095,247,288.859 | 12/12 | 10/12 | 0 |
| 240904 | small only | 55,002 | 165,051 | 1,943.029 | 1,859.594 | 47,771.450 | 2,316,116,292.362 | 12/12 | 11/12 | 0 |
| 240904 | fixed mixed | 55,001 | 165,027 | 2,599.049 | 2,491.529 | 66,611.777 | 3,115,536,134.215 | 12/12 | 10/12 | 0 |

Small-only was eliminated. Fixed mixed remained the reference; adaptive four-arm was retained as the strongest challenger for longer matched runs.

## Measurements: successive halving

| Bank | Route | Candidates | Domain simulations | Accepted best | Accepted top-5 mean | Final QD | Candidate-evaluation QD AUC | Replay parity | Motion pass | Rolling signatures |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 240905 | fixed mixed | 90,010 | 270,050 | 2,670.840 | 2,437.787 | 66,542.192 | 5,260,514,853.176 | 12/12 | 9/12 | 0 |
| 240905 | adaptive four-arm | 90,004 | 270,046 | 2,891.743 | 2,595.790 | 64,650.207 | 5,014,974,289.101 | 12/12 | 11/12 | 0 |
| 240906 | adaptive four-arm | 90,006 | 270,055 | 2,805.755 | 2,406.926 | 60,461.429 | 4,829,288,906.300 | 12/12 | 11/12 | 0 |
| 240906 | fixed mixed | 90,005 | 270,033 | 2,538.878 | 2,501.152 | 65,009.695 | 5,157,072,006.702 | 12/12 | 11/12 | 0 |

On bank 240905, adaptive changed accepted best by +8.271%, final QD by -2.843%, candidate-evaluation QD AUC by -4.668%, accepted top-five mean by +6.481%, and the accepted champion's worst-domain score by +2.800% relative to fixed. On bank 240906 the corresponding changes were +10.512%, -6.996%, -6.356%, -3.767%, and +11.020%. The median accepted-best gain was +9.391%, but adaptive crossed the predeclared 5% paired-regression limit for both final QD and QD AUC on bank 240906. It therefore did not replace fixed mixed for exploitation.

## Calculations and promotion rule

Development routes are ranked lexicographically by accepted validated best, final raw QD, candidate-evaluation QD AUC, accepted top-five mean, worst domain, coverage, insertion efficiency, throughput, and reliability. A challenger advances only with a median gain of at least 5% in accepted best or QD AUC, no paired regression above 5% in the other primary metric, and no material robustness or replay regression.

## Measurements: historical-archive exploitation

The preserved historical archive was copied to new run directories; no historical checkpoint was overwritten.

| Block | Policy | End candidates | Domain simulations | Measured block wall time | Accepted best | Accepted top-5 mean | Final QD | Occupied cells | Motion pass |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | fixed mixed | 350,000 | 1,050,070 | 1,131.730 s | 3,067.628 | 2,697.482 | 79,215.844 | 48 | 10/12 |
| 2 | fixed mixed | 400,001 | 1,200,026 | 1,009.595 s | 3,067.628 | 2,697.482 | 79,532.589 | 48 | 11/12 |
| 3 | adaptive four-arm | 450,001 | 1,350,043 | 1,042.124 s | 3,067.628 | 2,719.382 | 79,813.297 | 48 | 11/12 |

All three blocks had 12/12 nominal replay parity and zero rolling signatures. Block 1 increased QD by 1.500% from the inherited 78,045.382 without improving the champion. Block 2 added only 0.400% QD, no best, and no cell; this met the predeclared flatness condition and triggered the one permitted policy switch. Adaptive block 3 added 0.353% QD and 0.812% accepted top-five mean, again without improving the champion or coverage. Exploitation therefore stopped without another hypothesis switch.

## Unseen holdout ring

The frozen isolated cases are nominal, gravity -99, gravity -101, capsule mass scale 0.000099, capsule mass scale 0.000101, friction 0.6, and friction 1.0. Friction cases change ground and capsule friction together. Each case evaluates the same ordered top twelve exploitation candidates in one domain with mutation and crossover disabled.

The first seven completed evaluator runs were rejected for analysis because the original summarizer read the evolved final archive rather than the original selected candidates. No scores from that pass were used. The corrected route joins each selected `creatureId` to its first immutable evaluation-history result. The rerun reproduced all 84 configured scores within the validator's absolute `1e-4` / relative `1e-8` parity tolerance, and none exhibited the rolling signature. Retention in the case table divides every candidate's perturbed score by that same candidate's nominal holdout score; the per-candidate `worstCaseRetention` fields instead divide by training robust fitness and are deliberately a different quantity.

| Case | Motion-valid candidates | Median score retention | Mean score retention | Below 50% retention |
| --- | ---: | ---: | ---: | ---: |
| nominal | 11/12 | 1.000 baseline | 1.000 baseline | 0/12 |
| gravity -99 | 6/12 | 58.247% | 64.128% | 4/12 |
| gravity -101 | 4/12 | 39.894% | 41.300% | 9/12 |
| mass -1% | 8/12 | 55.184% | 58.533% | 5/12 |
| mass +1% | 10/12 | 66.869% | 76.603% | 2/12 |
| friction 0.6 | 5/12 | 44.305% | 46.419% | 9/12 |
| friction 1.0 | 5/12 | 44.752% | 54.725% | 7/12 |

The fastest historical controller retained only 22.174% in its worst case. The best absolute worst-case alternative was selected candidate 6, controller-data SHA-256 `835d8e8f3e9644d2e8a461597a5fb5838dd27ac85f8015a99e0342cf7be78536`: baseline robust fitness 2,521.580, worst holdout score 1,287.669, mean holdout score 1,960.789, and worst-case retention 51.066%. Gravity was frozen as the extra R5 training-room variable because gravity -101 caused the lowest median retention and nine of twelve candidates lost more than half their score.

## Measurements: R3 versus R5 development-room comparison

Fixed mixed was run from the new immutable bank 240909. R3 used 50,005 candidates and R5 used 30,003 so total domain simulations and measured wall time were matched to normal in-flight overshoot (168 simulations and 0.331 seconds apart). Development-table motion pass is the 12-candidate jump-aware selection validation; room holdout motion pass is separately the 84 candidate-case credibility count.

| Room | Candidates | Domain simulations | Wall time | Accepted best | Accepted top-5 mean | Final QD | Domain-simulation QD AUC | Cells | Holdout motion pass | All-case motion-valid candidates |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| R3 | 50,005 | 150,026 | 1,025.563 s | 3,152.361 | 2,601.183 | 65,382.605 | 8,166,237,280.860 | 43 | 52/84 | 0/12 |
| R5 gravity | 30,003 | 150,194 | 1,025.232 s | 2,107.319 | 2,012.397 | 49,410.167 | 6,287,027,598.293 | 37 | 62/84 | 2/12 |

Relative to R3, R5 changed accepted best by -33.151%, accepted top-five mean by -22.635%, final QD by -24.429%, and domain-simulation QD AUC by -23.012%. All 168 holdout replays reproduced configured fitness within the validator tolerance and none matched the analysis-layer rolling signature. R5 nevertheless produced two candidates that passed the motion gate in every unseen case, versus none for R3. Its strongest all-case-valid candidate has controller-data SHA-256 `19e50be68fa6aeb52997522f69d47d9fb735667f40dcbcfa09f93bc9225f154c`, training robust fitness 2,016.907, worst holdout score 963.274, mean holdout score 1,856.208, and worst-case retention 47.760%.

This is not a development promotion: the search-performance regressions are large. It is a categorical robustness signal sufficient to freeze fixed-mixed/R5 as the provisional system for untouched confirmation against fixed-mixed/R3 on banks 240907 and 240908.

## Measurements: untouched confirmation

The first confirmation launch set was invalidated before use because its bank-derived configs omitted the fixed policy's random-injection and large-mutation fields. The completed invalid R3 route and partial invalid R5 route are preserved as diagnostic evidence but excluded from every comparison and conclusion. The corrected `confirm2-*` routes restarted from the original untouched banks, preserved the full ordered 192-candidate payload and Python RNG state byte-for-byte, and added the complete frozen fixed-mixture mutation block.

Corrected R3 and R5 routes used approximately 150,000 domain simulations per bank. Each completed in one attempt with exit code 0, 12/12 selected replay parity, 84/84 holdout replay parity, and zero analysis-layer rolling signatures.

| Bank | Room | Candidates | Domain simulations | Wall time | Accepted best | Accepted top-5 mean | Final QD | Domain-simulation QD AUC | Cells | Selection motion | Holdout motion | All-case-valid |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 240907 | R3 control | 50,010 | 150,080 | 1,083.379 s | 2,814.839 | 2,464.697 | 65,522.871 | 8,280,013,281.233 | 44 | 11/12 | 57/84 | 0/12 |
| 240907 | R5 proposed | 30,001 | 150,085 | 1,111.226 s | 1,957.506 | 1,906.429 | 51,081.618 | 6,583,571,003.921 | 43 | 10/12 | 53/84 | 2/12 |
| 240908 | R5 proposed | 30,001 | 150,089 | 1,090.344 s | 2,013.384 | 1,937.791 | 47,251.521 | 6,233,121,094.026 | 36 | 9/12 | 58/84 | 0/12 |
| 240908 | R3 control | 50,001 | 150,044 | 1,028.391 s | 2,800.465 | 2,637.899 | 64,089.997 | 8,163,903,439.013 | 39 | 12/12 | 60/84 | 1/12 |

`Selection motion` applies the frozen jump-aware gate to the twelve archive selections. `Holdout motion` applies the same numerical thresholds to seven unseen cases for each of twelve candidates. The raw R5 bank-240907 champion failed the motion gate, so its accepted best is the next valid candidate.

## Calculations: paired confirmation deltas

All percentages below are proposed R5 relative to same-bank R3. They are calculations from the measured table, not separate measurements.

| Bank | Accepted best | Top-5 mean | Winner worst training domain | Final QD | Domain-simulation QD AUC | Coverage |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 240907 | -30.458% | -22.651% | -32.016% | -22.040% | -20.488% | -2.273% |
| 240908 | -28.105% | -26.540% | -36.264% | -26.273% | -23.650% | -7.692% |

R3 processed 2,770 and 2,917 candidate evaluations per minute on the two banks, versus R5's 1,620 and 1,651, because each R5 candidate used five domains. Domain-simulation throughput was much closer: 8,312 and 8,754 per minute for R3 versus 8,104 and 8,259 for R5.

## Measurements: final holdout and selected controllers

The final confirmation holdout contains 336 ID-bound replays: four routes, twelve candidates, and seven isolated cases. All 336 reproduced configured fitness within absolute `1e-4` / relative `1e-8`; 228 passed the jump-aware motion gate and none matched the rolling signature. All-seven-case-valid candidate counts were R3 `0, 1` and R5 `2, 0` on banks 240907 and 240908 respectively.

The strongest validated creature found is the R3 development-bank-240909 champion:

- creature ID `dc2b008c-9505-432a-a253-29506560c59c`
- creature-data SHA-256 `a7d00ef9c5ad949fc9f166a7195306d25d7870d024caa88277d3d5f3f7b33e11`
- balanced morphology; robust training fitness `3,152.361459`
- training-domain scores `2,846.391357`, `3,229.344238`, and `4,499.776367`; worst `2,846.391357`
- nominal compact replay `2,846.391360`, maximum distance `28.464` replay display units, final/max ratio `0.932863`, root spin `8.756 rad/s`, no rolling signature, motion valid
- five of seven mild holdout cases motion valid; the controller is the fastest accepted result, not the robust selection

The robust alternative is R5 confirmation bank-240907 rank 4 / holdout index 3:

- creature ID `17621a5f-1a5d-459a-b2f4-d21300d18337`
- creature-data SHA-256 `d013013babc119ce4ba190fe6565fd1e164ce71dae0ffef289fbda992e97a6ae`
- R5 training robust fitness `1,912.052172`
- holdout scores: nominal `2,940.100342`, gravity -99 `2,734.832520`, gravity -101 `2,276.129150`, mass -1% `1,157.787598`, mass +1% `1,503.101196`, friction 0.6 `2,425.579102`, friction 1.0 `1,706.528931`
- worst holdout `1,157.787598`; mean holdout `2,106.294120`; worst/training-baseline retention `60.552%`
- seven of seven cases motion valid; no rolling signature

Both compact controllers produced byte-identical JSON in duplicate 20 Hz deterministic replays. Exact hashes are in `duplicate-replay-hashes.json`; complete numerical movement descriptions are in the two motion dossiers.

## Inferences and promotion decision

The proposed R5 gravity room does not beat fixed-mixed/R3. It fails both the non-negative paired-result requirement and the permitted below-3% regression allowance by large margins on every primary search metric. Its development all-case robustness signal was real but did not replicate consistently: two all-case-valid candidates appeared on one confirmation bank and none on the other. Fixed-mixed/R3 remains the training system.

The four-arm adaptive selector also does not earn promotion. It improved accepted best on both successive-halving banks, but regressed final QD and QD AUC beyond the predeclared 5% limit on bank 240906. The implementation remains config-gated and topology-independent; old configs retain the fixed path. No experiment-only optimizer or room change is made the default.

The fastest creature and robust alternative therefore come from different runs. This is not evidence that R5 is the better system; it is evidence that a broader room can occasionally find a useful robust controller while substantially reducing search performance under this budget.

## Failed hypotheses

- Small-only mutation was much worse than fixed mixed on both screening banks.
- Adaptive four-arm search raised accepted best but failed the paired QD regression gate.
- Continuing the historical archive for 154,639 actual additional candidates (approximately 150,000 nominal block budget) improved QD only 2.265% in total and never improved its champion; one allowed policy switch did not break the best-fitness plateau.
- R5 improved categorical robustness on the development bank but regressed search performance by 22–33%, then repeated 20–36% primary-metric regressions on both untouched banks.
- The first confirmation launch did not test the declared system because the route-generation step omitted two emitter rates and the large-mutation config; those outputs are invalid-attempt evidence only.

## Operational failures and recovery

- AC power was initially unavailable, so sustained training waited rather than violating the power constraint. A later disconnect caused a checkpointed pause with no bank-state loss.
- Early process-identity reconciliation and below-cap completion classification defects were fixed and regression-tested. The active route was recovered without a training restart.
- Two obsolete keepalive jobs from the earlier experiment repeatedly attempted to launch against occupied port 9999. They failed closed, were precisely removed, and did not evaluate candidates; wall-time comparisons retain any contention.
- The first population-holdout summarizer inspected the evolved final archive rather than original selected IDs. Those summaries were rejected, ID-bound evaluation-history joins and replay export were added with seven focused tests, and all seven cases were rerun.
- A read-only mechanical audit caught the invalid first confirmation configs. The active invalid route was checkpointed and stopped by its recorded PID, all four definitions were disabled, no evolved invalid checkpoint was reused, and corrected routes were rebuilt from untouched candidate/RNG banks. The invalid compute was 50,005 R3 candidates / 150,061 simulations plus 17,759 R5 candidates / 88,848 simulations.

None of these failures changed the immutable hard deadline.

## Measurements, calculations, and inference boundary

Measurements are the saved candidate/domain counters, wall timestamps, archive values, evaluator scores, replay trajectories, process state, and hashes. Calculations are QD sums, trapezoidal AUCs, percentage deltas, score retention, throughput, and holdout aggregations. Inferences are motion acceptance, robustness ranking, hypothesis rejection, and the promotion decision. Raw score alone never overrides replay parity or the frozen motion gate.

## Genericity limitations

The adaptive selector consumes only flat controller parameters/signature, morphology ID, fitness, behavior descriptors, archive outcomes, QD delta, and emitter identity; it does not inspect capsule count, order, root identity, template names, or snake topology. The existing motion and behavior-descriptor adapters still contain capsule-specific assumptions. Generalizing those adapters is separate work and was deliberately not mixed into this optimizer experiment.

## Remaining uncertainty

- Two untouched banks are enough to reject the large R5 regressions, but not enough to estimate the rare probability of finding an all-case-valid controller precisely.
- The fastest creature remains fragile to some one-variable perturbations and is not interchangeable with the robust alternative.
- Motion gates reject obvious numerical and rolling signatures but do not prove a gait is visually natural or game-ready.
- The snake is a disposable training-system probe; neither controller has been calibrated for a final Robby Creature Lab asset or Rapier transfer.

## Artifact verification

Required comparison charts, compact controllers, duplicate replay hashes, movement dossiers, corrected confirmation summaries, and final holdout evidence are present in this timestamped directory. Final regressions passed: 52 trainer, 31 script, and 31 supervisor tests, 114 total with zero failures. All 2,926 JSON files and five JSONL logs (1,724 nonblank records) parse; all required named outputs are nonempty and there are no zero-byte or task-owned temporary files.

At `2026-09-04T04:37:40.169203Z` the persisted supervisor state was `deadline_reached` with reason `hard_deadline`, no active route, no Trainer, no ShellWorker, and no port-9999 listener. The exact LaunchAgent was unloaded, its task-owned plist removed, and the orchestration heartbeat paused. The local evidence bundle contains 3,218 files and approximately 795.5 MiB. The narrow tracked payload is published on `codex/overnight-adaptive-qd-2026-09-04`; the massive run tree remains local and untracked as required.
