#!/usr/bin/env python3
"""Create matched R3/R5 continuation banks from one MAP-Elites checkpoint."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def read_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def write_object(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def selected_bank(checkpoint: dict) -> tuple[list[dict], dict]:
    if checkpoint.get("algorithm", {}).get("type") != "MapElites":
        raise ValueError("Source checkpoint must use MapElites")
    population = checkpoint["algorithm"]["arguments"]["population"]
    target = int(population["size"])
    stored = checkpoint.get("structure", {}).get("creatures")
    if not isinstance(stored, list) or len(stored) < target:
        raise ValueError("Source checkpoint does not contain the configured bank target")

    selected = copy.deepcopy(stored[:target])
    omitted = copy.deepcopy(stored[target:])
    omitted_finite = [entry for entry in omitted if entry.get("fitness") is not None]
    if omitted_finite:
        raise ValueError("A finite archive elite occurs after the configured bank target")
    for entry in selected:
        if not isinstance(entry.get("data"), dict):
            raise ValueError("Every bank entry must contain opaque controller data")
        entry["fitness"] = None
        entry.pop("evaluation", None)

    state = checkpoint.get("experiment", {}).get("trainerState", {})
    if "pythonRandomState" not in state:
        raise ValueError("Source checkpoint has no saved Python RNG state")
    clean_state = {
        "schemaVersion": 1,
        "pythonRandomState": copy.deepcopy(state["pythonRandomState"]),
        "bestFitnessEvaluation": 0,
        "domainProgress": {},
        "evaluationHistory": [],
        "evaluationSimulations": 0,
    }
    return selected, omitted, clean_state


def prepare_pair(checkpoint: dict, seed: int) -> tuple[dict, dict, dict]:
    selected, omitted, clean_state = selected_bank(checkpoint)
    base = copy.deepcopy(checkpoint)
    population = base["algorithm"]["arguments"]["population"]
    population["generation"] = 0
    population["evaluations"] = 0
    base["algorithm"]["arguments"]["mutation"].pop("adaptiveSelector", None)
    base["structure"]["creatures"] = selected
    base["experiment"]["seed"] = seed
    base["experiment"]["trainerState"] = clean_state
    base["experiment"].pop("overnightRoute", None)
    base["experiment"].pop("followupRoute", None)

    r3 = copy.deepcopy(base)
    r5 = copy.deepcopy(base)
    r3_id = f"fork-R3-{seed}"
    r5_id = f"fork-R5-{seed}"
    for config, route_id, room in ((r3, r3_id, "R3"), (r5, r5_id, "R5")):
        config["experiment"]["profile"] = route_id
        config["experiment"]["followupFork"] = {
            "schemaVersion": 1,
            "id": route_id,
            "sourceWarmup": f"warmup-R3-{seed}",
            "room": room,
        }
    r5["experiment"]["evaluationDomains"] = copy.deepcopy(r3["experiment"]["evaluationDomains"])
    r5["experiment"]["evaluationDomains"].extend([
        {"id": "gravity-99", "physics": {"gravityZ": -99}},
        {"id": "gravity-101", "physics": {"gravityZ": -101}},
    ])

    data = [entry["data"] for entry in selected]
    ids = [entry["data"].get("metadata", {}).get("creatureId") for entry in selected]
    morphologies = [entry["data"].get("metadata", {}).get("morphologyId") for entry in selected]
    pair = {
        "schemaVersion": 1,
        "seed": seed,
        "sourceStoredControllerCount": len(checkpoint["structure"]["creatures"]),
        "storedControllerBankCount": len(selected),
        "sourceFiniteArchiveEntries": sum(
            entry.get("fitness") is not None for entry in checkpoint["structure"]["creatures"]
        ),
        "selectionRule": "first configured population.size entries in saved order; fail if this omits a finite archive elite",
        "omittedPendingControllerCount": len(omitted),
        "omittedPendingControllerPayloadSha256": digest([entry["data"] for entry in omitted]),
        "canonicalControllerPayloadSha256": digest(data),
        "orderedCreatureIdsSha256": digest(ids),
        "orderedMorphologyIdsSha256": digest(morphologies),
        "pythonRandomStateSha256": digest(clean_state["pythonRandomState"]),
        "r3EvaluationDomainsSha256": digest(r3["experiment"]["evaluationDomains"]),
        "r5EvaluationDomainsSha256": digest(r5["experiment"]["evaluationDomains"]),
    }
    return r3, r5, pair


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--output-r3", type=Path, required=True)
    parser.add_argument("--output-r5", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    r3, r5, manifest = prepare_pair(read_object(args.source), args.seed)
    write_object(args.output_r3, r3)
    write_object(args.output_r5, r5)
    manifest["source"] = str(args.source)
    manifest["r3"] = str(args.output_r3)
    manifest["r5"] = str(args.output_r5)
    write_object(args.manifest, manifest)


if __name__ == "__main__":
    main()
