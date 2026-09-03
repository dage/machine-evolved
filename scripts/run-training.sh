#!/usr/bin/env bash

set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_dir=$(cd "$script_dir/.." && pwd)
build_dir="$repo_dir/build"
config=""
evaluations=""
minutes=""
workers=4
startup_seconds=120
seed=""
stall_evaluations=""
reset_fitness=false
resume_existing=false
run_name=""
trainer_pid=""
worker_pid=""
hard_deadline_epoch=""
deadline_signal_epoch=""

usage() {
  echo "Usage: $0 --config FILE (--evaluations N | --minutes N) [--workers N] [--startup-seconds N] [--seed N] [--stall-evaluations N] [--reset-fitness] [--resume-existing] [--run-name NAME]"
}

positive_integer() {
  [[ "$1" =~ ^[1-9][0-9]*$ ]]
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config) config=${2:-}; shift 2 ;;
    --evaluations) evaluations=${2:-}; shift 2 ;;
    --minutes) minutes=${2:-}; shift 2 ;;
    --workers) workers=${2:-}; shift 2 ;;
    --startup-seconds) startup_seconds=${2:-}; shift 2 ;;
    --seed) seed=${2:-}; shift 2 ;;
    --stall-evaluations) stall_evaluations=${2:-}; shift 2 ;;
    --reset-fitness) reset_fitness=true; shift ;;
    --resume-existing) resume_existing=true; shift ;;
    --run-name) run_name=${2:-}; shift 2 ;;
    --help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$config" || ! -f "$config" ]]; then
  echo "--config must identify an existing JSON file." >&2
  exit 2
fi
if [[ -n "$evaluations" ]] && ! positive_integer "$evaluations"; then
  echo "--evaluations must be a positive integer." >&2
  exit 2
fi
if [[ -n "$minutes" && ! "$minutes" =~ ^([0-9]+([.][0-9]*)?|[.][0-9]+)$ ]]; then
  echo "--minutes must be a positive number." >&2
  exit 2
fi
if [[ -n "$minutes" ]] && ! awk -v value="$minutes" 'BEGIN { exit !(value > 0) }'; then
  echo "--minutes must be greater than zero." >&2
  exit 2
fi
if [[ -z "$evaluations" && -z "$minutes" ]]; then
  echo "Either --evaluations or --minutes is required." >&2
  exit 2
fi
if [[ -n "$evaluations" && -n "$minutes" ]]; then
  echo "Use either --evaluations or --minutes, not both." >&2
  exit 2
fi
if ! positive_integer "$workers"; then
  echo "--workers must be a positive integer." >&2
  exit 2
fi
if ! positive_integer "$startup_seconds"; then
  echo "--startup-seconds must be a positive integer." >&2
  exit 2
fi
if [[ -n "$seed" && ! "$seed" =~ ^[0-9]+$ ]]; then
  echo "--seed must be a non-negative integer." >&2
  exit 2
fi
if [[ -n "$stall_evaluations" ]] && ! positive_integer "$stall_evaluations"; then
  echo "--stall-evaluations must be a positive integer." >&2
  exit 2
fi
if [[ -z "$run_name" ]]; then
  config_stem=$(basename "$config" .json)
  run_name="${config_stem}-$(date -u +%Y%m%dT%H%M%SZ)"
