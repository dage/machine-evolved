# Machine Evolved two-hour final attempt

All fitness figures are authoritative raw simulation units. Values multiplied by `0.01` are scaled display units, not established SI metres.

| UTC time | Stage | Evidence or decision |
|---|---|---|
| 06:41 | Start | Adopted the corrected Pro plan. Preserve `machine-evolved-bullet-v1`, morphology, physics, 7,200 ticks, and raw maximum-distance objective. |
| 06:45 | Baseline freeze | The 8,192 run reached atomic checkpoint generation 109/evaluation 539,012 with best 119,876.359375 raw (1,198.764 display). |
| 06:46 | Stop-path finding | Direct SIGINT exposed a double-signal/final-save interruption in the wrapper. The preceding atomic checkpoint is intact; all trainer and worker processes stopped. |
| 06:47 | Replay parity | Two independent 60 Hz exports were byte-identical (`47a8d7f...`) and each reproduced fitness exactly. |
| 06:49 | Trainer correctness | Fixed tournament sentinels, protected elites, persisted/restored Python RNG and stall counters, and extended shutdown checkpoint grace from 15 to 120 seconds. Primary verification reached 23 unit tests plus smoke/replay checks. |
| 06:57–07:05 | Paired bakeoff | Two 5,000-evaluation seeds per lane compared legacy shared-offset mutation with independent offsets from the exact same champion. Shared results: 121,610.023438 and 122,526.125. Independent results: 122,192.421875 and 121,284.515625. Shared won both mean and maximum; independent was not promoted. |
| 07:05–07:09 | Winner exploitation | Continued the winning shared-offset seed with deterministic RNG resume. It stopped at evaluation 13,397 after the configured 10,000-evaluation no-improvement gate; best remained 122,526.125. |
| 07:10–07:24 | Bounded alternatives | Uniform versus log-uniform independent mutation, finer 1–9-parameter mutation, and elite-parent shared mutation all failed to beat 122,526.125. Each direction was stopped after its bounded canary or stall gate. |
| 07:26–07:28 | Directional search | The winning controller differs from the baseline in exactly 138/6,120 parameters, all by the same −0.163114978834 offset. Wide and zoomed deterministic line searches along that direction reproduced the peak but did not exceed it. |
| 07:28 | Final parity | Two final 60 Hz exports were byte-identical and reproduced configured fitness 122,526.125 exactly. A compact canonical champion config reproduced the same samples and metrics; only its intentional profile label differs. |
| 07:29–07:30 | Robustness ring | ±5% and ±1% paired gravity/mass perturbations plus paired friction changes substantially reduced distance. The speed champion is classified as exact-condition-only improvement, not robust improvement. |
| 07:35–07:36 | Robust alternative selection | Re-evaluated the top 64 nominal controllers under all six mild perturbations. Nominal rank 2 was strongest by absolute worst-case fitness: 121,637.1875 nominal, 60,058.480469 worst case, and 104,527.009766 perturbed mean. |

## Outcome

- Final best: **122,526.125 raw simulation units**, up 2,649.765625 or 2.2104% from the frozen 119,876.359375 baseline.
- Search compute: 65,439 trainer-accepted evaluations across 11 optimization runs, approximately 1,276.9 aggregate wall seconds by run-directory timestamps, always using six workers.
- Validation compute: 1,418 evaluations across two line searches, twelve single-champion physics cases, and six matched 64-controller robustness sweeps.
- Classification: **exact-condition-only improvement**. Exact replay is deterministic, but even small physics perturbations can collapse performance.
- Motion classification: near-ground rolling/spinning locomotion (99.40% near-ground time, 73.40 rad/s root spin, 0.99896 path efficiency). The legacy anti-spin credibility predicate is intentionally not an acceptance gate for this experiment.
- Robust alternative: nominal fitness 121,637.1875 (0.73% below the speed champion), but 49.38% worst-case retention across the mild six-case ring versus 18.92% for the speed champion. It is preserved separately; the faster exact-condition champion remains the active preview.
- Rank-ES was dropped rather than rushed: the corrected Pro plan made it optional only if implementation and testing fit a short timebox. The independently perturbed GA was implemented and tested first, and did not win the paired comparison.

Machine-readable per-run evidence, hashes, exact optimizer arguments, stop reasons, and timing proxies are in `two-hour-run-results.json`. The 8,192-population checkpoint remains untouched as the immutable fallback.

Next action: train for robustness explicitly (paired/domain-randomized physics during evaluation) before spending a day-scale budget. Do not continue the current exact-condition optimizer unchanged; it has demonstrated a 10,000-evaluation plateau and a narrow physics operating envelope.
