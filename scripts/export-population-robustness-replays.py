#!/usr/bin/env python3

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path


def canonical_sha256(value):
	return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def write_json_atomic(path, value):
	path.parent.mkdir(parents=True, exist_ok=True)
	temporary = path.with_name(path.name + ".tmp")
	with temporary.open("w", encoding="utf-8") as destination:
		json.dump(value, destination, indent=2, allow_nan=False)
		destination.write("\n")
		destination.flush()
		os.fsync(destination.fileno())
	os.replace(temporary, path)


def export_replays(source_path, result_path, output_directory):
	with source_path.open(encoding="utf-8") as source:
		source_config = json.load(source)
	with result_path.open(encoding="utf-8") as source:
		result_config = json.load(source)
	source_metadata = source_config["experiment"]["populationRobustness"]
	result_metadata = result_config["experiment"]["populationRobustness"]
	if source_metadata["candidates"] != result_metadata["candidates"]:
		raise ValueError("Source and result candidate metadata do not match.")
	candidate_ids = [item.get("creatureId") for item in source_metadata["candidates"]]
	if any(not isinstance(creature_id, str) or not creature_id for creature_id in candidate_ids):
		raise ValueError("Every candidate must have a non-empty creature ID.")
	if len(set(candidate_ids)) != len(candidate_ids):
		raise ValueError("Candidate metadata contains duplicate creature IDs.")

	source_ids = [item["data"]["metadata"].get("creatureId") for item in source_config["structure"]["creatures"]]
	if len(set(source_ids)) != len(source_ids):
		raise ValueError("Source config contains duplicate creature IDs.")
	source_by_id = {
		item["data"]["metadata"]["creatureId"]: item
		for item in source_config["structure"]["creatures"]
	}
	history_by_id = {}
	for item in result_config["experiment"]["trainerState"]["evaluationHistory"]:
		creature_id = item.get("creatureId")
		if creature_id not in history_by_id:
			history_by_id[creature_id] = item

	experiment = copy.deepcopy(result_config["experiment"])
	experiment.pop("trainerState", None)
	manifest_candidates = []
	for candidate in source_metadata["candidates"]:
		index = candidate["index"]
		creature_id = candidate["creatureId"]
		if creature_id not in source_by_id or creature_id not in history_by_id:
			raise ValueError("Missing source or evaluated candidate {}.".format(creature_id))
		source_entry = source_by_id[creature_id]
		if canonical_sha256(source_entry["data"]) != candidate["creatureSha256"]:
			raise ValueError("Candidate hash mismatch for {}.".format(creature_id))
		evaluation = history_by_id[creature_id]
		fitness = evaluation.get("robustFitness")
		if fitness is None or not math.isfinite(float(fitness)):
			raise ValueError("Candidate fitness must be finite for {}.".format(creature_id))
		entry = copy.deepcopy(source_entry)
		entry["fitness"] = float(fitness)
		entry["evaluation"] = {
			"behavior": copy.deepcopy(evaluation.get("behavior", {})),
			"domainScores": copy.deepcopy(evaluation.get("domainScores", [float(fitness)])),
		}
		name = "candidate-{:02d}-{}.json".format(index, candidate["creatureSha256"][:16])
		replay_config = {
			"schemaVersion": 1,
			"kind": "machine-evolved-population-robustness-replay-config-v1",
			"algorithm": {"type": result_config["algorithm"]["type"]},
			"selectionProvenance": {
				"schemaVersion": 1,
				"case": source_metadata["case"],
				"sourceIndex": index,
				"sourceCreatureId": creature_id,
				"sourceCreatureSha256": candidate["creatureSha256"],
				"sourceBaselineFitness": candidate["baselineFitness"],
				"evaluatedFitness": float(fitness),
			},
			"experiment": copy.deepcopy(experiment),
			"structure": {"creatures": [entry]},
		}
		write_json_atomic(output_directory / "configs" / name, replay_config)
		manifest_candidates.append({
			"index": index,
			"creatureId": creature_id,
			"creatureSha256": candidate["creatureSha256"],
			"baselineFitness": candidate["baselineFitness"],
			"evaluatedFitness": float(fitness),
			"config": "configs/{}".format(name),
		})
	manifest = {
		"schemaVersion": 1,
		"case": source_metadata["case"],
		"candidateCount": len(manifest_candidates),
		"physicsSha256": canonical_sha256(experiment["physics"]),
		"objectiveSha256": canonical_sha256(experiment["objective"]),
		"evaluationDomainsSha256": canonical_sha256(experiment.get("evaluationDomains", [])),
		"candidates": manifest_candidates,
	}
	write_json_atomic(output_directory / "selection-manifest.json", manifest)
	return manifest


def main():
	parser = argparse.ArgumentParser(description="Export ID-bound population robustness replay configs.")
	parser.add_argument("--source-config", required=True, type=Path)
	parser.add_argument("--result-config", required=True, type=Path)
	parser.add_argument("--output-dir", required=True, type=Path)
	args = parser.parse_args()
	manifest = export_replays(args.source_config, args.result_config, args.output_dir)
	print("Exported {} replay configs for case {}.".format(manifest["candidateCount"], manifest["case"]))


if __name__ == "__main__":
	main()