fi
if [[ ! "$run_name" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "--run-name may contain only letters, digits, dots, underscores, and dashes." >&2
  exit 2
fi

run_dir="$repo_dir/training-runs/$run_name"
if [[ -e "$run_dir" ]]; then
  if [[ "$resume_existing" != true ]]; then
    echo "Run directory already exists: $run_dir" >&2
    exit 2
  fi
  if [[ -f "$run_dir/summary.json" ]]; then
    echo "Training run is already complete: $run_dir"
    exit 0
  fi
  if [[ ! -f "$run_dir/config.json" ]]; then
    echo "Cannot resume because the run checkpoint is missing: $run_dir/config.json" >&2
    exit 2
  fi
  config="$run_dir/config.json"
fi

cleanup() {
  status=$?
  trap - EXIT
  if [[ -n "$trainer_pid" ]] && kill -0 "$trainer_pid" 2>/dev/null; then
    kill -TERM "$trainer_pid" 2>/dev/null || true
    wait "$trainer_pid" 2>/dev/null || true
  fi
  if [[ -n "$worker_pid" ]] && kill -0 "$worker_pid" 2>/dev/null; then
    kill "$worker_pid" 2>/dev/null || true
    wait "$worker_pid" 2>/dev/null || true
  fi
  if [[ $status -ne 0 ]]; then
    echo "Training run failed; retained diagnostics in $run_dir" >&2
  fi
  exit "$status"
}
trap cleanup EXIT

cmake -S "$repo_dir" -B "$build_dir" -DCMAKE_BUILD_TYPE=Release
cmake --build "$build_dir" --target shellworker --parallel

python3 -c 'import socket, sys
try:
    with socket.create_connection(("127.0.0.1", 9999), timeout=0.2):
        sys.exit("TCP port 9999 is already in use")
except OSError:
    pass'

if [[ ! -e "$run_dir" ]]; then
  mkdir -p "$run_dir"
  cp "$config" "$run_dir/config.json"
fi

trainer_args=(
  python3 -u "$repo_dir/machine-evolved-trainer/Trainer.py"
)
if [[ -n "$evaluations" ]]; then
  trainer_args+=(--terminate-evaluations "$evaluations")
fi
if [[ -n "$minutes" ]]; then
  requested_duration_seconds=$(awk -v value="$minutes" 'BEGIN { printf "%.0f", value * 60 }')
  deadline_file="$run_dir/deadline-epoch"
  if [[ "$resume_existing" == true && -f "$deadline_file" ]]; then
    hard_deadline_epoch=$(tr -d '[:space:]' < "$deadline_file")
    if [[ ! "$hard_deadline_epoch" =~ ^[0-9]+$ ]]; then
      echo "Invalid saved deadline: $deadline_file" >&2
      exit 2
    fi
  else
    hard_deadline_epoch=$(( $(date +%s) + requested_duration_seconds ))
    printf '%s\n' "$hard_deadline_epoch" > "$deadline_file"
  fi
  remaining_seconds=$((hard_deadline_epoch - $(date +%s)))
  if [[ "$remaining_seconds" -lt 1 ]]; then
    remaining_seconds=1
  fi
  duration_seconds=$(printf '%s.000' "$remaining_seconds")
  trainer_args+=(--terminate-seconds "$duration_seconds")
fi
if [[ -n "$stall_evaluations" ]]; then
  trainer_args+=(--terminate-stall-evaluations "$stall_evaluations")
fi
if [[ -n "$seed" ]]; then
  trainer_args+=(--seed "$seed")
fi
if [[ "$reset_fitness" == true ]]; then
  trainer_args+=(--reset-fitness)
fi
trainer_args+=("$run_dir/config.json")

"${trainer_args[@]}" >"$run_dir/trainer.log" 2>&1 &
trainer_pid=$!
if [[ -n "$minutes" ]]; then
  hard_deadline_epoch=$((hard_deadline_epoch + 30))
fi

python3 -c 'import json, os, socket, sys, time
trainer_pid = int(sys.argv[1])
startup_seconds = int(sys.argv[2])
deadline = time.time() + startup_seconds
while time.time() < deadline:
    try:
        os.kill(trainer_pid, 0)
    except ProcessLookupError:
        sys.exit("trainer exited before becoming ready")
    try:
        with socket.create_connection(("127.0.0.1", 9999), timeout=0.2) as connection:
            connection.sendall(b"{\"type\":\"PING\"}")
            response = json.loads(connection.recv(4096).decode("utf-8"))
            if response.get("response") == "PING":
                sys.exit(0)
    except (OSError, json.JSONDecodeError):
        time.sleep(0.05)
sys.exit(f"trainer did not become ready within {startup_seconds} seconds")' "$trainer_pid" "$startup_seconds"

if ! kill -0 "$trainer_pid" 2>/dev/null; then
  wait "$trainer_pid"
fi

"$build_dir/shellworker" --threads "$workers" >"$run_dir/shellworker.log" 2>&1 &
worker_pid=$!

while kill -0 "$trainer_pid" 2>/dev/null && kill -0 "$worker_pid" 2>/dev/null; do
  if [[ -n "$hard_deadline_epoch" ]]; then
    now_epoch=$(date +%s)
    if [[ -z "$deadline_signal_epoch" && "$now_epoch" -ge "$hard_deadline_epoch" ]]; then
      echo "Trainer exceeded the wall-clock deadline plus grace period; requesting an interrupt-safe checkpoint." >&2
      kill -INT "$trainer_pid" 2>/dev/null || true
      deadline_signal_epoch=$now_epoch
    elif [[ -n "$deadline_signal_epoch" && "$now_epoch" -ge $((deadline_signal_epoch + 15)) ]]; then
      echo "Trainer did not exit after SIGINT; sending SIGTERM." >&2
      kill -TERM "$trainer_pid" 2>/dev/null || true
    fi
  fi
  sleep 0.1
done

if ! kill -0 "$worker_pid" 2>/dev/null && kill -0 "$trainer_pid" 2>/dev/null; then
  set +e
  wait "$worker_pid"
  worker_status=$?
  set -e
  worker_pid=""
  # A clean worker exits as soon as the trainer starts shutting down, while
  # the trainer may still be atomically writing a large final checkpoint.
  # Give that normal lifecycle a bounded grace period before calling it a
  # worker failure.
  trainer_exit_deadline=$((SECONDS + 10))
  while kill -0 "$trainer_pid" 2>/dev/null && [[ "$SECONDS" -lt "$trainer_exit_deadline" ]]; do
    sleep 0.1
  done
  if kill -0 "$trainer_pid" 2>/dev/null; then
    echo "ShellWorker exited with status $worker_status while the trainer was still running." >&2
    exit 1
  fi
fi

wait "$trainer_pid"
trainer_pid=""
if [[ -n "$worker_pid" ]]; then
  worker_exit_deadline=$((SECONDS + 20))
  while kill -0 "$worker_pid" 2>/dev/null && [[ "$SECONDS" -lt "$worker_exit_deadline" ]]; do
    sleep 0.1
  done
  if kill -0 "$worker_pid" 2>/dev/null; then
    echo "ShellWorker did not exit within 20 seconds of trainer shutdown; sending SIGTERM." >&2
    kill -TERM "$worker_pid" 2>/dev/null || true
  fi
  wait "$worker_pid" || true
  worker_pid=""
fi

python3 "$script_dir/summarize-training.py" \
  --config "$run_dir/config.json" \
  --output "$run_dir/summary.json" \
  --workers "$workers"

echo "Training run complete: $run_dir"
