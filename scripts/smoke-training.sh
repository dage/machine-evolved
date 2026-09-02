#!/usr/bin/env bash

set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_dir=$(cd "$script_dir/.." && pwd)
build_dir=${1:-"$repo_dir/build"}
worker_threads=${SMOKE_WORKER_THREADS:-1}
run_dir=$(mktemp -d "${TMPDIR:-/tmp}/machine-evolved-training-smoke.XXXXXX")
trainer_pid=""

cleanup() {
  status=$?
  trap - EXIT
  if [[ -n "$trainer_pid" ]] && kill -0 "$trainer_pid" 2>/dev/null; then
    kill "$trainer_pid" 2>/dev/null || true
    wait "$trainer_pid" 2>/dev/null || true
  fi
  if [[ $status -ne 0 ]]; then
    [[ -f "$run_dir/trainer.log" ]] && { echo "--- trainer.log ---"; sed -n '1,240p' "$run_dir/trainer.log"; }
    [[ -f "$run_dir/shellworker.log" ]] && { echo "--- shellworker.log ---"; sed -n '1,240p' "$run_dir/shellworker.log"; }
  fi
  find "$run_dir" -type f -delete 2>/dev/null || true
  rmdir "$run_dir" 2>/dev/null || true
  exit "$status"
}
trap cleanup EXIT

cmake -S "$repo_dir" -B "$build_dir" -DCMAKE_BUILD_TYPE=Release
cmake --build "$build_dir" --target shellworker replayworker --parallel

python3 -c 'import socket, sys
try:
    with socket.create_connection(("127.0.0.1", 9999), timeout=0.2):
        sys.exit("TCP port 9999 is already in use; refusing to attach the smoke worker to an unrelated trainer")
except OSError:
    pass'

cp "$repo_dir/machine-evolved-trainer/configs/smoke-three-capsule.json" "$run_dir/smoke.json"

python3 "$repo_dir/machine-evolved-trainer/Trainer.py" \
  --seed 1 \
  --terminate-evaluations 1 \
  "$run_dir/smoke.json" \
  >"$run_dir/trainer.log" 2>&1 &
trainer_pid=$!

python3 -c 'import json, socket, sys, time
deadline = time.time() + 10
while time.time() < deadline:
    try:
        with socket.create_connection(("127.0.0.1", 9999), timeout=0.2) as connection:
            connection.sendall(b"{\"type\":\"PING\"}")
            response = json.loads(connection.recv(4096).decode("utf-8"))
            if response.get("response") == "PING":
                sys.exit(0)
    except (OSError, json.JSONDecodeError):
        time.sleep(0.05)
sys.exit("trainer did not listen on 127.0.0.1:9999 within 10 seconds")'

if ! kill -0 "$trainer_pid" 2>/dev/null; then
  wait "$trainer_pid"
fi

"$build_dir/shellworker" --threads "$worker_threads" --max-creatures-per-worker 1 \
  >"$run_dir/shellworker.log" 2>&1

wait "$trainer_pid"
trainer_pid=""

python3 -c 'import json, math, sys
with open(sys.argv[1]) as source:
    config = json.load(source)
population = config["algorithm"]["arguments"]["population"]
evaluations = population["evaluations"]
creatures = config["structure"]["creatures"]
finite = [item["fitness"] for item in creatures if item["fitness"] is not None and math.isfinite(item["fitness"])]
missing = [item for item in creatures if item["fitness"] is None]
assert evaluations >= 1, population
if int(sys.argv[2]) == 1:
    assert evaluations == 1, population
assert len(finite) == evaluations, (finite, population)
assert len(missing) == len(creatures) - len(finite), len(missing)
assert len(creatures[0]["data"]["structure"]["capsules"]) == 3
print(f"Training smoke passed: evaluations={evaluations}, best_fitness={max(finite):.6f}")' "$run_dir/smoke.json" "$worker_threads"

"$repo_dir/scripts/export-replay.sh" "$run_dir/smoke.json" "$run_dir/replay.json" 20

if [[ "$worker_threads" == "1" ]]; then
  grep -F "Completed 1 evaluation." "$run_dir/shellworker.log" >/dev/null
else
  grep -E "Completed [1-9][0-9]* evaluations?\." "$run_dir/shellworker.log" >/dev/null
fi
grep -F "Exiting since max number of fitness evaluations has been performed." "$run_dir/trainer.log" >/dev/null

sed -n '1,160p' "$run_dir/shellworker.log"
sed -n '1,200p' "$run_dir/trainer.log"
