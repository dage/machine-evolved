#!/usr/bin/env python3
"""Atomically enable the documented broad-exploration MAP-Elites phase."""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("config", type=Path)
	parser.add_argument("--reason", required=True)
	args = parser.parse_args()
	with args.config.open() as source:
		config = json.load(source)
	if config["algorithm"]["type"] != "MapElites":
		raise ValueError("Exploration phase requires a MapElites checkpoint")
	mutation = config["algorithm"]["arguments"]["mutation"]
	mutation["randomInjectionRate"] = 0.10
	mutation["largeMutationRate"] = 0.25
	mutation["largeConfig"] = {
		"mode": "independent-offset-v1",
		"numParameterChangedRatioRange": "0.15-0.50",
		"offsetRange": "0.02;1.0",
		"offsetSampling": "log-uniform-v1",
		"offsetExponent": 1,
		"randomizeSign": "yes",
	}
	population = config["algorithm"]["arguments"]["population"]
	state = config.setdefault("experiment", {}).setdefault("trainerState", {})
	state.setdefault("experimentPhases", []).append({
		"id": "mixed-exploration-emitter-v1",
		"startedAt": datetime.now(timezone.utc).isoformat(),
		"evaluation": int(population.get("evaluations", 0)),
		"bestFitnessEvaluation": int(state.get("bestFitnessEvaluation", 0)),
		"reason": args.reason,
		"randomInjectionRate": mutation["randomInjectionRate"],
		"largeMutationRate": mutation["largeMutationRate"],
		"largeMutationConfig": mutation["largeConfig"],
	})
	temporary = args.config.with_suffix(args.config.suffix + ".phase.tmp")
	with temporary.open("w") as output:
		json.dump(config, output, indent=1, allow_nan=False)
		output.write("\n")
		output.flush()
		os.fsync(output.fileno())
	os.replace(temporary, args.config)


if __name__ == "__main__":
	main()
