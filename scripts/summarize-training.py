#!/usr/bin/env python3

import argparse
import datetime
import json
import math
import os


def main():
	parser = argparse.ArgumentParser(description="Summarize a completed Machine Evolved run.")
	parser.add_argument("--config", required=True)
	parser.add_argument("--output", required=True)
	parser.add_argument("--workers", required=True, type=int)
	args = parser.parse_args()

	with open(args.config) as source:
		config = json.load(source)

	experiment = config.get("experiment", {})
	population = config["algorithm"]["arguments"]["population"]
	creatures = config["structure"]["creatures"]
	fitnesses = [
		float(creature["fitness"])
		for creature in creatures
		if math.isfinite(float(creature["fitness"]))
	]
	summary = {
		"schemaVersion": 1,
		"status": "completed",
		"completedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
		"backend": experiment.get("backend"),
		"profile": experiment.get("profile"),
		"seed": experiment.get("seed"),
		"workers": args.workers,
		"populationSize": population["size"],
		"generation": population["generation"],
		"evaluations": population["evaluations"],
		"evaluatedCreatures": len(fitnesses),
		"bestFitness": max(fitnesses) if fitnesses else None,
		"averageFitness": sum(fitnesses) / len(fitnesses) if fitnesses else None,
		"objective": experiment.get("objective"),
		"physics": experiment.get("physics"),
	}

	temporary = args.output + ".tmp"
	with open(temporary, "w") as destination:
		json.dump(summary, destination, indent=2)
		destination.write("\n")
		destination.flush()
		os.fsync(destination.fileno())
	os.replace(temporary, args.output)
	print(json.dumps(summary, indent=2))


if __name__ == "__main__":
	main()
