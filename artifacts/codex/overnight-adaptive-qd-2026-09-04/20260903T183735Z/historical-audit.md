# Historical audit

Audited source commit: `9ebf67add6087d7a6ae30764d1ee6e29b9608029`.

## Requested original-route improvement attribution

The six requested `bestFitnessEvaluation` values are present in the original-gravity progress history. None can be directly joined to a preserved `generatorType`, so attributing them to small mutation, large mutation, or random injection would be unsupported.

| Best-fitness evaluation | Robust best | Snapshot generation | Snapshot current evaluations | Direct generator attribution |
| ---: | ---: | ---: | ---: | --- |
| 44,750 | 2,263.045086 | 240 | 46,147 | Unsupported |
| 46,260 | 2,376.189101 | 251 | 48,378 | Unsupported |
| 49,473 | 2,383.531720 | 263 | 50,596 | Unsupported |
| 65,602 | 2,602.422252 | 345 | 66,393 | Unsupported |
| 129,370 | 2,638.065152 | 674 | 129,428 | Unsupported |
| 168,978 | 3,067.627554 | 888 | 170,687 | Unsupported |

Evidence searched directly:

- `review-data/three-route-snapshot-2026-09-03/plain/progress/original-gravity-100.progress.jsonl`
- `training-runs/me-v2-harmonic-qd-01-2h/trainer-phase-local-emitter.log`
- `training-runs/me-v2-harmonic-qd-01-2h/trainer.log`
- `training-runs/me-v2-harmonic-qd-01-2h/shellworker.log`
- byte-identical archived copies under `review-data/three-route-snapshot-2026-09-03/raw-snapshot/runs/original-gravity-100/`
- every file in `review-data/three-route-snapshot-2026-09-03/plain/prior-analysis/`

The phase-local trainer log preserves six explicit best events, all labeled `qd-mutate`, but none corresponds to the six requested evaluation IDs or robust-fitness values. The only exact overlap with the progress history is an earlier robust best of `1912.6542146445895`. `Trainer.py` stored an evaluation ID internally but its historical log line printed only generator type, fitness, and domain scores. Consequently, timing-based attribution is explicitly excluded.

## Comparable historical progress measurements

| Route | Progress records | Wall span | First finite robust best | Final robust best | Final best-eval/current-eval | Archive mean first to last | Final occupancy | Improvements after first | Accepted-evaluation plateau after final best |
| --- | ---: | --- | ---: | ---: | --- | --- | ---: | ---: | ---: |
| Gravity -100, population 192 | 322 | 09:33:46-12:51:21 UTC | 1,912.654 | 3,067.628 | 168,978 / 295,362 | 1,363.149 to 1,625.945 | 48 | 6 | 126,384 |
| Gravity -200, population 192 | 189 | 12:53:46-14:27:40 UTC | 1,059.432 | 1,520.297 | 91,248 / 214,542 | 742.952 to 1,062.445 | 33 | 9 | 123,294 |
| Gravity -200, population 384 | 385 | 14:32:50-17:45:36 UTC | 1,207.768 | 1,558.311 | 295,708 / 333,021 | 729.947 to 1,031.757 | 36 | 6 | 37,313 |

## Evidence limitations and mismatches

- The population-384 progress history reaches generation 867/evaluation 333,021, while `run-summary.json` is stale at generation 637/evaluation 244,929; the snapshot README flags this mismatch.
- The gravity -100 history is a resumed continuation beginning at generation 113/evaluation 21,884. Both gravity -200 histories are fresh populations.
- The gravity -100 configuration has random injection, large mutation, and large-mutation bounds that the gravity -200 configurations do not contain. Those routes therefore do not isolate gravity alone.
- Snapshots are approximately 30 seconds apart and include adjacent duplicate states. The gravity -100 series has pause gaps up to 2,047 seconds.
- The preserved original-route logs have a coverage gap: phase-local output ends with best 1,912.7; the later trainer log resumes already reporting best 3,067.6. The six requested improvements fall in this unlogged interval.
- Snapshot records lag their referenced best-fitness evaluation by 58 to 2,118 accepted evaluations. A snapshot timestamp is not an improvement timestamp.

This audit makes no optimizer recommendation; it establishes what the historical evidence can and cannot directly support.
