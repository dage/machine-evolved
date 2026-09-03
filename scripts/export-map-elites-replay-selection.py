#!/usr/bin/env python3
"""Export deterministic, integrity-bound replay inputs from a MAP-Elites checkpoint."""

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path


SELECTION_RULE = "fitness-desc-morphology-id-creature-id-v1"


def sha256_bytes(value):
	return hashlib.sha256(value).hexdigest()


def sha256_file(path):
	digest = hashlib.sha256()
	with path.open("rb") as source:
		for block in iter(lambda: source.read(1024 * 1024), b""):
			digest.update(block)
	return digest.hexdigest()


def canonical_sha256(value):
	serialized = json.dumps(
		value,
		sort_keys=True,
		separators=(",", ":"),
		ensure_ascii=False,
		allow_nan=False,
	).encode("utf-8")
	return sha256_bytes(serialized)


def required_identifier(value, description):
	if not isinstance(value, str) or not value:
		raise ValueError("Every finite MAP-Elites creature requires a non-empty {}.".format(description))
	return value


def finite_fitness(value):
	if isinstance(value, bool) or value is None:
		return None
	try:
		fitness = float(value)
	except (TypeError, ValueError, OverflowError):
		return None
	return fitness if math.isfinite(fitness) else None


def load_candidates(checkpoint):
	if not isinstance(checkpoint, dict):
		raise ValueError("Checkpoint root must be an object.")
	algorithm = checkpoint.get("algorithm", {})
	if not isinstance(algorithm, dict) or algorithm.get("type") != "MapElites":
		raise ValueError("Checkpoint algorithm.type must be 'MapElites'.")

	try:
		creatures = checkpoint["structure"]["creatures"]
	except (KeyError, TypeError):
		raise ValueError("Checkpoint must contain structure.creatures.") from None
	if not isinstance(creatures, list):
		raise ValueError("Checkpoint structure.creatures must be a list.")

	candidates = []
	creature_ids = set()
	for entry in creatures:
		if not isinstance(entry, dict):
			continue
		fitness = finite_fitness(entry.get("fitness"))
		if fitness is None:
			continue
		data = entry.get("data")
		if not isinstance(data, dict):
			raise ValueError("Every finite MAP-Elites creature requires object-valued data.")
		metadata = data.get("metadata", {})
		if not isinstance(metadata, dict):
			raise ValueError("Every finite MAP-Elites creature requires object-valued data.metadata.")
		morphology_id = required_identifier(metadata.get("morphologyId"), "morphology ID")
		creature_id = required_identifier(metadata.get("creatureId"), "creature ID")
		if creature_id in creature_ids:
			raise ValueError("Finite MAP-Elites creature IDs must be unique: {}".format(creature_id))
		creature_ids.add(creature_id)
		candidates.append({
			"entry": entry,
			"fitness": fitness,
			"morphologyId": morphology_id,
			"creatureId": creature_id,
			"creatureSha256": canonical_sha256(data),
		})

	if not candidates:
		raise ValueError("Checkpoint has no finite-fitness MAP-Elites creatures.")

	candidates.sort(key=lambda candidate: (
		-candidate["fitness"],
		candidate["morphologyId"],
		candidate["creatureId"],
	))
	for rank, candidate in enumerate(candidates, 1):
		candidate["overallRank"] = rank

	by_morphology = {}
	for candidate in candidates:
		by_morphology.setdefault(candidate["morphologyId"], []).append(candidate)
	for morphology_candidates in by_morphology.values():
		for rank, candidate in enumerate(morphology_candidates, 1):
			candidate["morphologyRank"] = rank
	return candidates, by_morphology


def first_domain_id(experiment):
	domains = experiment.get("evaluationDomains", [])
	if isinstance(domains, list) and domains:
		first = domains[0]
		if isinstance(first, dict) and isinstance(first.get("id"), str) and first["id"]:
			return first["id"]
	return "nominal"


def expected_replay_fitness(candidate):
	evaluation = candidate["entry"].get("evaluation", {})
	domain_scores = evaluation.get("domainScores", []) if isinstance(evaluation, dict) else []
	if isinstance(domain_scores, list) and domain_scores:
		replay_fitness = finite_fitness(domain_scores[0])
		if replay_fitness is None:
			raise ValueError(
				"First domain score must be finite for creature {}.".format(candidate["creatureId"])
			)
		return replay_fitness
	return candidate["fitness"]


def public_candidate(candidate, config_path, config_sha256, selected_overall):
	evaluation = candidate["entry"].get("evaluation", {})
	domain_scores = evaluation.get("domainScores", []) if isinstance(evaluation, dict) else []
	return {
		"config": {
			"path": config_path,
			"sha256": config_sha256,
		},
		"sourceOverallRank": candidate["overallRank"],
		"sourceMorphologyRank": candidate["morphologyRank"],
		"selectedOverall": selected_overall,
		"morphologyId": candidate["morphologyId"],
		"fitness": candidate["fitness"],
		"creatureId": candidate["creatureId"],
		"creatureSha256": candidate["creatureSha256"],
		"sourceDomainScores": copy.deepcopy(domain_scores),
		"expectedReplayFitness": expected_replay_fitness(candidate),
	}


