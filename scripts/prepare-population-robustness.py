#!/usr/bin/env python3

import argparse
import copy
import hashlib
import json
import math
import os


def canonicalSha256(value):
	return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def parsePhysicsOverride(raw):
	if "=" not in raw:
		raise ValueError("Physics overrides must use key=value syntax.")
	key, rawValue = raw.split("=", 1)
	value = float(rawValue)
	if not key or not math.isfinite(value):
		raise ValueError("Physics override key must be non-empty and value must be finite.")
	return key, value


def main():
	parser = argparse.ArgumentParser(description="Prepare a top-population robustness evaluation.")
	parser.add_argument("--checkpoint", required=True)
	parser.add_argument("--case", required=True)
	parser.add_argument("--top", type=int, default=64)
	parser.add_argument("--physics", action="append", default=[])
	parser.add_argument(
		"--single-domain",
		action="store_true",
		help="replace the training-domain ring with one nominal domain for an isolated holdout case",
	)
	parser.add_argument("--seed", required=True, type=int)
	parser.add_argument("--output", required=True)
	args = parser.parse_args()

	with open(args.checkpoint) as source:
		config = json.load(source)
	finite = [
		copy.deepcopy(item) for item in config["structure"]["creatures"]
		if item.get("fitness") is not None and math.isfinite(float(item["fitness"]))
	]
	finite.sort(key=lambda item: float(item["fitness"]), reverse=True)
	selected = finite[:args.top]
	if len(selected) != args.top:
		raise ValueError("Checkpoint does not contain the requested number of finite creatures.")

	experiment = config.setdefault("experiment", {})
	experiment.pop("trainerState", None)
	experiment["profile"] = "two-hour-population-robustness-{}".format(args.case)
	experiment["seed"] = args.seed
	sourceDomains = copy.deepcopy(experiment.get("evaluationDomains", []))
	physics = experiment.setdefault("physics", {})
	overrides = {}
	for rawOverride in args.physics:
		key, value = parsePhysicsOverride(rawOverride)
		if key not in physics:
			raise ValueError("Unknown physics field: {}".format(key))
		overrides[key] = value
		physics[key] = value
	robustnessMetadata = {
		"schemaVersion": 1,
		"case": args.case,
		"selectionRule": "top-baseline-fitness-v1",
		"physicsOverrides": overrides,
		"candidates": [
			{
				"index": index,
				"baselineFitness": float(item["fitness"]),
				"creatureSha256": canonicalSha256(item["data"]),
			}
			for index, item in enumerate(selected)
		],
	}
	if args.single_domain:
		experiment["evaluationDomains"] = [{ "id": args.case, "physics": {} }]
		robustnessMetadata.update({
			"evaluationMode": "single-domain-v1",
			"sourceEvaluationDomainsSha256": canonicalSha256(sourceDomains),
		})
	experiment["populationRobustness"] = robustnessMetadata

	population = config["algorithm"]["arguments"]["population"]
	population.update({ "size": args.top, "generation": 0, "evaluations": 0, "checkpointIntervalSeconds": 60 })
	population.pop("eliteCount", None)
	for operation in ("crossover", "mutation"):
		config["algorithm"]["arguments"][operation]["rate"] = 0
		config["algorithm"]["arguments"][operation]["competitionSize"] = {
			"reproduce": 1,
			"eliminate": 1,
		}
	config["structure"]["creatures"] = [
		{ "fitness": None, "data": item["data"] }
		for item in selected
	]

	outputDirectory = os.path.dirname(os.path.abspath(args.output))
	os.makedirs(outputDirectory, exist_ok=True)
	temporary = args.output + ".tmp"
	with open(temporary, "w") as destination:
		json.dump(config, destination, separators=(",", ":"), allow_nan=False)
		destination.write("\n")
		destination.flush()
		os.fsync(destination.fileno())
	os.replace(temporary, args.output)
	print("Prepared {} top candidates for robustness case {}.".format(args.top, args.case))


if __name__ == "__main__":
	main()
