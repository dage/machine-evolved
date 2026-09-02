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


def quaternion_multiply(first, second):
	ax, ay, az, aw = (first[key] for key in ("x", "y", "z", "w"))
	bx, by, bz, bw = (second[key] for key in ("x", "y", "z", "w"))
	return {
		"x": aw * bx + ax * bw + ay * bz - az * by,
		"y": aw * by - ax * bz + ay * bw + az * bx,
		"z": aw * bz + ax * by - ay * bx + az * bw,
		"w": aw * bw - ax * bx - ay * by - az * bz,
	}


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


def rolling_signature_config(replay, override=None):
	"""Resolve the optional rolling gate without changing legacy replays."""
	motion = replay.get("motionMetrics", {})
	source = motion.get("rollingSignatureConfig")
	if source is None:
		source = replay.get("objective", {}).get("credibility", {}).get("rollingSignature", {})
	if not isinstance(source, dict):
		source = {}
	config = dict(source)
	if override:
		config.update(override)
	enabled = bool(config.get("enabled", motion.get("rollingSignatureEnabled", False)))
	return {
		"enabled": enabled,
		"minSpinRateRadiansPerSecond": float(config.get("minSpinRateRadiansPerSecond", 1.0)),
		"minRootRollingCoupling": float(config.get("minRootRollingCoupling", 0.8)),
		"maxRootRollingCoupling": float(config.get("maxRootRollingCoupling", 1.2)),
		"minRootTransverseTravelFraction": float(config.get("minRootTransverseTravelFraction", 0.8)),
		"maxRootAxisStability": float(config.get("maxRootAxisStability", 0.2)),
		"maxRootTravelAlignment": float(config.get("maxRootTravelAlignment", 0.25)),
		"minActiveSegmentSimulationUnits": float(config.get("minActiveSegmentSimulationUnits", 0.0)),
	}


def rolling_discount_config(replay, override=None):
	"""Resolve the optional continuous rolling discount without changing legacy replays."""
	motion = replay.get("motionMetrics", {})
	source = motion.get("rollingDiscountConfig")
	if source is None:
		source = replay.get("objective", {}).get("credibility", {}).get("rollingDiscount", {})
	if not isinstance(source, dict):
		source = {}
	config = dict(source)
	config.setdefault("enabled", motion.get("rollingDiscountEnabled", False))
	config.setdefault("lambda", motion.get("rollingDiscountLambda", 1.0))
	config.setdefault("epsilonSimulationUnits", motion.get("rollingDiscountEpsilonSimulationUnits", 1e-6))
	if override:
		config.update(override)
	rolling_lambda = float(config.get("lambda", 1.0))
	epsilon = float(config.get("epsilonSimulationUnits", 1e-6))
	if not math.isfinite(rolling_lambda) or rolling_lambda < 0.0:
		rolling_lambda = 1.0
	if not math.isfinite(epsilon) or epsilon < 0.0:
		epsilon = 1e-6
	return {
		"enabled": bool(config.get("enabled", motion.get("rollingDiscountEnabled", False))),
		"lambda": rolling_lambda,
		"epsilonSimulationUnits": epsilon,
	}