def write_json_atomic(path, value):
	path.parent.mkdir(parents=True, exist_ok=True)
	serialized = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
	temporary = path.with_name(path.name + ".tmp")
	with temporary.open("w", encoding="utf-8") as destination:
		destination.write(serialized)
		destination.flush()
		os.fsync(destination.fileno())
	os.replace(temporary, path)


def export_selection(checkpoint_path, output_directory, top=4):
	checkpoint_path = Path(checkpoint_path).resolve()
	output_directory = Path(output_directory).resolve()
	if top < 1:
		raise ValueError("--top must be a positive integer.")

	with checkpoint_path.open(encoding="utf-8") as source:
		checkpoint = json.load(source)
	candidates, by_morphology = load_candidates(checkpoint)
	try:
		experiment = checkpoint["experiment"]
	except (KeyError, TypeError):
		raise ValueError("Checkpoint must contain experiment configuration.") from None
	if not isinstance(experiment, dict):
		raise ValueError("Checkpoint experiment configuration must be an object.")
	for field in ("physics", "objective"):
		if not isinstance(experiment.get(field), dict):
			raise ValueError("Checkpoint experiment.{} must be an object.".format(field))
	if "evaluationDomains" in experiment and not isinstance(experiment["evaluationDomains"], list):
		raise ValueError("Checkpoint experiment.evaluationDomains must be a list.")

	checkpoint_sha256 = sha256_file(checkpoint_path)
	selected_overall = candidates[:top]
	selected_overall_ids = {candidate["creatureId"] for candidate in selected_overall}
	selected_ids = set(selected_overall_ids)
	for morphology_id in sorted(by_morphology):
		selected_ids.update(candidate["creatureId"] for candidate in by_morphology[morphology_id][:top])
	selected = [candidate for candidate in candidates if candidate["creatureId"] in selected_ids]

	manifest_candidates = []
	public_by_id = {}
	for candidate in selected:
		config_name = "rank-{:06d}-{}.json".format(
			candidate["overallRank"], candidate["creatureSha256"][:16])
		relative_path = "configs/{}".format(config_name)
		provenance = {
			"schemaVersion": 1,
			"sourceCheckpointSha256": checkpoint_sha256,
			"sourceOverallRank": candidate["overallRank"],
			"sourceMorphologyRank": candidate["morphologyRank"],
			"sourceMorphologyId": candidate["morphologyId"],
			"sourceFitness": candidate["fitness"],
			"sourceCreatureId": candidate["creatureId"],
			"sourceCreatureSha256": candidate["creatureSha256"],
		}
		replay_experiment = copy.deepcopy(experiment)
		replay_experiment.pop("trainerState", None)
		replay_config = {
			"schemaVersion": 1,
			"kind": "machine-evolved-map-elites-replay-config-v1",
			"algorithm": {"type": "MapElites"},
			"selectionProvenance": provenance,
			"experiment": replay_experiment,
			"structure": {"creatures": [copy.deepcopy(candidate["entry"])]},
		}
		config_path = output_directory / relative_path
		write_json_atomic(config_path, replay_config)
		config_sha256 = sha256_file(config_path)
		public = public_candidate(
			candidate,
			relative_path,
			config_sha256,
			candidate["creatureId"] in selected_overall_ids,
		)
		manifest_candidates.append(public)
		public_by_id[candidate["creatureId"]] = public

	contract = {
		"physicsSha256": canonical_sha256(experiment["physics"]),
		"objectiveSha256": canonical_sha256(experiment["objective"]),
		"evaluationDomainsSha256": canonical_sha256(experiment.get("evaluationDomains", [])),
		"firstReplayDomainId": first_domain_id(experiment),
	}
	manifest = {
		"schemaVersion": 1,
		"kind": "machine-evolved-map-elites-replay-selection-v1",
		"sourceCheckpoint": {
			"fileName": checkpoint_path.name,
			"sha256": checkpoint_sha256,
		},
		"selection": {
			"rule": SELECTION_RULE,
			"rankBase": 1,
			"topOverall": top,
			"topPerMorphology": top,
			"finiteCandidateCount": len(candidates),
			"exportedUniqueCandidateCount": len(selected),
		},
		"replayContract": contract,
		"candidates": manifest_candidates,
		"topOverall": [
			public_by_id[candidate["creatureId"]]
			for candidate in selected_overall
		],
		"topPerMorphology": [
			{
				"morphologyId": morphology_id,
				"candidates": [
					public_by_id[candidate["creatureId"]]
					for candidate in by_morphology[morphology_id][:top]
				],
			}
			for morphology_id in sorted(by_morphology)
		],
	}
	manifest_path = output_directory / "selection-manifest.json"
	write_json_atomic(manifest_path, manifest)
	return manifest


def main():
	parser = argparse.ArgumentParser(
		description="Export top MAP-Elites creatures as compact replay configs plus a parity manifest."
	)
	parser.add_argument("--checkpoint", required=True, type=Path)
	parser.add_argument("--output-dir", required=True, type=Path)
	parser.add_argument("--top", type=int, default=4)
	args = parser.parse_args()

	manifest = export_selection(args.checkpoint, args.output_dir, args.top)
	print(
		"Exported {} unique replay configs and selection-manifest.json.".format(
			manifest["selection"]["exportedUniqueCandidateCount"]
		)
	)


if __name__ == "__main__":
	main()
