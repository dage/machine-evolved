#!/usr/bin/env python3
"""Durable, single-owner supervisor for bounded Machine Evolved training.

The supervisor deliberately owns only host lifecycle concerns.  Route choices live
in an atomically replaceable JSON queue, while the existing run-training.sh keeps
owning Trainer and ShellWorker startup.  All process signals are restricted to
identities recorded in orchestrator-state.json before the signal is sent.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path


SCHEMA_VERSION = 1
HEARTBEAT_SECONDS = 60
RUN_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


def utc_timestamp(epoch_seconds: float) -> str:
    return dt.datetime.fromtimestamp(epoch_seconds, dt.timezone.utc).isoformat()


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def atomic_json(path: Path, value: object) -> None:
    """Replace path atomically and durably on the containing filesystem."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    payload = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with temporary.open("x", encoding="utf-8") as destination:
        destination.write(payload)
        destination.flush()
        os.fsync(destination.fileno())
    os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def append_json_line(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as destination:
        destination.write(canonical_json(value) + "\n")
        destination.flush()
        os.fsync(destination.fileno())


def read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as source:
        value = json.load(source)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def positive_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"{name} must be positive")
    return float(value)


def positive_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def load_configuration(path: Path) -> dict:
    raw = read_json(path)
    if raw.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError("Unsupported supervisor configuration schemaVersion")
    base = path.parent
    repository = (base / raw.get("repositoryDirectory", "..")).resolve()
    required_workers = positive_integer(raw.get("requiredWorkers", 8), "requiredWorkers")
    if required_workers != 8:
        raise ValueError("The overnight experiment requires exactly 8 workers")
    tick_seconds = positive_number(raw.get("tickSeconds", 5), "tickSeconds")
    if tick_seconds > HEARTBEAT_SECONDS:
        raise ValueError("tickSeconds cannot exceed the 60-second state-write requirement")
    port = positive_integer(raw.get("port", 9999), "port")
    if port != 9999:
        raise ValueError("Machine Evolved Trainer ownership checks require port 9999")
    config = {
        "schemaVersion": SCHEMA_VERSION,
        "experimentId": str(raw["experimentId"]),
        "repository": repository,
        "queueFile": (repository / raw["queueFile"]).resolve(),
        "stateDirectory": (repository / raw["stateDirectory"]).resolve(),
        "runRoot": (repository / raw.get("runRoot", "training-runs")).resolve(),
        "durationSeconds": positive_number(raw.get("durationSeconds", 36_000), "durationSeconds"),
        "t0EpochSeconds": (
            positive_number(raw["t0EpochSeconds"], "t0EpochSeconds")
            if "t0EpochSeconds" in raw else None
        ),
        "t0MonotonicSeconds": (
            positive_number(raw["t0MonotonicSeconds"], "t0MonotonicSeconds")
            if "t0MonotonicSeconds" in raw else None
        ),
        "tickSeconds": tick_seconds,
        "staleProgressSeconds": positive_number(
            raw.get("staleProgressSeconds", 180), "staleProgressSeconds"
        ),
        "checkpointGraceSeconds": positive_number(
            raw.get("checkpointGraceSeconds", 120), "checkpointGraceSeconds"
        ),
        "terminateGraceSeconds": positive_number(
            raw.get("terminateGraceSeconds", 15), "terminateGraceSeconds"
        ),
        "startupGraceSeconds": positive_number(
            raw.get("startupGraceSeconds", 120), "startupGraceSeconds"
        ),
        "restartDelaySeconds": positive_number(
            raw.get("restartDelaySeconds", 10), "restartDelaySeconds"
        ),
        "rapidCrashWindowSeconds": positive_number(
            raw.get("rapidCrashWindowSeconds", 180), "rapidCrashWindowSeconds"
        ),
        "rapidCrashLimit": positive_integer(raw.get("rapidCrashLimit", 3), "rapidCrashLimit"),
        "minimumDiskFreeBytes": positive_integer(
            raw.get("minimumDiskFreeBytes", 10 * 1024**3), "minimumDiskFreeBytes"
        ),
        "requiredWorkers": required_workers,
        "port": port,
        "requireACPower": bool(raw.get("requireACPower", True)),
    }
    if not repository.is_dir():
        raise ValueError(f"repositoryDirectory does not exist: {repository}")
    runner = repository / "scripts" / "run-training.sh"
    if not runner.is_file():
        raise ValueError(f"Training runner does not exist: {runner}")
    return config


