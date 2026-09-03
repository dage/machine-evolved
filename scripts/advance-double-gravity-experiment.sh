#!/usr/bin/env bash

# Advance the bounded double-gravity comparison without transferring a
# population between runs. Intended for the 15-minute Codex heartbeat.
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_dir=$(cd "$script_dir/.." && pwd)
source_run="me-v2-harmonic-qd-01-double-gravity-8w"
target_run="me-v2-harmonic-qd-01-double-gravity-double-population-8w"
source_dir="$repo_dir/training-runs/$source_run"
target_dir="$repo_dir/training-runs/$target_run"
target_config="$repo_dir/machine-evolved-trainer/configs/me-v2-harmonic-qd-01-double-gravity-double-population.json"
target_generation=1000
target_population=384
target_evaluations=$((target_generation * target_population))
workers=8

if [[ ! -f "$source_dir/config.json" ]]; then
  echo "WAIT: source checkpoint is not available: $source_dir/config.json"
  exit 0
fi

source_generation=$(jq -er '.algorithm.arguments.population.generation | tonumber' "$source_dir/config.json")
source_population=$(jq -er '.algorithm.arguments.population.size | tonumber' "$source_dir/config.json")
source_gravity=$(jq -er '.experiment.physics.gravityZ | tonumber' "$source_dir/config.json")
if [[ "$source_population" -ne 192 || "$source_gravity" -ne -200 ]]; then
  echo "BLOCKED: source run no longer matches the expected 192-member, -200 gravity experiment."
  exit 1
fi

target_running() {
  pgrep -f "scripts/run-training.sh.*--run-name $target_run" >/dev/null 2>&1
}

source_trainer_pids() {
  ps -ax -o pid= -o command= | awk -v config="$source_dir/config.json" \
    'index($0, "Trainer.py") && index($0, config) { print $1 }'
}

start_target() {
  if [[ -f "$target_dir/summary.json" ]]; then
    echo "DONE: independent doubled-population run completed: $target_dir"
    return
  fi
  if target_running; then
    echo "ACTIVE: independent doubled-population run is already running: $target_dir"
    return
  fi
  if [[ -e "$target_dir" ]]; then
    echo "BLOCKED: target run directory exists without an active launcher or completion summary: $target_dir"
    exit 1
  fi
  if [[ ! -f "$target_config" ]]; then
    echo "BLOCKED: target source config is missing: $target_config"
    exit 1
  fi

  (
    "$script_dir/run-training.sh" \
      --config "$target_config" \
      --evaluations "$target_evaluations" \
      --workers "$workers" \
      --seed 240903 \
      --run-name "$target_run" &
    runner_pid=$!
    for _ in $(seq 1 120); do
      [[ -f "$target_dir/config.json" ]] && break
      kill -0 "$runner_pid" 2>/dev/null || break
      sleep 1
    done
    if [[ -f "$target_dir/config.json" ]]; then
      python3 "$script_dir/capture-training-progress.py" \
        --config "$target_dir/config.json" \
        --output "$target_dir/progress.jsonl" \
        --summary "$target_dir/summary.json" \
        --interval-seconds 30 &
      capture_pid=$!
      wait "$runner_pid"
      wait "$capture_pid" || true
    else
      wait "$runner_pid"
    fi
  ) >"$repo_dir/training-runs/$target_run.launcher.log" 2>&1 &
  launcher_pid=$!

  for _ in $(seq 1 20); do
    if target_running && [[ -f "$target_dir/config.json" ]]; then
      echo "STARTED: fresh 384-member, -200 gravity run; capped at $target_generation generations ($target_evaluations evaluations): $target_dir"
      return
    fi
    kill -0 "$launcher_pid" 2>/dev/null || break
    sleep 1
  done
  echo "BLOCKED: target launcher exited before the new training run became ready; inspect $repo_dir/training-runs/$target_run.launcher.log"
  exit 1
}

if [[ "$source_generation" -lt "$target_generation" ]]; then
  echo "WAIT: source run is at generation $source_generation/$target_generation."
  exit 0
fi

if [[ ! -f "$source_dir/summary.json" ]]; then
  trainer_pids=$(source_trainer_pids || true)
  if [[ -z "$trainer_pids" ]]; then
    echo "BLOCKED: source is at generation $source_generation but no Trainer process or completion summary was found."
    exit 1
  fi
  echo "STOPPING: source run reached generation $source_generation; requesting its interrupt-safe checkpoint."
  while read -r trainer_pid; do
    [[ -n "$trainer_pid" ]] && kill -INT "$trainer_pid"
  done <<< "$trainer_pids"
  for _ in $(seq 1 300); do
    [[ -f "$source_dir/summary.json" ]] && break
    sleep 1
  done
fi

if [[ ! -f "$source_dir/summary.json" ]]; then
  echo "BLOCKED: source shutdown did not produce a completion summary within five minutes."
  exit 1
fi

start_target
