#!/usr/bin/env bash

set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_dir=$(cd "$script_dir/.." && pwd)
config=${1:-"$repo_dir/ops/overnight-supervisor.json"}

# launchd supplies a deliberately small PATH.  The supervisor itself invokes
# system tools by absolute path; this PATH is retained for run-training.sh.
PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PATH

exec /usr/bin/caffeinate -i /usr/bin/python3 \
  "$script_dir/overnight_supervisor.py" --config "$config"