def analyze(
	replay,
	clearance_epsilon,
	max_spin_rate,
	max_capsule_rotation_rate,
	max_unsupported_path_fraction,
	min_joint_rotation_rate,
	rolling_signature=None,
	rolling_discount=None,
):
	samples = replay["samples"]
	if len(samples) < 2:
		raise ValueError("Replay must contain at least two samples")
	duration = float(replay["durationSeconds"])
	sample_hz = float(replay["sampleHz"])
	delta_time = 1.0 / sample_hz
	first = samples[0]["poses"]["body"]["translation"]
	body_positions = [sample["poses"]["body"]["translation"] for sample in samples]
	distances = [horizontal_distance(first, position) for position in body_positions]
	heights = [position["y"] for position in body_positions]
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
	joint_rotations = [[] for _ in range(max(0, len(capsules) - 1))]
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
		ordered_rotations = [sample["poses"]["parts"][capsule_id]["rotation"] for capsule_id in capsules]
		for index in range(len(ordered_rotations) - 1):
			parent = ordered_rotations[index]
			child = ordered_rotations[index + 1]
			parent_inverse = {"x": -parent["x"], "y": -parent["y"], "z": -parent["z"], "w": parent["w"]}
			joint_rotations[index].append(quaternion_multiply(parent_inverse, child))
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
	rolling = rolling_signature_config(replay, rolling_signature)
	discount = rolling_discount_config(replay, rolling_discount)
	root_radius = float(replay["capsules"][0]["radius"])
	min_active_segment = rolling["minActiveSegmentSimulationUnits"] * float(replay.get("displayScale", 0.01))
	transverse_travel = 0.0
	active_path_length = 0.0
	rolling_explained_distance = 0.0
	for index, segment in enumerate(segments):
		if segment > 0.0:
			axis = root_axes[index + 1]
			axis_length = math.hypot(axis[0], axis[2])
			previous_position = body_positions[index]
			current_position = body_positions[index + 1]
			travel_x = current_position["x"] - previous_position["x"]
			travel_z = current_position["z"] - previous_position["z"]
			travel_length = math.hypot(travel_x, travel_z)
			if axis_length and travel_length:
				alignment = abs(axis[0] * travel_x + axis[2] * travel_z) / (axis_length * travel_length)
				transverse_weight = max(0.0, 1.0 - alignment * alignment)
				rolling_displacement = root_radius * quaternion_delta(
					root_rotations[index], root_rotations[index + 1]
				) * axis_length * transverse_weight
				explained = segment * (1.0 - math.exp(
					-rolling_displacement / (segment + discount["epsilonSimulationUnits"] * float(replay.get("displayScale", 0.01)))
				))
				rolling_explained_distance += explained if math.isfinite(explained) else 0.0
		if segment <= min_active_segment:
			continue
		active_path_length += segment
		axis = root_axes[index + 1]
		axis_length = math.hypot(axis[0], axis[2])
		previous_position = body_positions[index]
		current_position = body_positions[index + 1]
		travel_x = current_position["x"] - previous_position["x"]
		travel_z = current_position["z"] - previous_position["z"]
		travel_length = math.hypot(travel_x, travel_z)
		if axis_length and travel_length:
			alignment = abs(axis[0] * travel_x + axis[2] * travel_z) / (axis_length * travel_length)
			if alignment <= rolling["maxRootTravelAlignment"]:
				transverse_travel += segment
	root_rolling_coupling = path_length / (full_rotation * root_radius) if full_rotation and root_radius else 0.0
	root_transverse_travel_fraction = transverse_travel / active_path_length if active_path_length else 0.0
	root_axis_stability = axis_rotation / full_rotation if full_rotation else 0.0
	capsule_rotation_rates = {
		capsule_id: sum(quaternion_delta(a, b) for a, b in zip(rotations, rotations[1:])) / duration
		for capsule_id, rotations in capsule_rotations.items()
	}
	maximum_capsule_rotation_rate = max(capsule_rotation_rates.values())
	joint_rotation_rates = [
		sum(quaternion_delta(a, b) for a, b in zip(rotations, rotations[1:])) / duration
		for rotations in joint_rotations
	]
	minimum_joint_rotation_rate = min(joint_rotation_rates, default=0.0)
	unsupported_path_fraction = unsupported_path / path_length if path_length else 0.0
	final_to_max = distances[-1] / max(distances) if max(distances) else 1.0
	rolling_explained_fraction = (
		max(0.0, min(1.0, rolling_explained_distance / path_length)) if path_length else 0.0
	)
	rolling_signature_match = (
		rolling["enabled"]
		and spin_rate >= rolling["minSpinRateRadiansPerSecond"]
		and rolling["minRootRollingCoupling"] <= root_rolling_coupling <= rolling["maxRootRollingCoupling"]
		and root_transverse_travel_fraction >= rolling["minRootTransverseTravelFraction"]
		and root_axis_stability <= rolling["maxRootAxisStability"]
	)
	credible = (
		spin_rate <= max_spin_rate
		and maximum_capsule_rotation_rate <= max_capsule_rotation_rate
		and unsupported_path_fraction <= max_unsupported_path_fraction
		and final_to_max >= 0.9
		and minimum_joint_rotation_rate >= min_joint_rotation_rate
		and not rolling_signature_match
	)
	raw_max_distance_simulation_units = float(replay["measuredMaxDistanceSimulationUnits"])
	selected_fitness_simulation_units = 0.0
	if credible:
		discount_multiplier = 1.0 - discount["lambda"] * rolling_explained_fraction if discount["enabled"] else 1.0
		selected_fitness_simulation_units = raw_max_distance_simulation_units * max(0.0, discount_multiplier)

	return {
		"schemaVersion": 1,
		"configuredFitnessSimulationUnits": replay["configuredFitness"],
		"replayedFitnessSimulationUnits": replay.get("measuredFitness", replay["measuredMaxDistanceSimulationUnits"]),
		"rawMaxDistanceSimulationUnits": replay["measuredMaxDistanceSimulationUnits"],
		"undiscountedRawDistanceSimulationUnits": raw_max_distance_simulation_units,
		"selectedFitnessSimulationUnits": selected_fitness_simulation_units,
		"discountedFitnessSimulationUnits": selected_fitness_simulation_units,
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
		"rootRollingCoupling": root_rolling_coupling,
		"rootTransverseTravelFraction": root_transverse_travel_fraction,
		"rootAxisStability": root_axis_stability,
		"rollingExplainedFraction": rolling_explained_fraction,
		"rollingDiscountEnabled": discount["enabled"],
		"rollingDiscountLambda": discount["lambda"],
		"rollingDiscountEpsilonSimulationUnits": discount["epsilonSimulationUnits"],
		"rollingDiscountConfig": discount,
		"rollingSignatureEnabled": rolling["enabled"],
		"rollingSignature": rolling_signature_match,
		"rollingSignatureConfig": rolling,
		"capsuleRotationRatesRadiansPerSecond": capsule_rotation_rates,
		"maxCapsuleRotationRateRadiansPerSecond": maximum_capsule_rotation_rate,
		"jointRotationRatesRadiansPerSecond": joint_rotation_rates,
		"minJointRotationRateRadiansPerSecond": minimum_joint_rotation_rate,
		"credibility": {
			"passes": credible,
			"maxSpinRateRadiansPerSecond": max_spin_rate,
			"maxCapsuleRotationRateRadiansPerSecond": max_capsule_rotation_rate,
			"minJointRotationRateRadiansPerSecond": min_joint_rotation_rate,
			"maxUnsupportedPathFraction": max_unsupported_path_fraction,
			"clearanceEpsilonMeters": clearance_epsilon,
			"rollingDiscountEnabled": discount["enabled"],
			"rollingDiscountLambda": discount["lambda"],
			"rollingExplainedFraction": rolling_explained_fraction,
		},
	}


