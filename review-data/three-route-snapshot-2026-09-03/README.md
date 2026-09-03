# Machine Evolved: three-route review snapshot

This package is an immutable data snapshot prepared for an external GitHub reviewer. It covers the three directly comparable harmonic MAP-Elites routes below, including their complete saved run directories, raw progress histories, terminal trainer states, worker/trainer logs, and prior analysis artifacts relevant to the original route.

The repository at this branch supplies the corresponding source code, training launch scripts, committed configuration templates, tests, and Git history. The snapshot archive preserves ignored, generated run state that Git would otherwise omit.

## Plain-text review set (no archive extraction required)

Use this first if the reviewing environment cannot unpack `tar.xz`. It is 738,682 bytes of ordinary Git files:

- `run-summary.json` — static configuration for all three routes plus the first archive snapshot's terminal records.
- `plain/progress/` — the complete, uncompressed `progress.jsonl` history for every route. The 384-population file was refreshed at 2026-09-03T17:45:36Z (generation 867 / 333,021 evaluations); the other two are stopped.
- `plain/prior-analysis/` — the original-run ledger, result records, attempt manifest, motion analyses, and robustness record.
- `plain/runtime-notes/double-gravity-192-worker-shutdown-tail.log` — the relevant tail from the stopped 192-population route. It records workers losing the trainer connection after that route was terminated.

All static physics, objective, domain, seed, mutation, archive, and population settings are present directly in `run-summary.json`. The archive is only needed for full mutable trainer state, all worker/trainer logs, phase-local checkpoint data, and full replay traces.

## Snapshot identity

- Captured: 2026-09-03T16:57:06Z
- Source revision at capture: `288c031621aa2c0f43b97e02a73d207ee1c123cd`
- Archive: `three-route-raw-snapshot.tar.xz`
- Archive SHA-256: `f20a2c912c8525ac319f3b9a55e3d4c199b1cc8bf4ea74788197e3f6249ef3d3`
- Archive size: 5,829,548 bytes
- Archive members: 39 files

The 384-population route was still running when this snapshot was made. Its data is therefore a frozen partial record, not a terminal result. The two other routes were stopped before the snapshot.

## Routes and why each was started

| ID | Change under test | Independence and status at snapshot |
| --- | --- | --- |
| `original-gravity-100` | Baseline: `gravityZ=-100`, population 192, harmonic MAP-Elites. It began as the two-hour run and was later continued open-ended because it had recently improved. | Stopped at generation 1,538 / 295,362 evaluations. |
| `double-gravity-200-population-192` | Gravity-only comparison: `gravityZ=-200` while retaining the baseline population, seed, objective, Bullet settings, domains, and training profile. | Independent fresh population; stopped at generation 1,117 / 214,542 evaluations. |
| `double-gravity-200-population-384` | Population-size comparison: retain the double-gravity configuration and double population from 192 to 384. | Independent fresh population, no population/controller transfer; running at generation 637 / 244,929 evaluations. The evaluation cap was set to 384,000, corresponding to 1,000 population-sized generations. |

All three use Bullet v2, the three-capsule controller/morphology family, the `max-horizontal-distance-v1` objective, 60 Hz control, 120 Hz physics, three robustness domains (nominal/slick/rough), and `half-min-plus-geometric-mean-v1` aggregation. Fitness is stored in centimetres; presentation charts divide by 100 to show metres.

## Contents

```text
three-route-raw-snapshot.tar.xz  full frozen source records
run-summary.json                  compact machine-readable configuration and final progress records
README.md                         this index
```

The archive expands to `raw-snapshot/`:

- `runs/original-gravity-100/`
- `runs/double-gravity-200-population-192/`
- `runs/double-gravity-200-population-384/`
- `prior-analysis/` — original run ledger, prior retrospective, canonical replay and movement trace, robustness/motion analyses, and the current three-route chart.
- `SNAPSHOT-METADATA.tsv` — source path, byte count, and source modification time for every archived file.

The three run directories each contain their full saved `config.json` (including terminal trainer state and archive), `progress.jsonl`, plus trainer and ShellWorker logs. The original also includes its earlier phase-local-emitter checkpoint/progress and pause summaries.

## Verify and inspect

```sh
cd review-data/three-route-snapshot-2026-09-03
shasum -a 256 three-route-raw-snapshot.tar.xz
tar -tJf three-route-raw-snapshot.tar.xz
mkdir extracted
tar -xJf three-route-raw-snapshot.tar.xz -C extracted
```

The calculated SHA-256 must equal the value in “Snapshot identity.” The archive is intentionally not a live feed: use the repository's current ignored `training-runs/` only when evaluating the state after this snapshot.

## Requested external evaluation

Please audit the three routes before proposing any implementation change:

1. Check that the comparisons are fair, state any confounders, and distinguish population-size effects from run-duration/evaluation-budget effects.
2. Analyse the full best and mean progress histories, including plateau/recent-improvement behavior, archive occupancy, per-morphology records, and robustness-domain implications.
3. Inspect the saved best-controller/replay evidence and the objective/physics implementation for reward-hacking or numerical-physics failure modes.
4. Review the training code and configuration for the smallest credible system change that could improve exploration or locomotion quality.
5. Recommend one bounded next experiment (one to two hours): exact changed variables, unchanged controls, fresh-vs-transfer decision, seed policy, population, stop rule, and acceptance measurements.

Do not treat this index as evidence of a successful next direction. The raw records and the current branch are the sources of truth; explicitly mark inferences versus directly observed measurements.
