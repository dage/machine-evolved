#!/usr/bin/env python3
"""Build a factual, checksum-bound index for a staged follow-up experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def read_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def write_object(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def relative_file(repo: Path, path: Path) -> dict:
    return {
        "path": str(path.relative_to(repo)),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--experiment-root", type=Path, required=True)
    parser.add_argument("--run-prefix", default="followup-")
    args = parser.parse_args()
    repo = args.repository.resolve()
    experiment = args.experiment_root.resolve()
    state = read_object(experiment / "orchestrator-state.json")
    queue = read_object(experiment / "routes.json")["routes"]

    routes = []
    for route in queue:
        run = repo / "training-runs" / route["runName"]
        summary_path = run / "summary.json"
        checkpoint_path = run / "config.json"
        summary = read_object(summary_path) if summary_path.is_file() else None
        ledger = state.get("routes", {}).get(route["id"], {})
        ledger_status = ledger.get("status", "not-started")
        terminal_disposition = ledger_status
        if state.get("status") == "deadline_reached" and state.get("activeRouteId") == route["id"]:
            terminal_disposition = "interrupted-at-deadline"
        routes.append({
            "id": route["id"],
            "phase": route["phase"],
            "runName": route["runName"],
            "evaluationCap": route["evaluationCap"],
            "seed": route["seed"],
            "ledgerStatus": ledger_status,
            "terminalDisposition": terminal_disposition,
            "attemptCount": ledger.get("attemptCount", 0),
            "lastProgress": ledger.get("lastProgress"),
            "lastProgressAtEpochSeconds": ledger.get("lastProgressAtEpochSeconds"),
            "completedAt": ledger.get("completedAt"),
            "summary": None if summary is None else {
                key: summary.get(key) for key in (
                    "status", "completedAt", "backend", "profile", "seed", "workers",
                    "populationSize", "generation", "evaluations", "evaluatedCreatures",
                    "bestFitness", "averageFitness", "objective", "physics",
                )
            },
            "checkpoint": relative_file(repo, checkpoint_path) if checkpoint_path.is_file() else None,
            "summaryFile": relative_file(repo, summary_path) if summary_path.is_file() else None,
            "attempts": [
                {key: attempt.get(key) for key in (
                    "number", "startedAt", "endedAt", "endReason", "exitCode",
                    "resumeExisting", "commandDigest", "log",
                )}
                for attempt in ledger.get("attemptHistory", [])
            ] + ([
                {key: ledger["activeAttempt"].get(key) for key in (
                    "number", "startedAt", "endedAt", "endReason", "exitCode",
                    "resumeExisting", "commandDigest", "log",
                )}
            ] if ledger.get("activeAttempt") else []),
        })

    ledger_counts = {}
    disposition_counts = {}
    for route in routes:
        ledger_counts[route["ledgerStatus"]] = ledger_counts.get(route["ledgerStatus"], 0) + 1
        disposition = route["terminalDisposition"]
        disposition_counts[disposition] = disposition_counts.get(disposition, 0) + 1
    facts = {
        "schemaVersion": 1,
        "experimentId": state.get("experimentId"),
        "branch": "codex/followup-staged-robustness-2026-09-04",
        "timing": {
            "t0EpochSeconds": state.get("epoch", {}).get("t0EpochSeconds"),
            "hardDeadlineEpochSeconds": state.get("epoch", {}).get("hardDeadlineEpochSeconds"),
            "durationSeconds": state.get("epoch", {}).get("durationSeconds"),
            "finalUpdatedAt": state.get("updatedAt"),
            "finalStatus": state.get("status"),
            "finalReason": state.get("reason"),
        },
        "routeCounts": {
            "configured": len(routes),
            "byLedgerStatus": ledger_counts,
            "byTerminalDisposition": disposition_counts,
            "trainingConfigured": sum(route["phase"] != "exhaustive-archive-validation" for route in routes),
            "validationConfigured": sum(route["phase"] == "exhaustive-archive-validation" for route in routes),
            "trainingCompleted": sum(route["phase"] != "exhaustive-archive-validation" and route["ledgerStatus"] == "completed" for route in routes),
            "validationCompleted": sum(route["phase"] == "exhaustive-archive-validation" and route["ledgerStatus"] == "completed" for route in routes),
        },
        "methodReasons": [
            "Two independent warmup seeds were used to measure repeatability across starting populations.",
            "Each warmup was forked into controller-identical R3 and R5 banks so the continuation method was the intended changed variable.",
            "Matched continuation budgets were expressed as candidate evaluations and domain simulations rather than synthetic generations.",
            "Every finite archive entry was scheduled against 13 single-domain physics cases to measure sensitivity to gravity, mass, and friction changes.",
            "Training was allowed on battery after the user explicitly requested that power-source changes must not pause the experiment.",
            "The inter-route delay was shortened only during the final small validation jobs because the original delay consumed most of their remaining fixed validation window.",
            "The hard deadline was retained; the final route state records validation work interrupted or not started at that deadline.",
        ],
        "routes": routes,
        "events": state.get("events", []),
    }
    facts_path = experiment / "experiment-facts.json"
    write_object(facts_path, facts)

    evidence_files = [
        path for path in experiment.rglob("*")
        if path.is_file() and path.name != "evidence-file-inventory.json" and path.name != "supervisor.lock"
    ]
    run_directories = sorted(
        path for path in (repo / "training-runs").glob(args.run_prefix + "*") if path.is_dir()
    )
    for directory in run_directories:
        evidence_files.extend(path for path in directory.rglob("*") if path.is_file())
    evidence_files = sorted(set(evidence_files))
    inventory = {
        "schemaVersion": 1,
        "compression": "none",
        "scope": [str(experiment.relative_to(repo)), f"training-runs/{args.run_prefix}*"],
        "fileCount": len(evidence_files),
        "totalBytes": sum(path.stat().st_size for path in evidence_files),
        "files": [relative_file(repo, path) for path in evidence_files],
    }
    write_object(experiment / "evidence-file-inventory.json", inventory)
    print(json.dumps({
        "routeCounts": facts["routeCounts"],
        "evidenceFileCount": inventory["fileCount"],
        "evidenceTotalBytes": inventory["totalBytes"],
    }, indent=2))


if __name__ == "__main__":
    main()