def main():
	parser = argparse.ArgumentParser(description="Analyze a Machine Evolved capsule replay for distance and reward-hacking motion.")
	parser.add_argument("replay", type=Path)
	parser.add_argument("--output", type=Path)
	parser.add_argument("--clearance-epsilon", type=float, default=0.02)
	parser.add_argument("--max-spin-rate", type=float, default=10.0)
	parser.add_argument("--max-capsule-rotation-rate", type=float, default=10.0)
	parser.add_argument("--min-joint-rotation-rate", type=float, default=0.0)
	parser.add_argument("--max-unsupported-path-fraction", type=float, default=0.25)
	parser.add_argument("--enable-rolling-signature", action="store_true")
	parser.add_argument("--rolling-min-spin-rate", type=float)
	parser.add_argument("--rolling-min-coupling", type=float)
	parser.add_argument("--rolling-max-coupling", type=float)
	parser.add_argument("--rolling-min-transverse-fraction", type=float)
	parser.add_argument("--rolling-max-axis-stability", type=float)
	parser.add_argument("--rolling-max-travel-alignment", type=float)
	parser.add_argument("--rolling-min-active-segment-simulation-units", type=float)
	parser.add_argument("--enable-rolling-discount", action="store_true")
	parser.add_argument("--rolling-discount-lambda", type=float)
	parser.add_argument("--rolling-discount-epsilon-simulation-units", type=float)
	parser.add_argument("--require-credible", action="store_true")
	args = parser.parse_args()

	with args.replay.open() as source:
		replay = json.load(source)
	rolling_override = {"enabled": True} if args.enable_rolling_signature else {}
	for option, key in (
		(args.rolling_min_spin_rate, "minSpinRateRadiansPerSecond"),
		(args.rolling_min_coupling, "minRootRollingCoupling"),
		(args.rolling_max_coupling, "maxRootRollingCoupling"),
		(args.rolling_min_transverse_fraction, "minRootTransverseTravelFraction"),
		(args.rolling_max_axis_stability, "maxRootAxisStability"),
		(args.rolling_max_travel_alignment, "maxRootTravelAlignment"),
		(args.rolling_min_active_segment_simulation_units, "minActiveSegmentSimulationUnits"),
	):
		if option is not None:
			rolling_override[key] = option
	rolling_discount_override = {"enabled": True} if args.enable_rolling_discount else {}
	for option, key in (
		(args.rolling_discount_lambda, "lambda"),
		(args.rolling_discount_epsilon_simulation_units, "epsilonSimulationUnits"),
	):
		if option is not None:
			rolling_discount_override[key] = option
	result = analyze(
		replay,
		args.clearance_epsilon,
		args.max_spin_rate,
		args.max_capsule_rotation_rate,
		args.max_unsupported_path_fraction,
		args.min_joint_rotation_rate,
		rolling_override or None,
		rolling_discount_override or None,
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
