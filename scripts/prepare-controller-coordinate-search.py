#!/usr/bin/env python3

import argparse
import copy
import json
import math
import os


def loadBest(path):
	with open(path) as source:
		document = json.load(source)
	if "motorController" in document and "structure" in document:
		return document, None
	finite = [
		item for item in document.get("structure", {}).get("creatures", [])
		if item.get("fitness") is not None and math.isfinite(float(item["fitness"]))
	]
	if not finite:
		raise ValueError("Input has no finite-fitness creature.")
	item = max(finite, key=lambda creature: float(creature["fitness"]))
	return item["data"], float(item["fitness"])


def changedCoordinates(source, target):
	coordinates = []
	for layerIndex, (sourceLayer, targetLayer) in enumerate(zip(
		source["motorController"]["layers"],
		target["motorController"]["layers"],
	)):
		for key in ("weights", "biases"):
			for parameterIndex, (sourceValue, targetValue) in enumerate(zip(sourceLayer[key], targetLayer[key])):
				if sourceValue != targetValue:
					coordinates.append({
						"layer": layerIndex,
						"key": key,
						"index": parameterIndex,
						"sourceValue": sourceValue,
						"targetValue": targetValue,
					})
	return coordinates


def main():
	parser = argparse.ArgumentParser(description="Prepare single-coordinate controller probes.")
	parser.add_argument("--template", required=True)
	parser.add_argument("--source", required=True)
	parser.add_argument("--target", required=True)
	parser.add_argument("--target-fitness", required=True, type=float)
	parser.add_argument("--revert", action="store_true")
	parser.add_argument("--additive-step", action="append", type=float, default=[])
	parser.add_argument("--seed", required=True, type=int)
	parser.add_argument("--output", required=True)
	args = parser.parse_args()
	if not args.revert and not args.additive_step:
		raise ValueError("Specify --revert, at least one --additive-step, or both.")

	with open(args.template) as sourceFile:
		config = json.load(sourceFile)
	source, _ = loadBest(args.source)
	target, detectedFitness = loadBest(args.target)
	if source["structure"] != target["structure"]:
		raise ValueError("Coordinate-search endpoints must have identical morphology.")
	if detectedFitness is not None and not math.isclose(detectedFitness, args.target_fitness, rel_tol=0, abs_tol=1e-9):
		raise ValueError("Supplied target fitness does not match checkpoint best fitness.")
	coordinates = changedCoordinates(source, target)
	if not coordinates:
		raise ValueError("Coordinate-search endpoints have identical controllers.")

	variants = []
	creatures = [{ "fitness": args.target_fitness, "data": copy.deepcopy(target) }]
	for coordinateIndex, coordinate in enumerate(coordinates):
		probes = []
		if args.revert:
			probes.append(("revert", coordinate["sourceValue"]))
		for step in args.additive_step:
			if not math.isfinite(step) or step == 0:
				raise ValueError("Additive steps must be finite and non-zero.")
			probes.append(("additive", coordinate["targetValue"] + step))
		for operation, value in probes:
			creature = copy.deepcopy(target)
			creature["motorController"]["layers"][coordinate["layer"]][coordinate["key"]][coordinate["index"]] = value
			creatures.append({ "fitness": None, "data": creature })
			variants.append({
				"coordinateIndex": coordinateIndex,
				"layer": coordinate["layer"],
				"key": coordinate["key"],
				"index": coordinate["index"],
				"operation": operation,
				"value": value,
				"deltaFromTarget": value - coordinate["targetValue"],
			})

	experiment = config.setdefault("experiment", {})
	experiment.pop("trainerState", None)
	experiment["profile"] = "two-hour-controller-coordinate-search-seed{}".format(args.seed)
	experiment["seed"] = args.seed
	experiment["coordinateSearch"] = {
		"schemaVersion": 1,
		"targetFitness": args.target_fitness,
		"changedCoordinateCount": len(coordinates),
		"variants": variants,
	}
	population = config["algorithm"]["arguments"]["population"]
	population.update({ "size": len(creatures), "generation": 0, "evaluations": 0, "checkpointIntervalSeconds": 60 })
	population.pop("eliteCount", None)
	for operation in ("crossover", "mutation"):
		config["algorithm"]["arguments"][operation]["rate"] = 0
		config["algorithm"]["arguments"][operation]["competitionSize"] = { "reproduce": 1, "eliminate": 1 }
	config["structure"]["creatures"] = creatures

	outputDirectory = os.path.dirname(os.path.abspath(args.output))
	os.makedirs(outputDirectory, exist_ok=True)
	temporary = args.output + ".tmp"
	with open(temporary, "w") as destination:
		json.dump(config, destination, separators=(",", ":"), allow_nan=False)
		destination.write("\n")
		destination.flush()
		os.fsync(destination.fileno())
	os.replace(temporary, args.output)
	print("Prepared {} probes across {} changed coordinates.".format(len(variants), len(coordinates)))


if __name__ == "__main__":
	main()
