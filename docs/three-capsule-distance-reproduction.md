# Three-capsule distance reproduction

The recovered October 2017 experiment used a chain of three capsules, low
gravity, a six-output motor controller, and maximum horizontal displacement as
its fitness. The surviving video shows a population of 1000 with best fitness
4817.5 and average fitness 1937.9 after 754 evaluations. No saved population or
complete original JSON configuration was recovered.

## Calibrated bounded profile

`machine-evolved-trainer/configs/reproduction-three-capsule-distance-pilot.json`
records the reconstruction:

- Bullet 2.86, strict floating point, built without optional profiling;
- gravity `(0, 0, -100)`, ground friction `0.5`, motor force `5000`;
- 7200 fixed 60 Hz ticks, or 120 simulated seconds;
- three capsules and two joints, with all three rotational motors enabled;
- 50 inputs, then 50 tanh, 10 tanh, and 6 linear outputs;
- nine oscillators starting at `0.1` with multiplier `2`;
- joint limits from `-1*pi` to `1*pi` on each rotational axis;
- fitness equal to the maximum XY displacement from the starting center of
  mass, with no speed, direction, energy, balance, or survival penalty.

The gravity, motor force, horizon, network shape, capsule count, and historical
fitness target are grounded in recovered sources. Default friction is inferred.
The oscillator values, joint range, and genetic algorithm rates remain
calibrated hypotheses because the exact historical values were not preserved.

## Bounded evidence

All runs below used four worker threads and stopped automatically at 32 fitness
evaluations. The trainer was reset from the profile for each run.

| Profile | Seed | Best | Average | Observation |
| --- | ---: | ---: | ---: | --- |
| joint range `-0.5*pi..0.5*pi` | 1 | 2481.77 | 1178.35 | Did not reach the video target. |
| joint range `-1*pi..1*pi` | 1 | 21250.88 | 9433.77 | Crossed the historical target; randomized best was already 15177.11 and crossover improved it. |
| joint range `-1*pi..1*pi` | 2 | 34214.86 | 5838.56 | Independent seed also crossed the target. |

The calibrated profile therefore reproduces the intended high-distance
behavior and exceeds the historical captured fitness in two independent,
bounded runs. These values are Bullet simulation units, not meters.

## Running a bounded experiment

```sh
scripts/run-training.sh \
  --config machine-evolved-trainer/configs/reproduction-three-capsule-distance-pilot.json \
  --evaluations 32 \
  --workers 4 \
  --seed 1 \
  --run-name three-capsule-distance-seed-1
```

The runner refuses to share port 9999, builds the pinned worker, copies the
starting configuration into an ignored `training-runs/<run-name>/` directory,
and retains logs, the evolved population, and `summary.json`. It terminates the
worker and trainer after the requested evaluation count. Scaling to the
historical population of 1000 is intentionally a separate, user-approved run.
