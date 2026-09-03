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


def main():
	parser = argparse.ArgumentParser(description="Extract a compact, replayable best-creature config.")
	parser.add_argument("--checkpoint", required=True)
	parser.add_argument("--profile", required=True)
	parser.add_argument("--rank", type=int, default=0)
	parser.add_argument("--output", required=True)
	args = parser.parse_args()

	with open(args.checkpoint) as source:
		config = json.load(source)
	finite = [
		item for item in config["structure"]["creatures"]
		if item.get("fitness") is not None and math.isfinite(float(item["fitness"]))
	]
	if not finite:
		raise ValueError("Checkpoint has no finite-fitness creature.")
	finite.sort(key=lambda item: float(item["fitness"]), reverse=True)
	if args.rank < 0 or args.rank >= len(finite):
		raise ValueError("Rank is outside the finite checkpoint population.")
	best = copy.deepcopy(finite[args.rank])

	experiment = config.setdefault("experiment", {})
	experiment.pop("trainerState", None)
	experiment["profile"] = args.profile
	experiment["extractedChampion"] = {
		"schemaVersion": 1,
		"sourceCheckpoint": os.path.relpath(os.path.abspath(args.checkpoint), os.path.dirname(os.path.abspath(args.output))),
		"sourceCheckpointSha256": sha256File(args.checkpoint),
		"fitness": float(best["fitness"]),
		"sourceFitnessRank": args.rank,
	}

	population = config["algorithm"]["arguments"]["population"]
	population.update({ "size": 1, "generation": 0, "evaluations": 0 })
	population.pop("eliteCount", None)
	for operation in ("crossover", "mutation"):
		config["algorithm"]["arguments"][operation]["rate"] = 0
		config["algorithm"]["arguments"][operation]["competitionSize"] = {
			"reproduce": 1,
			"eliminate": 1,
		}
	config["structure"]["creatures"] = [best]

	outputDirectory = os.path.dirname(os.path.abspath(args.output))
	os.makedirs(outputDirectory, exist_ok=True)
	temporary = args.output + ".tmp"
	with open(temporary, "w") as destination:
		json.dump(config, destination, indent=1, allow_nan=False)
		destination.write("\n")
		destination.flush()
		os.fsync(destination.fileno())
	os.replace(temporary, args.output)
	print("Extracted fitness {} to {}.".format(best["fitness"], args.output))


if __name__ == "__main__":
	main()
