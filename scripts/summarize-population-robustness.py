#!/usr/bin/env python3

import argparse
import datetime
import json
import math
import os


def main():
	parser = argparse.ArgumentParser(description="Aggregate matched population robustness evaluations.")
	parser.add_argument("--config", action="append", required=True)
	parser.add_argument("--output", required=True)
	args = parser.parse_args()

	candidateRows = None
	candidateHashes = None
	caseNames = []
	for configPath in args.config:
		with open(configPath) as source:
			config = json.load(source)
		metadata = config["experiment"]["populationRobustness"]
		caseName = metadata["case"]
		if caseName in caseNames:
			raise ValueError("Duplicate robustness case: {}".format(caseName))
		caseNames.append(caseName)
		metadataCandidates = metadata["candidates"]
		hashes = [item["creatureSha256"] for item in metadataCandidates]
		candidateIds = [item.get("creatureId") for item in metadataCandidates]
		if all(isinstance(creatureId, str) and creatureId for creatureId in candidateIds):
			if len(set(candidateIds)) != len(candidateIds):
				raise ValueError("Robustness metadata contains duplicate candidate IDs.")
			history = config.get("experiment", {}).get("trainerState", {}).get("evaluationHistory", [])
			fitnessById = {}
			for item in history:
				creatureId = item.get("creatureId")
				fitness = item.get("robustFitness")
				if creatureId in candidateIds and creatureId not in fitnessById:
					if fitness is None or not math.isfinite(float(fitness)):
						raise ValueError("Robustness history contains missing or non-finite fitness.")
					fitnessById[creatureId] = float(fitness)
			missingIds = [creatureId for creatureId in candidateIds if creatureId not in fitnessById]
			if missingIds:
				raise ValueError("Robustness history is missing selected candidate evaluations.")
			caseFitnesses = [fitnessById[creatureId] for creatureId in candidateIds]
		else:
			creatures = config["structure"]["creatures"]
			if len(creatures) != len(metadataCandidates):
				raise ValueError("Legacy robustness config candidate count does not match metadata.")
			if any(item.get("fitness") is None or not math.isfinite(float(item["fitness"])) for item in creatures):
				raise ValueError("Robustness config contains missing or non-finite fitness.")
			caseFitnesses = [float(item["fitness"]) for item in creatures]
		if candidateRows is None:
			candidateHashes = hashes
			candidateRows = [
				{
					"index": item["index"],
					"creatureSha256": item["creatureSha256"],
					"baselineFitness": item["baselineFitness"],
					"cases": {},
				}
				for item in metadata["candidates"]
			]
		elif hashes != candidateHashes:
			raise ValueError("Robustness configs do not contain the same ordered candidates.")
		for index, fitness in enumerate(caseFitnesses):
			candidateRows[index]["cases"][caseName] = fitness

	for row in candidateRows:
		fitnesses = list(row["cases"].values())
		row["worstCaseFitness"] = min(fitnesses)
		row["meanPerturbedFitness"] = sum(fitnesses) / len(fitnesses)
		row["worstCaseRetention"] = row["worstCaseFitness"] / row["baselineFitness"]
	best = max(candidateRows, key=lambda row: row["worstCaseFitness"])
	output = {
		"schemaVersion": 1,
		"generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
		"selectionRule": "maximum-absolute-worst-case-fitness-v1",
		"cases": caseNames,
		"selected": best,
		"candidates": sorted(candidateRows, key=lambda row: row["worstCaseFitness"], reverse=True),
	}
	temporary = args.output + ".tmp"
	with open(temporary, "w") as destination:
		json.dump(output, destination, indent=2, allow_nan=False)
		destination.write("\n")
		destination.flush()
		os.fsync(destination.fileno())
	os.replace(temporary, args.output)
	print(json.dumps({
		"selectedIndex": best["index"],
		"baselineFitness": best["baselineFitness"],
		"worstCaseFitness": best["worstCaseFitness"],
		"meanPerturbedFitness": best["meanPerturbedFitness"],
		"worstCaseRetention": best["worstCaseRetention"],
	}, indent=2))


if __name__ == "__main__":
	main()
