# Overnight training supervisor

`scripts/overnight_supervisor.py` is the host-level guard for a bounded,
unattended Machine Evolved run. It does not choose optimization routes. An
orchestrator supplies those routes by atomically replacing the configured queue
file with schema 1 JSON shaped like `ops/overnight-routes.example.json`.

The first supervisor start creates an immutable `epoch.json` containing both
wall-clock and monotonic T0 values and their ten-hour deadlines. A supplied
`t0EpochSeconds` and `t0MonotonicSeconds` can preserve an already-started
experiment's exact anchors; omitted, they are derived at supervisor startup.
Later launchd restarts reuse that record and
cannot extend the deadline. The supervisor holds
an exclusive advisory lock, refuses an unrelated listener on TCP 9999, records
process identities before signaling them, and requires one ShellWorker process
whose command line declares exactly eight threads. It never uses `pgrep`, a
process-name-wide kill, or an unrecorded process group signal.

Every cycle atomically replaces `orchestrator-state.json`; the example uses a
five-second cycle and values above sixty seconds are rejected. A durable JSONL
heartbeat is appended at most sixty seconds after the preceding heartbeat. The
state reports process liveness, checkpoint evaluation/generation progress,
evaluation throughput, queue depth, aggregate owned-process CPU, free disk,
checkpoint age, power source, port ownership, and worker verification.
It also appends a compact `metrics.jsonl` sample every thirty seconds with the
evaluation/domain counts, throughput, available QD archive metrics, liveness,
eight-worker confirmation, CPU, disk, checkpoint age, and remaining deadline.
`qdScore` is the sum of all finite occupied-cell fitnesses.
`normalizedQdScore` has one stable definition: `qdScore / (occupiedCells *
bestFitness)` when the archive is non-empty and `bestFitness > 0`; otherwise it
is null. The same sample includes occupied-cell top-5 and top-12 means plus each
morphology's occupied count, best fitness, and QD sum.

After three minutes without an accepted evaluation, the supervisor sends SIGINT
only to a recorded Trainer identity, allows the configured checkpoint grace,
and then terminates only still-matching recorded identities. A restart passes
`--resume-existing` and the route's persisted original evaluation cap. Failed
attempt logs are never reused, and Trainer/ShellWorker logs are copied into the
attempt archive before a resume. Three consecutive crashes inside the rapid
crash window abandon the route and prioritize its declared safe fallback.
A route declared with `safeFallback: true, enabled: false` is skipped in normal
queue order but may be started when an abandoned route explicitly selects it;
the preference remains durable through temporary port or input waits.

When a verified route reaches its evaluation cap and Trainer and ShellWorker
exit, the supervisor allows a bounded launcher-only interval for summary
generation instead of misclassifying the normal drain as a runtime failure.
Zombie launchers are excluded from liveness and reaped when they remain direct
children, allowing the persisted summary to complete the route without signals.

At the hard deadline, or before pausing an active route because AC power was
lost, the same bounded checkpoint shutdown runs. No new route starts after the
deadline. If `pmset` reports Battery Power—or the power source cannot be safely
identified while `requireACPower` is enabled—the supervisor records a waiting
state and does not begin sustained training.

To prepare a real run without starting it:

1. Copy the two example JSON files without the `.example` suffix and replace the
   example route queue with the orchestrator's reviewed phases and absolute caps.
2. Copy the plist example into `~/Library/LaunchAgents`, after reviewing every
   path. Do not load it until the queue, disk threshold, and ten-hour duration
   are approved.
3. Validate the configuration observationally with
   `python3 scripts/overnight_supervisor.py --config ops/overnight-supervisor.json --once`.
   Once mode acquires the lock and writes state, but never launches or signals a
   training process.

launchd executes `scripts/run-overnight-supervisor.sh`, which keeps the
supervisor awake with `caffeinate -i`. Runtime state stays in ignored
`training-runs/`; the committed examples cannot start until explicitly copied to
the non-example filenames referenced by the plist.

The example uses `ProcessType=Interactive` because the supervised evaluator is
explicitly user-requested compute and must not inherit launchd's Background CPU
and I/O limits. Use Background only for genuinely opportunistic jobs where
reduced compute scheduling is intended. Each training route is additionally
launched through `/usr/sbin/taskpolicy -a`, which applies the resource-management
policy used for normal applications to the runner and its Trainer/ShellWorker
children.
