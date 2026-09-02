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
checks that a finite fitness was persisted, and cleans up. It does not start a
multi-generation training run.

The reconstructed smoke configuration uses three capsules and a
`50 inputs -> 50 tanh -> 10 tanh -> 6 linear outputs` controller. The topology
comes from the recovered project notes and the input/output counts agree with
the trainer's structure generator. The original saved population and exact
training configuration were not recovered; oscillator settings and motor
ranges in this smoke configuration are therefore plausible reconstruction
choices, not a claim of exact historical reproduction.
