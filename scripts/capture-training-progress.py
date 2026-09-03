#!/usr/bin/env python3
"""Capture atomic Machine Evolved checkpoint summaries as JSON Lines."""

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path


def read_json(path):
	with path.open() as source:
		return json.load(source)


def summarize(config):
	population = config["algorithm"]["arguments"]["population"]
	state = config.get("experiment", {}).get("trainerState", {})
	archived = [item for item in config["structure"]["creatures"] if item.get("fitness") is not None]
	fitnesses = [float(item["fitness"]) for item in archived]
	by_morphology = {}
	for item in archived:
		identifier = item["data"].get("metadata", {}).get("morphologyId", "unknown")
		by_morphology.setdefault(identifier, []).append(float(item["fitness"]))
	return {
		"capturedAt": datetime.now(timezone.utc).isoformat(),
		"generation": int(population.get("generation", 0)),
		"evaluations": int(population.get("evaluations", 0)),
		"domainSimulations": int(state.get("evaluationSimulations", 0)),
		"bestFitnessEvaluation": int(state.get("bestFitnessEvaluation", 0)),
		"bestRobustFitness": max(fitnesses) if fitnesses else None,
		"meanArchiveFitness": sum(fitnesses) / len(fitnesses) if fitnesses else None,
		"occupiedCells": len(archived),
		"partialCandidates": len(state.get("domainProgress", {})),
		"morphologies": {
			identifier: {"occupiedCells": len(values), "bestRobustFitness": max(values), "meanFitness": sum(values) / len(values)}
			for identifier, values in sorted(by_morphology.items())
		},
	}


def append_record(path, record):
	path.parent.mkdir(parents=True, exist_ok=True)
	with path.open("a") as output:
		output.write(json.dumps(record, separators=(",", ":"), allow_nan=False) + "\n")
		output.flush()
		os.fsync(output.fileno())


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("--config", type=Path, required=True)
	parser.add_argument("--output", type=Path, required=True)
	parser.add_argument("--summary", type=Path)
	parser.add_argument("--interval-seconds", type=float, default=30)
	parser.add_argument("--once", action="store_true")
	args = parser.parse_args()
	if args.interval_seconds <= 0:
		raise ValueError("--interval-seconds must be positive")
	while True:
		try:
			append_record(args.output, summarize(read_json(args.config)))
		except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
			append_record(args.output, {"capturedAt": datetime.now(timezone.utc).isoformat(), "captureError": str(error)})
		if args.once or (args.summary and args.summary.exists()):
			break
		time.sleep(args.interval_seconds)


if __name__ == "__main__":
	main()
