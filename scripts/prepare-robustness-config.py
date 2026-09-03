#!/usr/bin/env python3

import argparse
import copy
import hashlib
import json
import math
import os


def sha256File(path):
	digest = hashlib.sha256()
	with open(path, "rb") as source:
		for block in iter(lambda: source.read(1024 * 1024), b""):
			digest.update(block)
	return digest.hexdigest()


def parsePhysicsOverride(raw):
	if "=" not in raw:
		raise ValueError("Physics overrides must use key=value syntax.")
	key, rawValue = raw.split("=", 1)
	value = float(rawValue)
	if not key or not math.isfinite(value):
		raise ValueError("Physics override key must be non-empty and value must be finite.")
	return key, value


def main():
	parser = argparse.ArgumentParser(description="Prepare a one-creature physics robustness evaluation.")
	parser.add_argument("--checkpoint", required=True)
	parser.add_argument("--case", required=True)
	parser.add_argument("--physics", action="append", default=[])
	parser.add_argument("--seed", required=True, type=int)
	parser.add_argument("--output", required=True)
	args = parser.parse_args()

	with open(args.checkpoint) as source:
		config = json.load(source)
	creatures = config["structure"]["creatures"]
	finite = [
		item for item in creatures
		if item.get("fitness") is not None and math.isfinite(float(item["fitness"]))
	]
	if not finite:
		raise ValueError("Checkpoint has no finite-fitness creature.")
	best = max(finite, key=lambda item: float(item["fitness"]))

	experiment = config.setdefault("experiment", {})
	experiment.pop("trainerState", None)
	experiment["profile"] = "two-hour-robustness-{}".format(args.case)
	experiment["seed"] = args.seed
	physics = experiment.setdefault("physics", {})
	overrides = {}
	for rawOverride in args.physics:
		key, value = parsePhysicsOverride(rawOverride)
		if key not in physics:
			raise ValueError("Unknown physics field: {}".format(key))
		overrides[key] = value
		physics[key] = value
	experiment["robustness"] = {
		"schemaVersion": 1,
		"case": args.case,
		"sourceCheckpoint": {
			"path": os.path.abspath(args.checkpoint),
			"sha256": sha256File(args.checkpoint),
			"fitness": float(best["fitness"]),
		},
		"physicsOverrides": overrides,
	}

	population = config["algorithm"]["arguments"]["population"]
	population.update({ "size": 1, "generation": 0, "evaluations": 0, "checkpointIntervalSeconds": 60 })
	population.pop("eliteCount", None)
	for operation in ("crossover", "mutation"):
		config["algorithm"]["arguments"][operation]["rate"] = 0
		config["algorithm"]["arguments"][operation]["competitionSize"] = {
			"reproduce": 1,
			"eliminate": 1,
		}
	config["structure"]["creatures"] = [{ "fitness": None, "data": copy.deepcopy(best["data"]) }]

	outputDirectory = os.path.dirname(os.path.abspath(args.output))
	os.makedirs(outputDirectory, exist_ok=True)
	temporary = args.output + ".tmp"
	with open(temporary, "w") as destination:
		json.dump(config, destination, indent=1, allow_nan=False)
		destination.write("\n")
		destination.flush()
		os.fsync(destination.fileno())
	os.replace(temporary, args.output)
	print("Prepared robustness case {} with overrides {}.".format(args.case, overrides))


if __name__ == "__main__":
	main()
