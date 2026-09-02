#!/usr/bin/env bash

set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_dir=$(cd "$script_dir/.." && pwd)
config=${1:-}
output=${2:-}
sample_hz=${3:-20}

if [[ -z "$config" || ! -f "$config" || -z "$output" ]]; then
  echo "Usage: $0 CONFIG_JSON OUTPUT_JSON [SAMPLE_HZ]" >&2
  exit 2
fi
if [[ ! "$sample_hz" =~ ^[1-9][0-9]*$ ]]; then
  echo "SAMPLE_HZ must be a positive integer." >&2
  exit 2
fi

cmake -S "$repo_dir" -B "$repo_dir/build" -DCMAKE_BUILD_TYPE=Release
cmake --build "$repo_dir/build" --target replayworker --parallel
"$repo_dir/build/replayworker" \
  --config "$config" \
  --output "$output" \
  --sample-hz "$sample_hz"

python3 - "$output" <<'PY'
import json
import math
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
with path.open() as source:
    replay = json.load(source)
assert replay["schemaVersion"] == 1
assert replay["kind"] == "machine-evolved-capsules-v1"
assert replay["fitnessParity"]["verified"] is True
assert math.isclose(
    replay["configuredFitness"],
    replay["measuredMaxDistanceSimulationUnits"],
    rel_tol=1e-7,
    abs_tol=1e-3,
)
assert len(replay["capsules"]) == 3
assert replay["samples"]
assert all(math.isfinite(value) for sample in replay["samples"] for pose in [
    sample["poses"]["body"], *sample["poses"]["parts"].values()
] for value in [
    *pose["translation"].values(), *pose["rotation"].values()
])
print(f"Replay validation passed: samples={len(replay['samples'])}, bytes={path.stat().st_size}")
PY
