#!/usr/bin/env python3

import argparse
import json
import math
from pathlib import Path


def horizontal_distance(first, current):
	return math.hypot(current["x"] - first["x"], current["z"] - first["z"])


def quaternion_axis(rotation):
	x = rotation["x"]
	y = rotation["y"]
	z = rotation["z"]
	w = rotation["w"]
	norm = math.sqrt(x * x + y * y + z * z + w * w)
	if norm == 0:
		raise ValueError("Replay contains a zero-length quaternion")
	x /= norm
	y /= norm
	z /= norm
	w /= norm
	return (
		2 * (x * y - w * z),
		1 - 2 * (x * x + z * z),
		2 * (y * z + w * x),
	)


def quaternion_delta(first, second):
	dot = sum(first[key] * second[key] for key in ("x", "y", "z", "w"))
	first_norm = math.sqrt(sum(first[key] * first[key] for key in ("x", "y", "z", "w")))
	second_norm = math.sqrt(sum(second[key] * second[key] for key in ("x", "y", "z", "w")))
	if first_norm == 0 or second_norm == 0:
		raise ValueError("Replay contains a zero-length quaternion")
	return 2 * math.acos(max(-1.0, min(1.0, abs(dot / (first_norm * second_norm)))))


def axis_delta(first, second):
	dot = sum(a * b for a, b in zip(first, second))
	return math.acos(max(-1.0, min(1.0, abs(dot))))


