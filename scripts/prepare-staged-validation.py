#!/usr/bin/env python3
"""Append exhaustive, single-domain archive validation routes when forks finish."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys


CASES = (
    ("nominal", {}),
    ("gravity-99", {"gravityZ": -99.0}),
    ("gravity-101", {"gravityZ": -101.0}),
    ("mass-99", {"capsuleMassScale": 0.000099}),
    ("mass-101", {"capsuleMassScale": 0.000101}),
    ("friction-060", {"groundFriction": 0.6}),
    ("friction-100", {"groundFriction": 1.0}),
    ("gravity-985", {"gravityZ": -98.5}),
    ("gravity-1015", {"gravityZ": -101.5}),
    ("mass-985", {"capsuleMassScale": 0.0000985}),
    ("mass-1015", {"capsuleMassScale": 0.0001015}),
    ("gravity-101-mass-101", {"gravityZ": -101.0, "capsuleMassScale": 0.000101}),
    ("gravity-99-friction-060", {"gravityZ": -99.0, "groundFriction": 0.6}),
)


def read_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def write_object(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def finite_archive_count(checkpoint: dict) -> int:
    return sum(
        entry.get("fitness") is not None and math.isfinite(float(entry["fitness"]))
        for entry in checkpoint.get("structure", {}).get("creatures", [])
    )


def completed_source(repo_root: Path, route: dict) -> tuple[Path, dict, int] | None:
    run_directory = repo_root / "training-runs" / route["runName"]
    summary_path = run_directory / "summary.json"
    checkpoint_path = run_directory / "config.json"
    if not summary_path.is_file() or not checkpoint_path.is_file():
        return None
    summary = read_object(summary_path)
    if summary.get("status") != "completed" or int(summary.get("evaluations", -1)) < int(route["evaluationCap"]):
        return None
    count = finite_archive_count(read_object(checkpoint_path))
    if count <= 0 or count != int(summary.get("evaluatedCreatures", -1)):
        raise ValueError(f"Archive count does not match summary for {route['id']}")
    return checkpoint_path, summary, count


def generate_case_config(
    prepare_script: Path,
    checkpoint: Path,
    case_id: str,
    physics: dict[str, float],
    count: int,
    seed: int,
    output: Path,
) -> None:
    command = [
        sys.executable,
        str(prepare_script),
        "--checkpoint", str(checkpoint),
        "--case", case_id,
        "--top", str(count),
        "--single-domain",
        "--seed", str(seed),
        "--output", str(output),
    ]
    for key, value in physics.items():
        command.extend(("--physics", f"{key}={value}"))
    subprocess.run(command, check=True)


def prepare(repo_root: Path, experiment_root: Path, prepare_script: Path) -> dict:
    routes_path = experiment_root / "routes.json"
    routes_document = read_object(routes_path)
    routes = routes_document.get("routes")
    if not isinstance(routes, list):
        raise ValueError("routes.json must contain a routes array")
    by_id = {route["id"]: route for route in routes}
    sources = [
        route for route in routes
        if route.get("phase") == "matched-continuation" and route["id"].startswith("fork-")
    ]
    manifest = {
        "schemaVersion": 1,
        "selectionRule": "every finite MAP-Elites archive entry from each completed matched continuation",
        "evaluationMode": "one deterministic single-domain evaluation per archive entry and case",
        "caseCount": len(CASES),
        "cases": [{"id": case_id, "physicsOverrides": physics} for case_id, physics in CASES],
        "sources": [],
    }
    additions = []
    for source in sources:
        completed = completed_source(repo_root, source)
        if completed is None:
            continue
        checkpoint, summary, count = completed
        source_record = {
            "routeId": source["id"],
            "runName": source["runName"],
            "checkpoint": str(checkpoint.relative_to(repo_root)),
            "checkpointSha256": file_sha256(checkpoint),
            "archiveEntryCount": count,
            "sourceEvaluations": int(summary["evaluations"]),
            "validationRoutes": [],
        }
        for case_index, (case_id, physics) in enumerate(CASES):
            route_id = f"validate-{source['id']}-{case_id}"
            run_name = f"followup-{route_id}"
            config_relative = Path("route-configs") / f"{route_id}.json"
            config_path = experiment_root / config_relative
            if route_id not in by_id:
                generate_case_config(
                    prepare_script,
                    checkpoint,
                    case_id,
                    physics,
                    count,
                    int(source["seed"]) + 1000 + case_index,
                    config_path,
                )
                route = {
                    "id": route_id,
                    "phase": "exhaustive-archive-validation",
                    "config": str(config_path.relative_to(repo_root)),
                    "runName": run_name,
                    "evaluationCap": count,
                    "seed": int(source["seed"]) + 1000 + case_index,
                    "retainFiles": ["trainer.log", "shellworker.log", "summary.json", "config.json"],
                }
                additions.append(route)
                by_id[route_id] = route
            else:
                route = by_id[route_id]
                if not config_path.is_file():
                    raise ValueError(f"Queued validation config is missing: {config_path}")
                if int(route["evaluationCap"]) != count:
                    raise ValueError(f"Queued validation archive count changed for {route_id}")
            source_record["validationRoutes"].append({
                "id": route_id,
                "case": case_id,
                "config": str(config_path.relative_to(repo_root)),
                "configSha256": file_sha256(config_path),
                "evaluationCap": count,
            })
        manifest["sources"].append(source_record)

    if additions:
        routes.extend(additions)
        write_object(routes_path, routes_document)
    manifest["preparedSourceCount"] = len(manifest["sources"])
    manifest["preparedValidationRouteCount"] = sum(len(source["validationRoutes"]) for source in manifest["sources"])
    write_object(experiment_root / "validation-route-manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--experiment-root", type=Path, required=True)
    parser.add_argument(
        "--prepare-script",
        type=Path,
        default=Path(__file__).with_name("prepare-population-robustness.py"),
    )
    args = parser.parse_args()
    manifest = prepare(args.repository.resolve(), args.experiment_root.resolve(), args.prepare_script.resolve())
    print(
        f"Prepared {manifest['preparedValidationRouteCount']} validation routes "
        f"from {manifest['preparedSourceCount']} completed sources."
    )


if __name__ == "__main__":
    main()
