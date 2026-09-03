#!/usr/bin/env python3

import argparse
import copy
import hashlib
import json
import math
import os


def loadJson(path):
	with open(path) as source:
		return json.load(source)


def bestCreature(document):
	if "motorController" in document and "structure" in document:
		return document, None
	creatures = document.get("structure", {}).get("creatures", [])
	finite = [
		item for item in creatures
		if item.get("fitness") is not None and math.isfinite(float(item["fitness"]))
	]
	if not finite:
		raise ValueError("Checkpoint does not contain a finite-fitness creature.")
	item = max(finite, key=lambda creature: float(creature["fitness"]))
	return item["data"], float(item["fitness"])


def sha256File(path):
	digest = hashlib.sha256()
	with open(path, "rb") as source:
		for block in iter(lambda: source.read(1024 * 1024), b""):
			digest.update(block)
	return digest.hexdigest()


def controllerAtCoefficient(source, target, coefficient):
	creature = copy.deepcopy(source)
	for sourceLayer, targetLayer, outputLayer in zip(
		source["motorController"]["layers"],
		target["motorController"]["layers"],
		creature["motorController"]["layers"],
	):
		for key in ("weights", "biases"):
			if len(sourceLayer[key]) != len(targetLayer[key]):
				raise ValueError("Source and target controller shapes differ.")
			outputLayer[key] = [
				sourceValue + coefficient * (targetValue - sourceValue)
				for sourceValue, targetValue in zip(sourceLayer[key], targetLayer[key])
			]
	return creature


def main():
	parser = argparse.ArgumentParser(description="Prepare a fixed-direction controller line search.")
	parser.add_argument("--template", required=True)
	parser.add_argument("--source", required=True)
	parser.add_argument("--target", required=True)
	parser.add_argument("--target-fitness", required=True, type=float)
	parser.add_argument("--minimum-coefficient", required=True, type=float)
	parser.add_argument("--maximum-coefficient", required=True, type=float)
	parser.add_argument("--population", default=512, type=int)
	parser.add_argument("--seed", required=True, type=int)
	parser.add_argument("--output", required=True)
	args = parser.parse_args()

	if args.population < 3:
		raise ValueError("Population must include the target plus at least two measured samples.")
	if args.maximum_coefficient <= args.minimum_coefficient:
		raise ValueError("Maximum coefficient must exceed minimum coefficient.")
	if not math.isfinite(args.target_fitness):
		raise ValueError("Target fitness must be finite.")

	config = loadJson(args.template)
	source, _ = bestCreature(loadJson(args.source))
	target, detectedTargetFitness = bestCreature(loadJson(args.target))
	if source["structure"] != target["structure"]:
		raise ValueError("Line-search endpoints must have identical morphology.")
	if detectedTargetFitness is not None and not math.isclose(
		detectedTargetFitness,
		args.target_fitness,
		rel_tol=0,
		abs_tol=1e-9,
	):
		raise ValueError("Supplied target fitness does not match checkpoint best fitness.")

	changedParameters = 0
	for sourceLayer, targetLayer in zip(
		source["motorController"]["layers"],
		target["motorController"]["layers"],
	):
		for key in ("weights", "biases"):
			changedParameters += sum(
				1 for sourceValue, targetValue in zip(sourceLayer[key], targetLayer[key])
				if sourceValue != targetValue
			)
	if changedParameters == 0:
		raise ValueError("Line-search endpoints have identical controllers.")

	experiment = config.setdefault("experiment", {})
	experiment.pop("trainerState", None)
	experiment["profile"] = "two-hour-controller-line-search-seed{}".format(args.seed)
	experiment["seed"] = args.seed
	experiment["lineSearch"] = {
		"schemaVersion": 1,
		"source": { "path": os.path.abspath(args.source), "sha256": sha256File(args.source) },
		"target": {
			"path": os.path.abspath(args.target),
			"sha256": sha256File(args.target),
			"fitness": args.target_fitness,
		},
		"minimumCoefficient": args.minimum_coefficient,
		"maximumCoefficient": args.maximum_coefficient,
		"changedParameters": changedParameters,
	}

	arguments = config["algorithm"]["arguments"]
	arguments["population"].update({
		"size": args.population,
		"generation": 0,
		"evaluations": 0,
		"eliteCount": 1,
		"checkpointIntervalSeconds": 60,
	})
	arguments["crossover"]["rate"] = 0
	arguments["crossover"]["competitionSize"] = { "reproduce": 1, "eliminate": 1 }
	arguments["mutation"]["rate"] = 0
	arguments["mutation"]["competitionSize"] = { "reproduce": 1, "eliminate": 1 }

	measuredCount = args.population - 1
	coefficients = [
		args.minimum_coefficient + (args.maximum_coefficient - args.minimum_coefficient) * index / (measuredCount - 1)
		for index in range(measuredCount)
	]
	experiment["lineSearch"]["measuredCoefficients"] = coefficients
	config["structure"]["creatures"] = [{ "fitness": args.target_fitness, "data": target }]
	config["structure"]["creatures"].extend(
		{ "fitness": None, "data": controllerAtCoefficient(source, target, coefficient) }
		for coefficient in coefficients
	)

	outputDirectory = os.path.dirname(os.path.abspath(args.output))
	os.makedirs(outputDirectory, exist_ok=True)
	temporary = args.output + ".tmp"
	with open(temporary, "w") as destination:
		json.dump(config, destination, separators=(",", ":"), allow_nan=False)
		destination.write("\n")
		destination.flush()
		os.fsync(destination.fileno())
	os.replace(temporary, args.output)
	print("Prepared {} measured coefficients across [{}, {}]; {} controller parameters define the direction.".format(
		measuredCount,
		args.minimum_coefficient,
		args.maximum_coefficient,
		changedParameters,
	))


if __name__ == "__main__":
	main()