def percentile(values, ratio):
	ordered = sorted(values)
	if not ordered:
		return 0.0
	position = (len(ordered) - 1) * ratio
	lower = int(math.floor(position))
	upper = int(math.ceil(position))
	if lower == upper:
		return ordered[lower]
	return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def analyze(replay, clearance_epsilon, max_spin_rate, max_capsule_rotation_rate, max_unsupported_path_fraction):
	samples = replay["samples"]
	if len(samples) < 2:
		raise ValueError("Replay must contain at least two samples")
	duration = float(replay["durationSeconds"])
	sample_hz = float(replay["sampleHz"])
	delta_time = 1.0 / sample_hz
	first = samples[0]["poses"]["body"]["translation"]
	distances = [horizontal_distance(first, sample["poses"]["body"]["translation"]) for sample in samples]
	heights = [sample["poses"]["body"]["translation"]["y"] for sample in samples]
	segments = []
	for previous, current in zip(samples, samples[1:]):
		previous_position = previous["poses"]["body"]["translation"]
		current_position = current["poses"]["body"]["translation"]
		segments.append(math.hypot(
			current_position["x"] - previous_position["x"],
			current_position["z"] - previous_position["z"],
		))

	capsules = {capsule["id"]: capsule for capsule in replay["capsules"]}
	root_id = replay["capsules"][0]["id"]
	near_ground = []
	root_rotations = []
	root_axes = []
	capsule_rotations = {capsule_id: [] for capsule_id in capsules}
	for sample in samples:
		minimum_clearance = math.inf
		for capsule_id, definition in capsules.items():
			pose = sample["poses"]["parts"][capsule_id]
			axis = quaternion_axis(pose["rotation"])
			clearance = (
				pose["translation"]["y"]
				- definition["radius"]
				- 0.5 * definition["innerHeight"] * abs(axis[1])
			)
			minimum_clearance = min(minimum_clearance, clearance)
		root_pose = sample["poses"]["parts"][root_id]
		root_rotations.append(root_pose["rotation"])
		root_axes.append(quaternion_axis(root_pose["rotation"]))
		for capsule_id in capsules:
			capsule_rotations[capsule_id].append(sample["poses"]["parts"][capsule_id]["rotation"])
		near_ground.append(minimum_clearance <= clearance_epsilon)

	path_length = sum(segments)
	unsupported_path = sum(segment for segment, supported in zip(segments, near_ground[1:]) if not supported)
	unsupported_intervals = []
	interval_start = None
	for index, supported in enumerate(near_ground):
		if not supported and interval_start is None:
			interval_start = index
		elif supported and interval_start is not None:
			unsupported_intervals.append((interval_start, index - 1))
			interval_start = None
	if interval_start is not None:
		unsupported_intervals.append((interval_start, len(near_ground) - 1))
	longest_unsupported = max(
		((end - start + 1) * delta_time for start, end in unsupported_intervals),
		default=0.0,
	)

	full_rotation = sum(quaternion_delta(a, b) for a, b in zip(root_rotations, root_rotations[1:]))
	axis_rotation = sum(axis_delta(a, b) for a, b in zip(root_axes, root_axes[1:]))
	spin_rate = full_rotation / duration
	capsule_rotation_rates = {
		capsule_id: sum(quaternion_delta(a, b) for a, b in zip(rotations, rotations[1:])) / duration
		for capsule_id, rotations in capsule_rotations.items()
	}
	maximum_capsule_rotation_rate = max(capsule_rotation_rates.values())
	unsupported_path_fraction = unsupported_path / path_length if path_length else 0.0
	final_to_max = distances[-1] / max(distances) if max(distances) else 1.0
	credible = (
		spin_rate <= max_spin_rate
		and maximum_capsule_rotation_rate <= max_capsule_rotation_rate
		and unsupported_path_fraction <= max_unsupported_path_fraction
		and final_to_max >= 0.9
	)

	return {
		"schemaVersion": 1,
		"configuredFitnessSimulationUnits": replay["configuredFitness"],
		"replayedFitnessSimulationUnits": replay.get("measuredFitness", replay["measuredMaxDistanceSimulationUnits"]),
		"rawMaxDistanceSimulationUnits": replay["measuredMaxDistanceSimulationUnits"],
		"maxDistanceMeters": max(distances),
		"finalDistanceMeters": distances[-1],
		"finalToMaxDistanceRatio": final_to_max,
		"pathLengthMeters": path_length,
		"pathEfficiency": max(distances) / path_length if path_length else 1.0,
		"radialMonotonicity": sum(current >= previous for previous, current in zip(distances, distances[1:])) / (len(distances) - 1),
		"averagePathSpeedMetersPerSecond": path_length / duration,
		"comHeightMeters": {
			"median": percentile(heights, 0.5),
			"p95": percentile(heights, 0.95),
			"max": max(heights),
		},
		"nearGroundTimeFraction": sum(near_ground) / len(near_ground),
		"unsupportedPathFraction": unsupported_path_fraction,
		"longestUnsupportedSeconds": longest_unsupported,
		"rootRotationRadians": full_rotation,
		"rootAxisRotationRadians": axis_rotation,
		"rootSpinRateRadiansPerSecond": spin_rate,
		"capsuleRotationRatesRadiansPerSecond": capsule_rotation_rates,
		"maxCapsuleRotationRateRadiansPerSecond": maximum_capsule_rotation_rate,
		"credibility": {
			"passes": credible,
			"maxSpinRateRadiansPerSecond": max_spin_rate,
			"maxCapsuleRotationRateRadiansPerSecond": max_capsule_rotation_rate,
			"maxUnsupportedPathFraction": max_unsupported_path_fraction,
			"clearanceEpsilonMeters": clearance_epsilon,
		},
	}


def main():
	parser = argparse.ArgumentParser(description="Analyze a Machine Evolved capsule replay for distance and reward-hacking motion.")
	parser.add_argument("replay", type=Path)
	parser.add_argument("--output", type=Path)
	parser.add_argument("--clearance-epsilon", type=float, default=0.02)
	parser.add_argument("--max-spin-rate", type=float, default=10.0)
	parser.add_argument("--max-capsule-rotation-rate", type=float, default=10.0)
	parser.add_argument("--max-unsupported-path-fraction", type=float, default=0.25)
	parser.add_argument("--require-credible", action="store_true")
	args = parser.parse_args()

	with args.replay.open() as source:
		replay = json.load(source)
	result = analyze(
		replay,
		args.clearance_epsilon,
		args.max_spin_rate,
		args.max_capsule_rotation_rate,
		args.max_unsupported_path_fraction,
	)
	serialized = json.dumps(result, indent=2, allow_nan=False) + "\n"
	if args.output:
		args.output.parent.mkdir(parents=True, exist_ok=True)
		temporary = args.output.with_suffix(args.output.suffix + ".tmp")
		temporary.write_text(serialized)
		temporary.replace(args.output)
	else:
		print(serialized, end="")
	if args.require_credible and not result["credibility"]["passes"]:
		raise SystemExit(3)


if __name__ == "__main__":
	main()