def validate_route(raw: dict, repository: Path) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("Each route must be an object")
    route_id = str(raw.get("id", ""))
    run_name = str(raw.get("runName", ""))
    if not RUN_NAME_PATTERN.fullmatch(route_id):
        raise ValueError("route id may contain only letters, digits, dots, underscores, and dashes")
    if not RUN_NAME_PATTERN.fullmatch(run_name):
        raise ValueError(f"Invalid runName for route {route_id}")
    configured_path = Path(str(raw.get("config", "")))
    config_path = (configured_path if configured_path.is_absolute() else repository / configured_path).resolve()
    route = {
        "id": route_id,
        "phase": str(raw.get("phase", route_id)),
        "config": str(config_path),
        "runName": run_name,
        "evaluationCap": positive_integer(raw.get("evaluationCap"), f"{route_id}.evaluationCap"),
        "seed": raw.get("seed"),
        "stallEvaluations": raw.get("stallEvaluations"),
        "fallbackRouteId": raw.get("fallbackRouteId"),
        "safeFallback": bool(raw.get("safeFallback", False)),
        "enabled": bool(raw.get("enabled", True)),
        "retainFiles": list(raw.get("retainFiles", ["trainer.log", "shellworker.log"])),
    }
    if route["seed"] is not None and (
        isinstance(route["seed"], bool) or not isinstance(route["seed"], int) or route["seed"] < 0
    ):
        raise ValueError(f"{route_id}.seed must be a non-negative integer")
    if route["stallEvaluations"] is not None:
        route["stallEvaluations"] = positive_integer(
            route["stallEvaluations"], f"{route_id}.stallEvaluations"
        )
    if route["fallbackRouteId"] is not None:
        route["fallbackRouteId"] = str(route["fallbackRouteId"])
    for name in route["retainFiles"]:
        candidate = Path(name)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError(f"Route {route_id} retainFiles must stay inside its run directory")
    return route


def load_route_queue(path: Path, repository: Path) -> list[dict]:
    raw = read_json(path)
    if raw.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError("Unsupported route queue schemaVersion")
    routes = [validate_route(route, repository) for route in raw.get("routes", [])]
    ids = [route["id"] for route in routes]
    if len(ids) != len(set(ids)):
        raise ValueError("Route ids must be unique")
    id_set = set(ids)
    for route in routes:
        fallback = route["fallbackRouteId"]
        if fallback is not None and fallback not in id_set:
            raise ValueError(f"Route {route['id']} references missing fallback {fallback}")
    return routes


def route_digest(route: dict) -> str:
    immutable = {key: value for key, value in route.items() if key != "enabled"}
    return hashlib.sha256(canonical_json(immutable).encode("utf-8")).hexdigest()


def process_role(command: str) -> str:
    if re.search(r"(^|[/ ])Trainer\.py(?: |$)", command):
        return "trainer"
    if re.search(r"(^|[/ ])shellworker(?: |$)", command, re.IGNORECASE):
        return "shellworker"
    if re.search(r"(^|[/ ])caffeinate(?: |$)", command):
        return "caffeinate"
    return "owned"


def shellworker_thread_argument(command: str) -> int | None:
    match = re.search(r"(?:^|\s)--threads(?:=|\s+)(\d+)(?:\s|$)", command)
    return int(match.group(1)) if match else None


