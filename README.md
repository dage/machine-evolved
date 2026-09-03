# machine-evolved

A machine learning project to create virtual creatures that can be used in Unreal Engine 4.

This was a massive side project from 2017-2018 where the general idea was to use Bullet physics engine for physics simulations, Unreal Engine 4 for rendering and interactivity, and this project for machine learning to control the virtual creatures by outputting a set of forces to apply to the creature's body parts.

After I stopped working on this, DeepMind and others released a bunch of papers and demos on similar projects, so I'm not sure how much of this is novel anymore, but I want to open source it under the MIT license in case anyone finds it interesting or useful and want to do something with it.

The project is poorly documented and quite frankly I don't remember how to reproduce the results, but I did find a video from my Snapchat My Story history that demonstrates what the system is capable of so I'm including it here as a quick reference (please ignore the Norwegian text 😅):

https://user-images.githubusercontent.com/765574/194573278-60a3de93-42d2-424e-b445-b9337d930554.mp4

## Headless training

The standalone `shellworker` runs the Bullet simulation and communicates with
the Python trainer without building Unreal Engine or the discarded TensorFlow
experiment. It requires CMake, a C++17 compiler, Python 3, and Boost headers.
CMake fetches the pinned Bullet source used by the worker build.

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --target shellworker --parallel
```

Run the bounded end-to-end smoke test with:

```sh
scripts/smoke-training.sh
```

The smoke test copies its configuration to a temporary directory, starts the
trainer, performs exactly one physics evaluation with one worker thread,
checks that a finite fitness was persisted, and cleans up. The fixed seed makes
the default single-worker result deterministic. It does not start a
multi-generation training run.

For a wall-clock-bounded run, use `--minutes` instead of `--evaluations`. The
runner sends the trainer a graceful interrupt at the deadline so its latest
population is saved before the worker exits:

```sh
scripts/run-training.sh \
  --config machine-evolved-trainer/configs/reproduction-three-capsule-distance-pilot.json \
  --minutes 30 \
  --workers 6 \
  --seed 3 \
  --run-name three-capsule-distance-seed-3-30m
```

The reconstructed smoke configuration uses three capsules and a
`50 inputs -> 50 tanh -> 10 tanh -> 6 linear outputs` controller. The topology
comes from the recovered project notes and the input/output counts agree with
the trainer's structure generator. The original saved population and exact
training configuration were not recovered; oscillator settings and motor
ranges in this smoke configuration are therefore plausible reconstruction
choices, not a claim of exact historical reproduction.

For the bounded historical-profile runner and the calibrated three-capsule
distance result, see
[`docs/three-capsule-distance-reproduction.md`](docs/three-capsule-distance-reproduction.md).
The calibrated pilot exceeded the recovered video's fitness target in two
independent seeds without starting a population-1000 training round.

## Compare training progress

Generate one self-contained chart from any two or more captured training runs:

```sh
scripts/compare-training-progress.py \
  --run 'Original gravity=training-runs/original-run' \
  --run 'Double gravity=training-runs/double-gravity-run' \
  --output artifacts/codex/training-comparison/current.html
```

Each run contributes a solid best-robust-fitness line and a dashed occupied-
population mean line. Re-running the command refreshes the output from the
latest valid sample in each `progress.jsonl` file.

`scripts/advance-double-gravity-experiment.sh` is the idempotent handoff used
by the 15-minute monitor for the current gravity comparison. It waits for the
192-member double-gravity run to reach generation 1,000, requests a checkpoint-
safe stop, then starts a fresh 384-member double-gravity run capped at 384,000
evaluations (1,000 MAP-Elites generations). It does not transfer any population
or checkpoint state between the runs.

## Browser replay export

`replayworker` replays the highest-fitness creature in a saved training config
with the same 60 Hz Bullet step order as `shellworker`. It writes sampled capsule
poses converted from the historical Z-up simulation units to Three.js Y-up
metres, together with the objective and physics metadata used by Creature Lab.

```sh
scripts/export-replay.sh \
  training-runs/calibrated-profile-v2-seed-1-e32/config.json \
  /path/to/best-replay.json \
  20
```

The exporter does not train or mutate the saved population. Its reported
measured distance should match the selected creature's saved fitness under the
strict floating-point build profile.
