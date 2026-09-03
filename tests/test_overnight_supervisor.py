import importlib.util
import json
import signal
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "overnight_supervisor.py"
SPEC = importlib.util.spec_from_file_location("overnight_supervisor", MODULE_PATH)
SUPERVISOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SUPERVISOR)


class FakeSystem:
    def __init__(self):
        self.now = 1_000.25
        self.monotonic_now = 500.5
        self.power = "ac"
        self.process_table = []
        self.listeners = []
        self.spawned = []
        self.signals = []
        self.polled = []
        self.next_pid = 100
        self.exit_codes = {}

    def epoch(self):
        return self.now

    def monotonic(self):
        return self.monotonic_now

    def sleep(self, seconds):
        self.advance(seconds)

    def advance(self, seconds):
        self.now += seconds
        self.monotonic_now += seconds

    def boot_id(self):
        return "test-boot"

    def power_source(self):
        return self.power

    def processes(self):
        return [dict(item) for item in self.process_table]

    def port_pids(self, _port):
        return list(self.listeners)

    def disk_usage(self, _path):
        return {"totalBytes": 100_000, "usedBytes": 1_000, "freeBytes": 99_000}

    def spawn(self, command, cwd, log_path):
        pid = self.next_pid
        self.next_pid += 1
        self.spawned.append({"pid": pid, "command": list(command), "cwd": cwd, "log": log_path})
        self.process_table.append({
            "pid": pid,
            "ppid": 1,
            "pgid": pid,
            "state": "S",
            "startedAt": f"start-{pid}",
            "startedAtEpochSeconds": self.now,
            "cpuPercent": 1.0,
            "command": " ".join(command),
        })
        return pid

    def poll(self, pid):
        self.polled.append(pid)
        return self.exit_codes.get(pid)

    def signal(self, pid, signum):
        self.signals.append((pid, signum))


class SupervisorTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "scripts").mkdir()
        (self.root / "scripts" / "run-training.sh").write_text("#!/bin/sh\n")
        self.route_config = self.root / "route.json"
        self.route_config.write_text("{}\n")
        self.queue_path = self.root / "routes.json"
        self.state_dir = self.root / "state"
        self.system = FakeSystem()
        self.config = {
            "schemaVersion": 1,
            "experimentId": "test-overnight",
            "repository": self.root,
            "queueFile": self.queue_path,
            "stateDirectory": self.state_dir,
            "runRoot": self.root / "training-runs",
            "durationSeconds": 36_000.0,
            "qdNormalizationReferenceFitness": 4.0,
            "t0EpochSeconds": 900.125,
            "t0MonotonicSeconds": 400.375,
            "tickSeconds": 5.0,
            "staleProgressSeconds": 180.0,
            "checkpointGraceSeconds": 120.0,
            "terminateGraceSeconds": 15.0,
            "startupGraceSeconds": 120.0,
            "restartDelaySeconds": 10.0,
            "rapidCrashWindowSeconds": 180.0,
            "rapidCrashLimit": 3,
            "minimumDiskFreeBytes": 10,
            "requiredWorkers": 8,
            "port": 9999,
            "requireACPower": True,
        }
        self.write_queue([self.route("primary", "run-primary")])

    def tearDown(self):
        self.temporary.cleanup()

    def route(self, route_id, run_name, fallback=None):
        value = {
            "id": route_id,
            "phase": route_id,
            "config": str(self.route_config),
            "runName": run_name,
            "evaluationCap": 40_000,
            "seed": 7,
        }
        if fallback:
            value["fallbackRouteId"] = fallback
        if route_id == "fallback":
            value["safeFallback"] = True
        return value

    def write_queue(self, routes):
        self.queue_path.write_text(json.dumps({"schemaVersion": 1, "routes": routes}))

    def make_supervisor(self):
        supervisor = SUPERVISOR.Supervisor(self.config, self.system)
        supervisor.initialize()
        self.addCleanup(supervisor.lock_file.close)
        return supervisor

    def add_owned_runtime(self, launcher_pid=100, threads=8):
        self.system.process_table.extend([
            {
                "pid": 101,
                "ppid": launcher_pid,
                "pgid": launcher_pid,
                "state": "S",
                "startedAt": "trainer-start",
                "startedAtEpochSeconds": self.system.now,
                "cpuPercent": 12.5,
                "command": f"python3 {self.root}/machine-evolved-trainer/Trainer.py config.json",
            },
            {
                "pid": 102,
                "ppid": launcher_pid,
                "pgid": launcher_pid,
                "state": "S",
                "startedAt": "worker-start",
                "startedAtEpochSeconds": self.system.now,
                "cpuPercent": 780.0,
                "command": f"{self.root}/build/shellworker --threads {threads}",
            },
        ])
        self.system.listeners = [101]

    def write_checkpoint(self, run_name, evaluations):
        run_dir = self.config["runRoot"] / run_name
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "config.json").write_text(json.dumps({
            "algorithm": {"arguments": {
                "population": {"evaluations": evaluations, "generation": 2},
                "archive": {"binsPerAxis": 2, "axes": ["x", "y"]},
            }},
            "experiment": {"trainerState": {
                "evaluationSimulations": evaluations * 3,
                "bestFitnessEvaluation": max(0, evaluations - 2),
                "domainProgress": {"pending": {}},
            }},
            "structure": {"creatures": [
                {"fitness": 2.5, "data": {"metadata": {"morphologyId": "m0"}}},
                {"fitness": 3.5, "data": {"metadata": {"morphologyId": "m1"}}},
                {"fitness": -1.5, "data": {"metadata": {"morphologyId": "m0"}}},
                {"fitness": None, "data": {"metadata": {"morphologyId": "m1"}}},
            ], "templates": [{"id": "m0"}, {"id": "m1"}]},
        }))

    def test_immutable_precise_epoch_survives_restart(self):
        first = self.make_supervisor()
        epoch_before = (self.state_dir / "epoch.json").read_bytes()
        self.assertEqual(first.state["epoch"]["t0EpochSeconds"], 900.125)
        self.assertEqual(first.state["epoch"]["t0MonotonicSeconds"], 400.375)
        self.assertEqual(first.state["epoch"]["hardDeadlineEpochSeconds"], 36_900.125)
        first.lock_file.close()
        self.system.advance(600)
        second = SUPERVISOR.Supervisor(self.config, self.system)
        second.initialize()
        self.addCleanup(second.lock_file.close)
        self.assertEqual((self.state_dir / "epoch.json").read_bytes(), epoch_before)
        self.assertEqual(second.state["epoch"]["hardDeadlineEpochSeconds"], 36_900.125)

    def test_qd_normalization_reference_is_frozen_in_state(self):
        first = self.make_supervisor()
        self.assertEqual(first.state["qdNormalizationReferenceFitness"], 4.0)
        first.lock_file.close()
        changed = dict(self.config)
        changed["qdNormalizationReferenceFitness"] = 5.0
        second = SUPERVISOR.Supervisor(changed, self.system)
        self.addCleanup(lambda: second.lock_file and second.lock_file.close())
        with self.assertRaisesRegex(RuntimeError, "persisted reference"):
            second.initialize()

    def test_battery_waits_without_spawning_and_keeps_heartbeats(self):
        self.system.power = "battery"
        supervisor = self.make_supervisor()
        supervisor.tick()
        self.assertEqual(supervisor.state["status"], "waiting_power")
        self.assertEqual(self.system.spawned, [])
        initial = (self.state_dir / "heartbeats.jsonl").read_text().splitlines()
        self.system.advance(60)
        supervisor.tick()
        self.assertEqual(len((self.state_dir / "heartbeats.jsonl").read_text().splitlines()), len(initial) + 1)

    def test_command_enforces_eight_workers_original_cap_and_resume(self):
        (self.config["runRoot"] / "run-primary").mkdir(parents=True)
        supervisor = self.make_supervisor()
        supervisor.tick()
        command = self.system.spawned[0]["command"]
        self.assertEqual(command[command.index("--workers") + 1], "8")
        self.assertEqual(command[command.index("--evaluations") + 1], "40000")
        self.assertIn("--resume-existing", command)
        ledger = supervisor.state["routes"]["primary"]
        self.assertEqual(ledger["originalEvaluationCap"], 40_000)

    def test_unrelated_port_owner_blocks_start(self):
        self.system.listeners = [7654]
        supervisor = self.make_supervisor()
        supervisor.tick()
        self.assertEqual(supervisor.state["status"], "waiting_port")
        self.assertEqual(self.system.spawned, [])

    def test_deadline_never_starts_a_route(self):
        self.system.now = 36_900.125
        self.system.monotonic_now = 36_400.375
        supervisor = self.make_supervisor()
        supervisor.tick()
        self.assertEqual(supervisor.state["status"], "deadline_reached")
        self.assertEqual(self.system.spawned, [])

    def test_worker_port_metrics_and_three_minute_stall_checkpoint(self):
        supervisor = self.make_supervisor()
        supervisor.tick()
        self.add_owned_runtime()
        self.write_checkpoint("run-primary", 12)
        self.system.advance(1)
        supervisor.tick()
        self.assertTrue(supervisor.state["metrics"]["workers"]["verified"])
        self.assertEqual(supervisor.state["metrics"]["cpuPercent"], 793.5)
        self.system.advance(180)
        supervisor.tick()
        self.assertEqual(supervisor.state["status"], "checkpointing")
        self.assertEqual(supervisor.state["reason"], "evaluation_progress_stalled")
        self.assertIn((101, signal.SIGINT), self.system.signals)

    def test_normal_completion_drain_does_not_request_shutdown(self):
        supervisor = self.make_supervisor()
        supervisor.tick()
        self.add_owned_runtime()
        self.write_checkpoint("run-primary", 40_000)
        self.system.advance(1)
        supervisor.tick()
        self.system.process_table = [item for item in self.system.process_table if item["pid"] == 100]
        self.system.listeners = []
        self.system.advance(5)
        supervisor.tick()
        self.assertEqual(supervisor.state["status"], "finalizing_route")
        self.assertEqual(supervisor.state["reason"], "evaluation_cap_reached")
        self.assertIsNone(supervisor.state["shutdown"])
        self.assertEqual(self.system.signals, [])

    def test_zombie_launcher_is_reaped_and_completed_not_kept_live(self):
        supervisor = self.make_supervisor()
        supervisor.tick()
        run_dir = self.config["runRoot"] / "run-primary"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "summary.json").write_text("{}\n")
        self.system.process_table[0]["state"] = "Z"
        self.system.process_table[0]["command"] = "<defunct>"
        supervisor.tick()
        self.assertIn(100, self.system.polled)
        self.assertEqual(supervisor.state["ownedProcesses"], [])
        self.assertIsNone(supervisor.state["activeRouteId"])
        self.assertEqual(supervisor.state["routes"]["primary"]["status"], "completed")
        self.assertEqual(self.system.signals, [])

    def test_only_exact_recorded_identity_is_signaled(self):
        supervisor = self.make_supervisor()
        supervisor.tick()
        self.add_owned_runtime()
        supervisor.reconcile_owned_processes()
        supervisor.write_state()
        self.system.process_table = [
            item if item["pid"] != 101 else {**item, "startedAt": "reused-trainer"}
            for item in self.system.process_table
        ]
        supervisor.signal_recorded(None, signal.SIGTERM)
        self.assertNotIn((101, signal.SIGTERM), self.system.signals)
        self.assertIn((100, signal.SIGTERM), self.system.signals)

    def test_exec_command_change_keeps_owner_and_adopts_children(self):
        supervisor = self.make_supervisor()
        supervisor.tick()
        self.system.process_table[0]["command"] = self.system.process_table[0]["command"].replace(
            "/bin/bash", "/usr/bin/env bash", 1
        )
        self.add_owned_runtime()
        owned = supervisor.reconcile_owned_processes()
        self.assertEqual([item["pid"] for item in owned], [100, 101, 102])
        self.assertEqual(supervisor.state["activeRouteId"], "primary")

    def test_route_launch_uses_normal_application_policy(self):
        supervisor = self.make_supervisor()
        supervisor.tick()
        command = supervisor.state["routes"]["primary"]["activeAttempt"]["command"]
        self.assertEqual(command[:3], ["/usr/sbin/taskpolicy", "-a", "/bin/bash"])

    def test_repairs_already_misclassified_live_attempt(self):
        supervisor = self.make_supervisor()
        supervisor.tick()
        self.add_owned_runtime()
        supervisor.finish_attempt("process_exit", True)
        self.assertIsNone(supervisor.state["activeRouteId"])
        supervisor.tick()
        self.assertEqual(supervisor.state["activeRouteId"], "primary")
        self.assertEqual(supervisor.state["routes"]["primary"]["status"], "running")
        self.assertEqual(supervisor.state["routes"]["primary"]["attemptHistory"], [])
        self.assertEqual([item["pid"] for item in supervisor.state["ownedProcesses"]], [100, 101, 102])

    def test_compact_metrics_append_every_thirty_seconds_with_qd(self):
        supervisor = self.make_supervisor()
        supervisor.tick()
        self.add_owned_runtime()
        self.write_checkpoint("run-primary", 12)
        initial_count = len((self.state_dir / "metrics.jsonl").read_text().splitlines())
        self.system.advance(29)
        supervisor.tick()
        self.assertEqual(len((self.state_dir / "metrics.jsonl").read_text().splitlines()), initial_count)
        self.system.advance(1)
        supervisor.tick()
        lines = (self.state_dir / "metrics.jsonl").read_text().splitlines()
        self.assertEqual(len(lines), initial_count + 1)
        sample = json.loads(lines[-1])
        self.assertEqual(sample["evaluations"], 12)
        self.assertEqual(sample["domainSimulations"], 36)
        self.assertEqual(sample["qd"]["occupiedCells"], 3)
        self.assertEqual(sample["qd"]["bestFitness"], 3.5)
        self.assertEqual(sample["qd"]["qdScore"], 4.5)
        self.assertEqual(sample["qd"]["nonNegativeQdScore"], 6.0)
        self.assertEqual(sample["qd"]["totalArchiveCells"], 8)
        self.assertEqual(sample["qd"]["normalizationReferenceFitness"], 4.0)
        self.assertEqual(
            sample["qd"]["normalizationFormula"],
            "sum(max(0,fitness))/(referenceFitness*totalArchiveCells)",
        )
        self.assertAlmostEqual(sample["qd"]["normalizedQdScore"], 6.0 / 32.0)
        self.assertAlmostEqual(sample["qd"]["sampleRelativeOccupiedQdRatio"], 4.5 / 10.5)
        self.assertEqual(sample["qd"]["top5MeanFitness"], 1.5)
        self.assertEqual(sample["qd"]["top12MeanFitness"], 1.5)
        self.assertEqual(sample["qd"]["morphologies"], {
            "m0": {"occupiedCells": 2, "bestFitness": 2.5, "qdScore": 1.0},
            "m1": {"occupiedCells": 1, "bestFitness": 3.5, "qdScore": 3.5},
        })
        self.assertTrue(sample["workers"]["verified"])
        self.assertEqual(sample["diskFreeBytes"], 99_000)
        self.assertGreater(sample["deadlineRemainingSeconds"], 0)

    def test_three_rapid_crashes_abandon_primary_and_select_fallback(self):
        self.write_queue([
            self.route("primary", "run-primary", "fallback"),
            self.route("fallback", "run-fallback"),
        ])
        supervisor = self.make_supervisor()
        for attempt in range(3):
            supervisor.tick()
            self.assertEqual(supervisor.state["activeRouteId"], "primary")
            self.system.process_table = []
            self.system.advance(1)
            supervisor.tick()
            if attempt < 2:
                self.system.advance(10)
        self.assertEqual(supervisor.state["routes"]["primary"]["status"], "abandoned")
        self.system.advance(10)
        supervisor.tick()
        self.assertEqual(supervisor.state["activeRouteId"], "fallback")

    def test_disabled_safe_fallback_runs_only_when_preferred(self):
        fallback = self.route("fallback", "run-fallback")
        fallback["enabled"] = False
        fallback["safeFallback"] = True
        self.write_queue([self.route("primary", "run-primary", "fallback"), fallback])
        supervisor = self.make_supervisor()
        queue = SUPERVISOR.load_route_queue(self.queue_path, self.root)
        primary = supervisor.choose_route(queue)
        self.assertEqual(primary["id"], "primary")
        supervisor.state["routes"]["primary"]["status"] = "completed"
        self.assertIsNone(supervisor.choose_route(queue))
        supervisor.state["preferredRouteId"] = "fallback"
        selected = supervisor.choose_route(queue)
        self.assertEqual(selected["id"], "fallback")
        self.assertEqual(supervisor.state["preferredRouteId"], "fallback")
        self.system.listeners = [7654]
        supervisor.tick()
        self.assertEqual(supervisor.state["status"], "waiting_port")
        self.assertEqual(supervisor.state["preferredRouteId"], "fallback")
        self.system.listeners = []
        supervisor.tick()
        self.assertEqual(supervisor.state["activeRouteId"], "fallback")
        self.assertNotIn("preferredRouteId", supervisor.state)


if __name__ == "__main__":
    unittest.main()
