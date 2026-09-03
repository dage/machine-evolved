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


def top_fitness_summary(fitnesses, count):
	values = sorted(fitnesses, reverse=True)[:count]
	return {
		"fitnesses": values,
		"meanRobustFitness": sum(values) / len(values) if values else None,
	}


def normalized_qd_score(fitnesses, denominator):
	if not fitnesses or denominator is None or denominator <= 0:
		return None
	return sum(max(0.0, fitness) for fitness in fitnesses) / float(denominator)


def selector_summary(config):
	selector = config.get("algorithm", {}).get("arguments", {}).get("mutation", {}).get("adaptiveSelector", {})
	state = selector.get("state", {}) if isinstance(selector, dict) else {}
	arm_keys = (
		"selections", "attempts", "outcomes", "failures", "invalidOutcomes",
		"terminalFailures", "coverageGains", "replacements", "rejections", "globalBests",
		"positiveQdGain", "normalizedReward",
	)
	emitters = {
		emitter_id: {key: arm.get(key, 0) for key in arm_keys}
		for emitter_id, arm in sorted(state.get("arms", {}).items())
	}
	outcome_totals = {
		key: sum(emitter[key] for emitter in emitters.values())
		for key in ("coverageGains", "replacements", "rejections", "globalBests")
	}
	return {
		"enabled": bool(selector.get("enabled", False)) if isinstance(selector, dict) else False,
		"schemaVersion": state.get("schemaVersion"),
		"totalSelections": int(state.get("totalSelections", 0)),
		"totalAttempts": int(state.get("totalAttempts", 0)),
		"totalOutcomes": int(state.get("totalOutcomes", 0)),
		"totalFailures": int(state.get("totalFailures", 0)),
		"totalInvalidOutcomes": int(state.get("totalInvalidOutcomes", 0)),
		"totalTerminalFailures": int(state.get("totalTerminalFailures", 0)),
		"totalPositiveQdGain": float(state.get("totalPositiveQdGain", 0.0)),
		"totalNormalizedReward": float(state.get("totalNormalizedReward", 0.0)),
		"outcomes": outcome_totals,
		"emitters": emitters,
		"telemetryBaseline": state.get("telemetryBaseline"),
	}


def summarize(config, qd_normalization_reference=None):
	arguments = config["algorithm"]["arguments"]
	population = arguments["population"]
	state = config.get("experiment", {}).get("trainerState", {})
	archived = [item for item in config["structure"]["creatures"] if item.get("fitness") is not None]
	fitnesses = [float(item["fitness"]) for item in archived]
	best_fitness = max(fitnesses) if fitnesses else None
	archive_config = arguments.get("archive", {})
	bins = int(archive_config.get("binsPerAxis", 8))
	axis_count = len(archive_config.get("axes", ("airborneFraction", "rotationParticipation")))
	cells_per_morphology = bins ** axis_count
	template_ids = {
		str(template.get("id") or "unknown")
		for template in config.get("structure", {}).get("templates", [])
	}
	by_morphology = {}
	for item in archived:
		identifier = str(item["data"].get("metadata", {}).get("morphologyId") or "unknown")
		by_morphology.setdefault(identifier, []).append(float(item["fitness"]))
	morphology_count = max(1, len(template_ids | set(by_morphology)))
	total_archive_cells = cells_per_morphology * morphology_count
	if qd_normalization_reference is not None and qd_normalization_reference <= 0:
		raise ValueError("QD normalization reference must be positive")
	sample_denominator = best_fitness * total_archive_cells if best_fitness is not None and best_fitness > 0 else None
	normalization_denominator = qd_normalization_reference
	normalization_kind = "frozen-shared" if normalization_denominator is not None else "sample-relative-diagnostic"
	top5 = top_fitness_summary(fitnesses, 5)
	top12 = top_fitness_summary(fitnesses, 12)
	return {
		"capturedAt": datetime.now(timezone.utc).isoformat(),
		"generation": int(population.get("generation", 0)),
		"evaluations": int(population.get("evaluations", 0)),
		"domainSimulations": int(state.get("evaluationSimulations", 0)),
		"bestFitnessEvaluation": int(state.get("bestFitnessEvaluation", 0)),
		"bestRobustFitness": best_fitness,
		"meanArchiveFitness": sum(fitnesses) / len(fitnesses) if fitnesses else None,
		"occupiedCells": len(archived),
		"partialCandidates": len(state.get("domainProgress", {})),
		"qdScore": sum(fitnesses),
		"normalizedQdScore": normalized_qd_score(fitnesses, normalization_denominator),
		"sampleRelativeNormalizedQdScore": normalized_qd_score(fitnesses, sample_denominator),
		"normalizedQdDefinition": {
			"kind": normalization_kind,
			"comparableAcrossSamples": normalization_denominator is not None,
			"formula": "sum(max(0, cellFitness)) / frozenSharedDenominator" if normalization_denominator is not None else "sum(max(0, cellFitness)) / (sampleBestRobustFitness * sampleTotalArchiveCells)",
			"emptyCellFitness": 0.0,
			"denominator": normalization_denominator if normalization_denominator is not None else sample_denominator,
			"fitnessReference": "frozen-shared" if normalization_denominator is not None else "sample-best-diagnostic-only",
			"totalArchiveCells": total_archive_cells,
			"cellsPerMorphology": cells_per_morphology,
			"morphologyCount": morphology_count,
		},
		"top5": top5,
		"top12": top12,
		"adaptiveEmitterSelector": selector_summary(config),
		"morphologies": {
			identifier: {
				"occupiedCells": len(values),
				"bestRobustFitness": max(values),
				"meanFitness": sum(values) / len(values),
				"qdScore": sum(values),
				"normalizedQdScore": normalized_qd_score(values, normalization_denominator),
				"sampleRelativeNormalizedQdScore": normalized_qd_score(values, sample_denominator),
				"top5": top_fitness_summary(values, 5),
				"top12": top_fitness_summary(values, 12),
			}
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
	parser.add_argument("--qd-normalization-reference", type=float)
	parser.add_argument("--interval-seconds", type=float, default=30)
	parser.add_argument("--once", action="store_true")
	args = parser.parse_args()
	if args.interval_seconds <= 0:
		raise ValueError("--interval-seconds must be positive")
	if args.qd_normalization_reference is not None and args.qd_normalization_reference <= 0:
		raise ValueError("--qd-normalization-reference must be positive")
	while True:
		try:
			append_record(args.output, summarize(read_json(args.config), args.qd_normalization_reference))
		except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
			append_record(args.output, {"capturedAt": datetime.now(timezone.utc).isoformat(), "captureError": str(error)})
		if args.once or (args.summary and args.summary.exists()):
			break
		time.sleep(args.interval_seconds)


if __name__ == "__main__":
	main()
