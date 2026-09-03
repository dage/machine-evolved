#!/usr/bin/env python3

import argparse
import copy
import hashlib
import json
import math
import os


MUTATION_MODES = ("shared-offset-v1", "independent-offset-v1")


def loadJson(path):
	with open(path) as source:
		return json.load(source)


def unwrapCreature(document):
	if "structure" in document and "motorController" in document:
		return document
	creature = document.get("creature")
	if isinstance(creature, dict) and "structure" in creature and "motorController" in creature:
		return creature
	creatures = document.get("structure", {}).get("creatures", [])
	finiteCreatures = [
		item for item in creatures
		if item.get("fitness") is not None and math.isfinite(float(item["fitness"]))
	]
	if finiteCreatures:
		return max(finiteCreatures, key=lambda item: float(item["fitness"]))["data"]
	raise ValueError("Champion file must contain a creature structure and motorController.")


def sha256File(path):
	digest = hashlib.sha256()
	with open(path, "rb") as source:
		for block in iter(lambda: source.read(1024 * 1024), b""):
			digest.update(block)
	return digest.hexdigest()


def buildConfig(template, champion, championPath, championFitness, mode, populationSize, seed, offsetSampling=None, offsetRange=None, changedRatioRange=None, mutationRate=None, crossoverRate=None, mutationParentSelection=None):
	if len(champion["structure"].get("capsules", [])) != 3:
		raise ValueError("The local-search champion must retain the three-capsule morphology.")
	if not math.isfinite(championFitness):
		raise ValueError("Champion fitness must be finite.")
	if populationSize < 16:
		raise ValueError("Population size must be at least 16 for the 8/4 tournaments.")

	config = copy.deepcopy(template)
	experiment = config.setdefault("experiment", {})
	experiment.pop("trainerState", None)
	experiment["profile"] = "two-hour-local-search-{}-seed{}".format(mode, seed)
	experiment["seed"] = seed
	experiment["comparison"] = {
		"schemaVersion": 1,
		"startingController": {
			"path": os.path.abspath(championPath),
			"sha256": sha256File(championPath),
			"fitness": championFitness,
		},
		"mutationMode": mode,
		"pairedBudgetGroup": "two-hour-local-search-v1",
	}
	if offsetSampling is not None:
		experiment["comparison"]["offsetSampling"] = offsetSampling
	if offsetRange is not None:
		experiment["comparison"]["offsetRange"] = offsetRange
	if changedRatioRange is not None:
		experiment["comparison"]["changedRatioRange"] = changedRatioRange
	if mutationRate is not None:
		experiment["comparison"]["mutationRate"] = mutationRate
	if crossoverRate is not None:
		experiment["comparison"]["crossoverRate"] = crossoverRate
	if mutationParentSelection is not None:
		experiment["comparison"]["mutationParentSelection"] = mutationParentSelection

	arguments = config["algorithm"]["arguments"]
	population = arguments["population"]
	population.update({
		"size": populationSize,
		"generation": 0,
		"evaluations": 0,
		"eliteCount": 1,
		"checkpointIntervalSeconds": 60,
	})
	for operation in ("crossover", "mutation"):
		arguments[operation]["competitionSize"] = { "reproduce": 8, "eliminate": 4 }
	arguments["mutation"]["config"]["mode"] = mode
	if offsetSampling is not None:
		arguments["mutation"]["config"]["offsetSampling"] = offsetSampling
	if offsetRange is not None:
		arguments["mutation"]["config"]["offsetRange"] = offsetRange
	if changedRatioRange is not None:
		arguments["mutation"]["config"]["numParameterChangedRatioRange"] = changedRatioRange
	if mutationRate is not None:
		arguments["mutation"]["rate"] = mutationRate
	if crossoverRate is not None:
		arguments["crossover"]["rate"] = crossoverRate
	if mutationParentSelection is not None:
		arguments["mutation"]["parentSelection"] = mutationParentSelection

	config["structure"]["creatures"] = [
		{
			"fitness": championFitness if index == 0 else None,
			"data": copy.deepcopy(champion),
		}
		for index in range(populationSize)
	]
	return config


def main():
	parser = argparse.ArgumentParser(description="Prepare a fixed-morphology local-search training config.")
	parser.add_argument("--template", required=True)
	parser.add_argument("--champion", required=True)
	parser.add_argument("--champion-fitness", required=True, type=float)
	parser.add_argument("--mode", required=True, choices=MUTATION_MODES)
	parser.add_argument("--population", type=int, default=512)
	parser.add_argument("--seed", required=True, type=int)
	parser.add_argument("--offset-sampling", choices=("uniform-v1", "log-uniform-v1"))
	parser.add_argument("--offset-range")
	parser.add_argument("--changed-ratio-range")
	parser.add_argument("--mutation-rate", type=float)
	parser.add_argument("--crossover-rate", type=float)
	parser.add_argument("--mutation-parent-selection", choices=("tournament-v1", "elite-v1"))
	parser.add_argument("--output", required=True)
	args = parser.parse_args()

	template = loadJson(args.template)
	championDocument = loadJson(args.champion)
	champion = unwrapCreature(championDocument)
	config = buildConfig(
		template,
		champion,
		args.champion,
		args.champion_fitness,
		args.mode,
		args.population,
		args.seed,
		args.offset_sampling,
		args.offset_range,
		args.changed_ratio_range,
		args.mutation_rate,
		args.crossover_rate,
		args.mutation_parent_selection,
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
	print("Prepared {} fixed-morphology creatures in {} mode at {}.".format(
		args.population,
		args.mode,
		args.output,
	))


if __name__ == "__main__":
	main()