class RealSystem:
    def __init__(self) -> None:
        self.children: dict[int, subprocess.Popen] = {}

    def epoch(self) -> float:
        return time.time()

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def boot_id(self) -> str:
        if sys.platform == "darwin":
            result = subprocess.run(
                ["/usr/sbin/sysctl", "-n", "kern.boottime"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        path = Path("/proc/sys/kernel/random/boot_id")
        return path.read_text(encoding="utf-8").strip() if path.exists() else "unknown"

    def power_source(self) -> str:
        try:
            result = subprocess.run(
                ["/usr/bin/pmset", "-g", "batt"],
                capture_output=True,
                text=True,
                check=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return "unknown"
        first_line = result.stdout.splitlines()[0] if result.stdout else ""
        if "Battery Power" in first_line:
            return "battery"
        if "AC Power" in first_line:
            return "ac"
        return "unknown"

    def processes(self) -> list[dict]:
        result = subprocess.run(
            ["/bin/ps", "-axo", "pid=,ppid=,pgid=,lstart=,%cpu=,command="],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "LC_ALL": "C"},
        )
        records = []
        for line in result.stdout.splitlines():
            fields = line.split(None, 9)
            if len(fields) < 10:
                continue
            try:
                records.append({
                    "pid": int(fields[0]),
                    "ppid": int(fields[1]),
                    "pgid": int(fields[2]),
                    "startedAt": " ".join(fields[3:8]),
                    "cpuPercent": float(fields[8]),
                    "command": fields[9],
                })
            except ValueError:
                continue
        return records

    def port_pids(self, port: int) -> list[int]:
        try:
            result = subprocess.run(
                ["/usr/sbin/lsof", "-nP", "-a", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return []
        return sorted({int(line) for line in result.stdout.splitlines() if line.strip().isdigit()})

    def disk_usage(self, path: Path) -> dict:
        usage = shutil.disk_usage(path)
        return {"totalBytes": usage.total, "usedBytes": usage.used, "freeBytes": usage.free}

    def spawn(self, command: list[str], cwd: Path, log_path: Path) -> int:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = log_path.open("ab", buffering=0)
        try:
            child = subprocess.Popen(
                command,
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
            )
        finally:
            log.close()
        self.children[child.pid] = child
        return child.pid

    def poll(self, pid: int) -> int | None:
        child = self.children.get(pid)
        return child.poll() if child else None

    def signal(self, pid: int, signum: int) -> None:
        os.kill(pid, signum)


class Supervisor:
    def __init__(self, config: dict, system: RealSystem | None = None) -> None:
        self.config = config
        self.system = system or RealSystem()
        self.state_dir = Path(config["stateDirectory"])
        self.state_path = self.state_dir / "orchestrator-state.json"
        self.epoch_path = self.state_dir / "epoch.json"
        self.heartbeat_path = self.state_dir / "heartbeats.jsonl"
        self.lock_path = self.state_dir / "supervisor.lock"
        self.lock_file = None
        self.state: dict = {}

    def acquire_lock(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.lock_file = self.lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(f"Another supervisor owns {self.lock_path}") from error
        self.lock_file.seek(0)
        self.lock_file.truncate()
        self.lock_file.write(canonical_json({"pid": os.getpid(), "acquiredAt": utc_timestamp(self.system.epoch())}) + "\n")
        self.lock_file.flush()
        os.fsync(self.lock_file.fileno())

    def initialize(self) -> None:
        self.acquire_lock()
        now = self.system.epoch()
        monotonic = self.system.monotonic()
        boot_id = self.system.boot_id()
        if self.epoch_path.exists():
            epoch = read_json(self.epoch_path)
            if epoch.get("experimentId") != self.config["experimentId"]:
                raise RuntimeError("Existing immutable epoch belongs to another experiment")
            if float(epoch.get("durationSeconds", -1)) != self.config["durationSeconds"]:
                raise RuntimeError("Configured duration differs from the immutable original duration")
        else:
            t0_epoch = self.config["t0EpochSeconds"] or now
            elapsed_before_supervisor = max(0, now - t0_epoch)
            t0_monotonic = self.config["t0MonotonicSeconds"] or (monotonic - elapsed_before_supervisor)
            epoch = {
                "schemaVersion": SCHEMA_VERSION,
                "experimentId": self.config["experimentId"],
                "t0EpochSeconds": t0_epoch,
                "t0MonotonicSeconds": t0_monotonic,
                "bootId": boot_id,
                "durationSeconds": self.config["durationSeconds"],
                "hardDeadlineEpochSeconds": t0_epoch + self.config["durationSeconds"],
                "hardDeadlineMonotonicSeconds": t0_monotonic + self.config["durationSeconds"],
            }
            # O_EXCL makes the T0 record immutable even under an accidental race.
            self.epoch_path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(self.epoch_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                payload = (json.dumps(epoch, indent=2, sort_keys=True) + "\n").encode("utf-8")
                os.write(descriptor, payload)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        if self.state_path.exists():
            self.state = read_json(self.state_path)
        else:
            self.state = {
                "schemaVersion": SCHEMA_VERSION,
                "experimentId": self.config["experimentId"],
                "epoch": epoch,
                "status": "initializing",
                "reason": None,
                "activeRouteId": None,
                "routes": {},
                "ownedProcesses": [],
                "shutdown": None,
                "metrics": {},
                "events": [],
                "lastHeartbeatEpochSeconds": None,
            }
        self.state["epoch"] = epoch
        self.reconcile_owned_processes()
        self.write_state(now)

    def deadline_reached(self) -> bool:
        epoch = self.state["epoch"]
        if self.system.epoch() >= epoch["hardDeadlineEpochSeconds"]:
            return True
        return (
            self.system.boot_id() == epoch["bootId"]
            and self.system.monotonic() >= epoch["hardDeadlineMonotonicSeconds"]
        )

    def current_processes(self) -> list[dict]:
        return self.system.processes()

    @staticmethod
    def identity_matches(recorded: dict, current: dict) -> bool:
        return (
            recorded.get("pid") == current.get("pid")
            and recorded.get("pgid") == current.get("pgid")
            and recorded.get("startedAt") == current.get("startedAt")
            and recorded.get("command") == current.get("command")
        )

    def reconcile_owned_processes(self, processes: list[dict] | None = None) -> list[dict]:
        processes = processes if processes is not None else self.current_processes()
        by_pid = {process["pid"]: process for process in processes}
        active = self.active_route_state()
        attempt = active.get("activeAttempt") if active else None
        if not attempt:
            self.state["ownedProcesses"] = []
            return []
        launcher_pid = attempt["launcherPid"]
        launcher_pgid = attempt["processGroupId"]
        recorded_by_pid = {item["pid"]: item for item in attempt.get("ownedProcesses", [])}
        launcher_record = recorded_by_pid.get(launcher_pid)
        if launcher_record and not self.identity_matches(launcher_record, by_pid.get(launcher_pid, {})):
            # Never adopt a reused process group when the recorded owner identity vanished.
            live = [
                item for item in recorded_by_pid.values()
                if self.identity_matches(item, by_pid.get(item["pid"], {}))
            ]
        else:
            live = []
            for process in processes:
                if process["pgid"] != launcher_pgid:
                    continue
                existing = recorded_by_pid.get(process["pid"])
                if existing and not self.identity_matches(existing, process):
                    continue
                record = copy.deepcopy(process)
                record["role"] = "launcher" if process["pid"] == launcher_pid else process_role(process["command"])
                record["recordedAtEpochSeconds"] = existing.get(
                    "recordedAtEpochSeconds", self.system.epoch()
                ) if existing else self.system.epoch()
                live.append(record)
        live.sort(key=lambda item: item["pid"])
        attempt["ownedProcesses"] = live
        self.state["ownedProcesses"] = copy.deepcopy(live)
        return live

    def active_route_state(self) -> dict | None:
        route_id = self.state.get("activeRouteId")
        return self.state.get("routes", {}).get(route_id) if route_id else None

    def event(self, kind: str, detail: str) -> None:
        events = self.state.setdefault("events", [])
        events.append({"at": utc_timestamp(self.system.epoch()), "kind": kind, "detail": detail})
        del events[:-100]

    def write_state(self, now: float | None = None) -> None:
        now = self.system.epoch() if now is None else now
        self.state["updatedAt"] = utc_timestamp(now)
        self.state["updatedAtEpochSeconds"] = now
        atomic_json(self.state_path, self.state)
        last = self.state.get("lastHeartbeatEpochSeconds")
        if last is None or now - last >= HEARTBEAT_SECONDS:
            heartbeat = {
                "schemaVersion": SCHEMA_VERSION,
                "experimentId": self.config["experimentId"],
                "capturedAt": utc_timestamp(now),
                "capturedAtEpochSeconds": now,
                "status": self.state.get("status"),
                "reason": self.state.get("reason"),
                "activeRouteId": self.state.get("activeRouteId"),
                "metrics": self.state.get("metrics", {}),
            }
            append_json_line(self.heartbeat_path, heartbeat)
            self.state["lastHeartbeatEpochSeconds"] = now
            atomic_json(self.state_path, self.state)

    def route_command(self, route: dict, resume: bool) -> list[str]:
        command = [
            str(self.config["repository"] / "scripts" / "run-training.sh"),
            "--config", route["config"],
            "--evaluations", str(route["evaluationCap"]),
            "--workers", str(self.config["requiredWorkers"]),
            "--run-name", route["runName"],
        ]
        if route["seed"] is not None:
            command.extend(["--seed", str(route["seed"])])
        if route["stallEvaluations"] is not None:
            command.extend(["--stall-evaluations", str(route["stallEvaluations"])])
        if resume:
            command.append("--resume-existing")
        return command

    def route_run_dir(self, route: dict) -> Path:
        return self.config["runRoot"] / route["runName"]

    def archive_attempt_files(self, route: dict, attempt_number: int) -> None:
        run_dir = self.route_run_dir(route)
        archive_dir = self.state_dir / "attempts" / route["id"] / f"attempt-{attempt_number:03d}-retained"
        copied = []
        for relative in route["retainFiles"]:
            source = run_dir / relative
            if not source.is_file():
                continue
            destination = archive_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied.append(str(destination.relative_to(self.state_dir)))
        if copied:
            self.event("attempt-logs-retained", f"{route['id']}: {', '.join(copied)}")

    def ensure_route_ledger(self, route: dict) -> dict:
        ledger = self.state["routes"].get(route["id"])
        digest = route_digest(route)
        if ledger:
            if ledger["definitionDigest"] != digest:
                raise RuntimeError(f"Claimed route {route['id']} changed in the live queue")
            return ledger
        ledger = {
            "id": route["id"],
            "definition": copy.deepcopy(route),
            "definitionDigest": digest,
            "originalEvaluationCap": route["evaluationCap"],
            "status": "pending",
            "attemptCount": 0,
            "consecutiveRapidCrashes": 0,
            "activeAttempt": None,
            "lastProgress": None,
            "lastProgressAtEpochSeconds": None,
            "nextStartNotBeforeEpochSeconds": None,
        }
        self.state["routes"][route["id"]] = ledger
        return ledger

    def choose_route(self, queue: list[dict]) -> dict | None:
        preferred = self.state.pop("preferredRouteId", None)
        by_id = {route["id"]: route for route in queue}
        if preferred:
            route = by_id.get(preferred)
            if route and route["enabled"]:
                ledger = self.ensure_route_ledger(route)
                if ledger["status"] not in ("completed", "abandoned"):
                    return ledger["definition"]
        for route in queue:
            if not route["enabled"]:
                continue
            ledger = self.ensure_route_ledger(route)
            if ledger["status"] not in ("completed", "abandoned"):
                return ledger["definition"]
        return None

    def start_route(self, route: dict) -> None:
        ledger = self.ensure_route_ledger(route)
        now = self.system.epoch()
        if ledger.get("nextStartNotBeforeEpochSeconds", 0) and now < ledger["nextStartNotBeforeEpochSeconds"]:
            self.state["status"] = "waiting_restart_backoff"
            self.state["reason"] = "restart_backoff"
            return
        config_path = Path(route["config"])
        if not config_path.is_file():
            self.state["status"] = "waiting_route_input"
            self.state["reason"] = f"missing_route_config:{route['config']}"
            return
        run_dir = self.route_run_dir(route)
        if (run_dir / "summary.json").is_file():
            ledger["status"] = "completed"
            ledger["completedAt"] = utc_timestamp(now)
            self.event("route-completed", f"{route['id']} already has a summary")
            return
        port_pids = self.system.port_pids(self.config["port"])
        if port_pids:
            self.state["status"] = "waiting_port"
            self.state["reason"] = f"port_{self.config['port']}_owned_by_unrelated_pid:{','.join(map(str, port_pids))}"
            return
        attempt_number = ledger["attemptCount"] + 1
        if ledger["attemptCount"]:
            self.archive_attempt_files(route, ledger["attemptCount"])
        resume = run_dir.exists()
        command = self.route_command(route, resume)
        log_path = self.state_dir / "attempts" / route["id"] / f"attempt-{attempt_number:03d}.log"
        launcher_pid = self.system.spawn(command, self.config["repository"], log_path)
        processes = self.current_processes()
        launcher = next((item for item in processes if item["pid"] == launcher_pid), None)
        if launcher is None:
            raise RuntimeError(f"Could not record launcher identity for pid {launcher_pid}")
        launcher_record = copy.deepcopy(launcher)
        launcher_record["role"] = "launcher"
        launcher_record["recordedAtEpochSeconds"] = now
        attempt = {
            "number": attempt_number,
            "startedAt": utc_timestamp(now),
            "startedAtEpochSeconds": now,
            "launcherPid": launcher_pid,
            "processGroupId": launcher["pgid"],
            "command": command,
            "commandDigest": hashlib.sha256(canonical_json(command).encode("utf-8")).hexdigest(),
            "resumeExisting": resume,
            "log": str(log_path),
            "ownedProcesses": [launcher_record],
            "workerVerifiedAtEpochSeconds": None,
            "portVerifiedAtEpochSeconds": None,
        }
        ledger["attemptCount"] = attempt_number
        ledger["activeAttempt"] = attempt
        ledger["status"] = "running"
        ledger["lastProgressAtEpochSeconds"] = now
        ledger["nextStartNotBeforeEpochSeconds"] = None
        self.state["activeRouteId"] = route["id"]
        self.state["ownedProcesses"] = [launcher_record]
        self.state["status"] = "running"
        self.state["reason"] = None
        self.event("route-started", f"{route['id']} attempt {attempt_number}; resume={resume}")

    def progress_for(self, route: dict) -> dict:
        checkpoint = self.route_run_dir(route) / "config.json"
        result = {
            "checkpointPath": str(checkpoint),
            "checkpointExists": checkpoint.is_file(),
            "checkpointAgeSeconds": None,
            "evaluations": None,
            "generation": None,
            "domainSimulations": None,
            "readError": None,
        }
        if not checkpoint.is_file():
            return result
        try:
            stat = checkpoint.stat()
            value = read_json(checkpoint)
            population = value["algorithm"]["arguments"]["population"]
            trainer_state = value.get("experiment", {}).get("trainerState", {})
            result.update({
                "checkpointAgeSeconds": max(0, self.system.epoch() - stat.st_mtime),
                "evaluations": int(population.get("evaluations", 0)),
                "generation": int(population.get("generation", 0)),
                "domainSimulations": int(trainer_state.get("evaluationSimulations", 0)),
            })
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            result["readError"] = str(error)
        return result

    def update_metrics(self, queue: list[dict], processes: list[dict]) -> None:
        now = self.system.epoch()
        active = self.active_route_state()
        route = active["definition"] if active else None
        progress = self.progress_for(route) if route else None
        if active and progress and progress["evaluations"] is not None:
            current = progress["evaluations"]
            previous = active.get("lastProgress")
            if previous is None or current > previous:
                previous_at = active.get("lastProgressAtEpochSeconds")
                active["lastProgress"] = current
                active["lastProgressAtEpochSeconds"] = now
                if previous is not None and previous_at is not None and now > previous_at:
                    active["evaluationsPerMinute"] = (current - previous) * 60 / (now - previous_at)
            progress["secondsSinceEvaluationProgress"] = max(
                0, now - active["lastProgressAtEpochSeconds"]
            )
        disk = self.system.disk_usage(self.state_dir)
        owned_pids = {item["pid"] for item in self.state.get("ownedProcesses", [])}
        owned_current = [process for process in processes if process["pid"] in owned_pids]
        pending = 0
        for route_item in queue:
            ledger = self.state["routes"].get(route_item["id"])
            if route_item["enabled"] and (not ledger or ledger["status"] not in ("completed", "abandoned")):
                pending += 1
        self.state["metrics"] = {
            "liveness": {
                "ownedProcessCount": len(owned_current),
                "trainerCount": sum(process_role(item["command"]) == "trainer" for item in owned_current),
                "shellworkerProcessCount": sum(
                    process_role(item["command"]) == "shellworker" for item in owned_current
                ),
            },
            "progress": progress,
            "throughputEvaluationsPerMinute": active.get("evaluationsPerMinute") if active else None,
            "queue": {"configured": len(queue), "pending": pending},
            "cpuPercent": sum(item.get("cpuPercent", 0.0) for item in owned_current),
            "disk": disk,
            "powerSource": self.system.power_source(),
            "port": {"number": self.config["port"], "listenerPids": self.system.port_pids(self.config["port"])},
            "workers": self.worker_verification(owned_current),
        }

    def worker_verification(self, processes: list[dict]) -> dict:
        shellworkers = [
            item for item in processes if process_role(item["command"]) == "shellworker"
        ]
        arguments = [shellworker_thread_argument(item["command"]) for item in shellworkers]
        return {
            "required": self.config["requiredWorkers"],
            "shellworkerPids": [item["pid"] for item in shellworkers],
            "threadArguments": arguments,
            "verified": len(shellworkers) == 1 and arguments == [self.config["requiredWorkers"]],
        }

    def verify_runtime_ownership(self, owned: list[dict]) -> tuple[bool, str | None]:
        active = self.active_route_state()
        if not active:
            return True, None
        attempt = active["activeAttempt"]
        now = self.system.epoch()
        age = now - attempt["startedAtEpochSeconds"]
        owned_pids = {item["pid"] for item in owned}
        port_pids = self.system.port_pids(self.config["port"])
        if port_pids:
            if not set(port_pids).issubset(owned_pids):
                return False, "trainer_port_owner_is_not_recorded"
            attempt["portVerifiedAtEpochSeconds"] = now
        workers = self.worker_verification(owned)
        if workers["verified"]:
            attempt["workerVerifiedAtEpochSeconds"] = now
        if age >= self.config["startupGraceSeconds"]:
            if not port_pids:
                return False, "trainer_port_not_ready_before_startup_deadline"
            if not workers["verified"]:
                return False, "exactly_8_workers_not_verified_before_startup_deadline"
        return True, None

    def record_owned_before_signal(self) -> list[dict]:
        owned = self.reconcile_owned_processes(self.current_processes())
        self.write_state()
        return owned

    def signal_recorded(self, roles: set[str] | None, signum: int) -> list[int]:
        owned = self.record_owned_before_signal()
        current = {item["pid"]: item for item in self.current_processes()}
        signaled = []
        # Children first for graceful Trainer handling; launcher last for forceful cleanup.
        for recorded in sorted(owned, key=lambda item: item["role"] == "launcher"):
            if roles is not None and recorded["role"] not in roles:
                continue
            if not self.identity_matches(recorded, current.get(recorded["pid"], {})):
                continue
            try:
                self.system.signal(recorded["pid"], signum)
                signaled.append(recorded["pid"])
            except ProcessLookupError:
                pass
        return signaled

    def begin_shutdown(self, reason: str, resume: bool) -> None:
        if self.state.get("shutdown"):
            return
        now = self.system.epoch()
        trainer_pids = self.signal_recorded({"trainer"}, signal.SIGINT)
        if not trainer_pids:
            self.signal_recorded({"launcher"}, signal.SIGINT)
        self.state["shutdown"] = {
            "reason": reason,
            "resume": resume,
            "requestedAtEpochSeconds": now,
            "forceAtEpochSeconds": now + self.config["checkpointGraceSeconds"],
            "killAtEpochSeconds": now + self.config["checkpointGraceSeconds"] + self.config["terminateGraceSeconds"],
            "trainerPidsSignaled": trainer_pids,
            "termSent": False,
            "killSent": False,
        }
        self.state["status"] = "checkpointing"
        self.state["reason"] = reason
        self.event("checkpoint-requested", reason)

    def advance_shutdown(self, processes: list[dict]) -> None:
        shutdown = self.state["shutdown"]
        owned = self.reconcile_owned_processes(processes)
        now = self.system.epoch()
        if not owned:
            self.finish_attempt(shutdown["reason"], shutdown["resume"])
            return
        if now >= shutdown["forceAtEpochSeconds"] and not shutdown["termSent"]:
            pids = self.signal_recorded(None, signal.SIGTERM)
            shutdown["termSent"] = True
            shutdown["termPids"] = pids
            self.state["status"] = "terminating"
            self.event("owned-processes-terminated", f"SIGTERM pids={pids}")
        if now >= shutdown["killAtEpochSeconds"] and not shutdown["killSent"]:
            pids = self.signal_recorded(None, signal.SIGKILL)
            shutdown["killSent"] = True
            shutdown["killPids"] = pids
            self.event("owned-processes-killed", f"SIGKILL pids={pids}")

    def finish_attempt(self, reason: str, resume: bool) -> None:
        now = self.system.epoch()
        active = self.active_route_state()
        if not active:
            self.state["shutdown"] = None
            return
        attempt = active["activeAttempt"]
        attempt["endedAt"] = utc_timestamp(now)
        attempt["endedAtEpochSeconds"] = now
        attempt["endReason"] = reason
        attempt["exitCode"] = self.system.poll(attempt["launcherPid"])
        active.setdefault("attemptHistory", []).append(attempt)
        active["activeAttempt"] = None
        self.state["ownedProcesses"] = []
        self.state["shutdown"] = None
        route = active["definition"]
        completed = (self.route_run_dir(route) / "summary.json").is_file()
        if completed:
            active["status"] = "completed"
            active["completedAt"] = utc_timestamp(now)
            active["consecutiveRapidCrashes"] = 0
            self.event("route-completed", route["id"])
        elif reason == "deadline":
            active["status"] = "stopped_at_deadline"
        elif reason == "battery_power":
            active["status"] = "waiting_power"
            active["nextStartNotBeforeEpochSeconds"] = now + self.config["restartDelaySeconds"]
        else:
            uptime = now - attempt["startedAtEpochSeconds"]
            is_rapid = reason == "process_exit" and uptime < self.config["rapidCrashWindowSeconds"]
            active["consecutiveRapidCrashes"] = (
                active["consecutiveRapidCrashes"] + 1 if is_rapid else 0
            )
            if active["consecutiveRapidCrashes"] >= self.config["rapidCrashLimit"]:
                active["status"] = "abandoned"
                fallback = route.get("fallbackRouteId")
                if fallback:
                    self.state["preferredRouteId"] = fallback
                self.event("route-abandoned", f"{route['id']} after {active['consecutiveRapidCrashes']} rapid crashes")
            else:
                active["status"] = "pending"
                active["nextStartNotBeforeEpochSeconds"] = now + self.config["restartDelaySeconds"]
                self.event("route-restart-scheduled", f"{route['id']} after {reason}")
        self.state["activeRouteId"] = None
        if resume and reason not in ("deadline", "battery_power"):
            self.state["status"] = "waiting_restart_backoff"
        elif reason == "battery_power":
            self.state["status"] = "waiting_power"

    def handle_unexpected_exit(self, owned: list[dict]) -> bool:
        active = self.active_route_state()
        if not active or self.state.get("shutdown") or owned:
            return False
        self.finish_attempt("process_exit", True)
        return True

    def tick(self) -> None:
        now = self.system.epoch()
        try:
            queue = load_route_queue(self.config["queueFile"], self.config["repository"])
        except (OSError, ValueError, json.JSONDecodeError) as error:
            queue = []
            self.state["status"] = "waiting_route_queue"
            self.state["reason"] = str(error)
        processes = self.current_processes()
        owned = self.reconcile_owned_processes(processes)

        if self.deadline_reached():
            if owned and not self.state.get("shutdown"):
                self.begin_shutdown("deadline", False)
            elif self.state.get("shutdown"):
                self.advance_shutdown(processes)
            else:
                self.state["status"] = "deadline_reached"
                self.state["reason"] = "hard_deadline"
            self.update_metrics(queue, processes)
            self.write_state(now)
            return

        if self.state.get("shutdown"):
            self.advance_shutdown(processes)
            self.update_metrics(queue, processes)
            self.write_state(now)
            return

        power = self.system.power_source()
        if self.config["requireACPower"] and power != "ac":
            if owned:
                self.begin_shutdown("battery_power", True)
            else:
                self.state["status"] = "waiting_power"
                self.state["reason"] = "battery_power" if power == "battery" else "power_source_unknown"
            self.update_metrics(queue, processes)
            self.write_state(now)
            return

        disk = self.system.disk_usage(self.state_dir)
        if disk["freeBytes"] < self.config["minimumDiskFreeBytes"]:
            if owned:
                self.begin_shutdown("low_disk", True)
            else:
                self.state["status"] = "waiting_disk"
                self.state["reason"] = "minimum_free_disk_not_met"
            self.update_metrics(queue, processes)
            self.write_state(now)
            return

        if self.handle_unexpected_exit(owned):
            self.update_metrics(queue, processes)
            self.write_state(now)
            return

        active = self.active_route_state()
        if active:
            okay, reason = self.verify_runtime_ownership(owned)
            if not okay:
                self.begin_shutdown(reason or "runtime_ownership_failed", True)
            else:
                progress = self.progress_for(active["definition"])
                if progress["evaluations"] is not None:
                    current = progress["evaluations"]
                    if active["lastProgress"] is None or current > active["lastProgress"]:
                        active["lastProgress"] = current
                        active["lastProgressAtEpochSeconds"] = now
                    elif now - active["lastProgressAtEpochSeconds"] >= self.config["staleProgressSeconds"]:
                        self.begin_shutdown("evaluation_progress_stalled", True)
        else:
            route = self.choose_route(queue)
            if route:
                self.start_route(route)
            elif self.state["status"] not in ("waiting_route_queue",):
                self.state["status"] = "queue_complete"
                self.state["reason"] = None
        self.update_metrics(queue, self.current_processes())
        self.write_state(now)

    def run(self) -> None:
        self.initialize()
        while True:
            self.tick()
            if self.state.get("status") == "deadline_reached" and not self.state.get("ownedProcesses"):
                return
            self.system.sleep(self.config["tickSeconds"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--once", action="store_true", help="Run one non-launching status cycle only")
    args = parser.parse_args()
    config = load_configuration(args.config.resolve())
    supervisor = Supervisor(config)
    supervisor.initialize()
    if args.once:
        # Deliberately observational: --once never starts or signals training.
        queue = load_route_queue(config["queueFile"], config["repository"])
        processes = supervisor.current_processes()
        supervisor.reconcile_owned_processes(processes)
        supervisor.update_metrics(queue, processes)
        supervisor.state["status"] = "observed"
        supervisor.state["reason"] = "once_mode_does_not_launch"
        supervisor.write_state()
        return
    while True:
        supervisor.tick()
        if supervisor.state.get("status") == "deadline_reached" and not supervisor.state.get("ownedProcesses"):
            return
        supervisor.system.sleep(config["tickSeconds"])


if __name__ == "__main__":
    main()
