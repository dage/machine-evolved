#!/usr/bin/env python3

import argparse
import datetime
import hashlib
import json
import os
import re


BEST_PATTERN = re.compile(r"--> new best creature found through ([^!]+)! Fitness=([-+0-9.eE]+)")
COMPLETED_PATTERN = re.compile(r"Completed ([0-9]+) evaluations?\.")


def sha256File(path):
	digest = hashlib.sha256()
	with open(path, "rb") as source:
		for block in iter(lambda: source.read(1024 * 1024), b""):
			digest.update(block)
	return digest.hexdigest()


def stopReason(log):
	if "no new best creature" in log:
		return "fitness-stall"
	if "max number of fitness evaluations" in log:
		return "evaluation-limit"
	if "wall-clock training limit" in log:
		return "wall-clock-limit"
	if "interrupt signal" in log:
		return "signal"
	return None


def main():
	parser = argparse.ArgumentParser(description="Collect compact, integrity-bound training-run evidence.")
	parser.add_argument("--training-root", required=True)
	parser.add_argument("--prefix", default="")
	parser.add_argument("--output", required=True)
	args = parser.parse_args()

	runs = []
	for name in sorted(os.listdir(args.training_root)):
		if not name.startswith(args.prefix):
			continue
		runDirectory = os.path.join(args.training_root, name)
		summaryPath = os.path.join(runDirectory, "summary.json")
		configPath = os.path.join(runDirectory, "config.json")
		trainerLogPath = os.path.join(runDirectory, "trainer.log")
		workerLogPath = os.path.join(runDirectory, "shellworker.log")
		if not all(os.path.isfile(path) for path in (summaryPath, configPath, trainerLogPath, workerLogPath)):
			continue

		with open(summaryPath) as source:
			summary = json.load(source)
		with open(configPath) as source:
			config = json.load(source)
		with open(trainerLogPath) as source:
			trainerLog = source.read()
		with open(workerLogPath) as source:
			workerLog = source.read()

		birthTimestamp = os.stat(runDirectory).st_birthtime
		completedTimestamp = datetime.datetime.fromisoformat(summary["completedAt"]).timestamp()
		experiment = config.get("experiment", {})
		arguments = config["algorithm"]["arguments"]
		workerMatches = COMPLETED_PATTERN.findall(workerLog)
		runs.append({
			"name": name,
			"startedAtProxy": datetime.datetime.fromtimestamp(
				birthTimestamp,
				tz=datetime.timezone.utc,
			).isoformat(),
			"completedAt": summary["completedAt"],
			"wallSecondsProxy": completedTimestamp - birthTimestamp,
			"stopReason": stopReason(trainerLog),
			"workers": summary["workers"],
			"populationSize": summary["populationSize"],
			"generation": summary["generation"],
			"trainerAcceptedEvaluations": summary["evaluations"],
			"workerCompletedEvaluations": int(workerMatches[-1]) if workerMatches else None,
			"evaluatedCreaturesAtCheckpoint": summary["evaluatedCreatures"],
			"bestFitnessSimulationUnits": summary["bestFitness"],
			"averageFitnessSimulationUnits": summary["averageFitness"],
			"bestEvents": [
				{ "generator": match.group(1), "fitnessSimulationUnits": float(match.group(2)) }
				for match in BEST_PATTERN.finditer(trainerLog)
			],
			"config": {
				"bytes": os.path.getsize(configPath),
				"sha256": sha256File(configPath),
			},
			"optimizer": {
				"population": {
					"eliteCount": arguments["population"].get("eliteCount", 0),
				},
				"crossover": {
					"rate": arguments["crossover"]["rate"],
					"competitionSize": arguments["crossover"]["competitionSize"],
				},
				"mutation": {
					"rate": arguments["mutation"]["rate"],
					"competitionSize": arguments["mutation"]["competitionSize"],
					"parentSelection": arguments["mutation"].get("parentSelection", "tournament-v1"),
					"config": arguments["mutation"]["config"],
				},
			},
			"comparison": experiment.get("comparison"),
			"lineSearch": experiment.get("lineSearch"),
			"robustness": experiment.get("robustness"),
		})

	output = {
		"schemaVersion": 1,
		"generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
		"timeFields": {
			"startedAtProxy": "run-directory filesystem birth time",
			"wallSecondsProxy": "summary.completedAt minus run-directory birth time",
		},
		"runs": sorted(runs, key=lambda run: run["startedAtProxy"]),
	}
	temporary = args.output + ".tmp"
	with open(temporary, "w") as destination:
		json.dump(output, destination, indent=2, allow_nan=False)
		destination.write("\n")
		destination.flush()
		os.fsync(destination.fileno())
	os.replace(temporary, args.output)
	print("Collected {} runs into {}.".format(len(runs), args.output))


if __name__ == "__main__":
	main()
