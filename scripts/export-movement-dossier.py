#!/usr/bin/env python3

"""Export a complete, compact, model-readable description of a replay."""

import argparse
import hashlib
import json
import math
from pathlib import Path


def horizontal_distance(first, current):
	return math.hypot(current["x"] - first["x"], current["z"] - first["z"])


def quaternion_delta(first, second):
	dot = sum(first[key] * second[key] for key in ("x", "y", "z", "w"))
	first_norm = math.sqrt(sum(first[key] ** 2 for key in ("x", "y", "z", "w")))
	second_norm = math.sqrt(sum(second[key] ** 2 for key in ("x", "y", "z", "w")))
	if first_norm == 0 or second_norm == 0:
		raise ValueError("Replay contains a zero-length quaternion")
	return 2 * math.acos(max(-1.0, min(1.0, abs(dot / (first_norm * second_norm)))))


def percentile(values, ratio):
	ordered = sorted(values)
	position = (len(ordered) - 1) * ratio
	lower = math.floor(position)
	upper = math.ceil(position)
	if lower == upper:
		return ordered[lower]
	return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def pose_columns(label):
	return [
		f"{label}_x", f"{label}_y", f"{label}_z",
		f"{label}_qx", f"{label}_qy", f"{label}_qz", f"{label}_qw",
	]


def pose_values(pose):
	translation = pose["translation"]
	rotation = pose["rotation"]
	return [
		translation["x"], translation["y"], translation["z"],
		rotation["x"], rotation["y"], rotation["z"], rotation["w"],
	]


def format_row(values):
	return ",".join(str(value) if isinstance(value, int) else f"{value:.4f}" for value in values)


def build_report(replay_path):
	raw = replay_path.read_bytes()
	replay = json.loads(raw)
	samples = replay["samples"]
	if len(samples) < 2:
		raise ValueError("Replay must contain at least two samples")

	sample_hz = float(replay["sampleHz"])
	duration = float(replay["durationSeconds"])
	display_scale = float(replay["displayScale"])
	capsules = replay["capsules"]
	capsule_ids = [capsule["id"] for capsule in capsules]
	first_position = samples[0]["poses"]["body"]["translation"]
	body_positions = [sample["poses"]["body"]["translation"] for sample in samples]
	distances = [horizontal_distance(first_position, position) for position in body_positions]
	heights = [position["y"] for position in body_positions]
	segments = [
		math.hypot(current["x"] - previous["x"], current["z"] - previous["z"])
		for previous, current in zip(body_positions, body_positions[1:])
	]
	path_length = sum(segments)
	rotation_rates = {}
	for capsule_id in capsule_ids:
		rotations = [sample["poses"]["parts"][capsule_id]["rotation"] for sample in samples]
		rotation_rates[capsule_id] = sum(
			quaternion_delta(previous, current)
			for previous, current in zip(rotations, rotations[1:])
		) / duration

	motion = replay["motionMetrics"]
	coordinate = replay["coordinateSystem"]
	source_coordinate = replay["sourceCoordinateSystem"]
	lines = [
		"MACHINE EVOLVED - COMPLETE TEXT MOVEMENT DOSSIER",
		"=================================================",
		"",
		"PURPOSE",
		"This is a machine-readable and human-readable account of one full movement",
		"episode for the current raw-distance champion. It includes every recorded",
		"60 Hz pose; no frames are omitted. It is intended to let an external model",
		"inspect the gait numerically without watching the Three.js preview.",
		"",
		"IDENTITY AND INTEGRITY",
		f"Replay file: {replay_path.name}",
		f"Replay SHA-256: {hashlib.sha256(raw).hexdigest()}",
		f"Schema: {replay['kind']} v{replay['schemaVersion']}",
		f"Profile: {replay['profile']}",
		f"Creature ID: {replay['creatureId']}",
		f"Samples: {len(samples)} at {sample_hz:g} Hz over {duration:g} seconds",
		f"Configured fitness: {replay['configuredFitness']:.6f} source simulation-units",
		f"Replayed fitness: {replay['measuredFitness']:.6f} source simulation-units",
		f"Fitness parity verified: {str(replay['fitnessParity']['verified']).lower()}",
		"",
		"UNITS AND COORDINATES",
		f"Source: {source_coordinate['upAxis']} up; horizontal {','.join(source_coordinate['horizontalAxes'])}; units {source_coordinate['units']}.",
		f"Table: {coordinate['upAxis']} up; horizontal {','.join(coordinate['horizontalAxes'])}; replay displayScale={display_scale:g}.",
		"The replay metadata labels scaled coordinates as metres. There is no separate",
		"empirical calibration establishing SI metres, so this dossier calls them",
		"display units (DU). Conversion: 1 source simulation-unit = 0.01 DU.",
		"",
		"CREATURE",
		"Three serially connected capsules. Table aliases c0, c1, c2 are in this order:",
	]
	for index, capsule in enumerate(capsules):
		lines.append(
			f"c{index}: id={capsule['id']}; innerHeight={capsule['innerHeight']:.9f} DU "
			f"({capsule['innerHeight'] / display_scale:.9f} source units); "
			f"radius={capsule['radius']:.9f} DU ({capsule['radius'] / display_scale:.9f} source units)"
		)
	physics = replay["physics"]
	lines.extend([
		"Connectivity: c1 is jointed to c0; c2 is jointed to c1.",
		"",
		"PHYSICS AND OBJECTIVE",
		f"Objective: {replay['objective']['id']} ({replay['objective']['metric']}).",
		f"Gravity source vector: ({physics['gravityX']}, {physics['gravityY']}, {physics['gravityZ']}).",
		f"Ground/capsule friction: {physics['groundFriction']} / {physics['capsuleFriction']}.",
		f"Capsule rolling/spinning friction: {physics['capsuleRollingFriction']} / {physics['capsuleSpinningFriction']}.",
		f"Capsule linear/angular damping: {physics['capsuleLinearDamping']} / {physics['capsuleAngularDamping']}.",
		f"Capsule mass scale: {physics['capsuleMassScale']}; motor max force: {physics['motorMaxForce']}.",
	])

	final_distance_du = distances[-1]
	lines.extend([
		"",
		"WHAT THE NUMBERS SAY",
		f"Final horizontal displacement: {motion['finalDistanceSimulationUnits']:.6f} source units = {final_distance_du:.6f} DU.",
		f"Horizontal path length: {motion['pathLengthSimulationUnits']:.6f} source units = {path_length:.6f} DU.",
		f"Path efficiency (displacement/path): {final_distance_du / path_length:.6f}.",
		f"Average path speed: {path_length / duration:.6f} DU/s.",
		f"Final-to-maximum distance ratio: {motion['finalToMaxDistanceRatio']:.6f}.",
		f"Near-ground time fraction: {motion['nearGroundTimeFraction']:.6f}.",
		f"Unsupported path fraction: {motion['unsupportedPathFraction']:.9f}.",
		f"Longest unsupported interval: {motion['longestUnsupportedSeconds']:.6f} s.",
		f"Body height DU, median/p95/max: {percentile(heights, 0.5):.6f} / {percentile(heights, 0.95):.6f} / {max(heights):.6f}.",
		f"Rolling-explained path fraction: {motion['rollingExplainedFraction']:.6f}.",
		f"Root rolling coupling: {motion['rootRollingCoupling']:.6f}.",
		f"Root transverse-travel fraction: {motion['rootTransverseTravelFraction']:.6f}.",
		f"Root axis stability: {motion['rootAxisStability']:.6f}.",
		f"Root spin: {motion['rootSpinRateRadiansPerSecond']:.6f} rad/s = {motion['rootSpinRateRadiansPerSecond'] / (2 * math.pi):.6f} revolutions/s.",
	])
	for index, capsule_id in enumerate(capsule_ids):
		lines.append(f"c{index} mean rotation rate: {rotation_rates[capsule_id]:.6f} rad/s.")
	lines.extend([
		"",
		"INTERPRETATION FOR REVIEW",
		"This is not an upright whole-creature wheel or a jumping gait. It is almost",
		"continuously ground-bound and travels on a nearly straight path while steadily",
		"accelerating. The leading capsule rotates extraordinarily fast, whereas c1 and",
		"c2 rotate much more slowly. About 72.9% of the path is numerically explained by",
		"rolling. Thus the replay is the raw-distance winner but looks like a low-friction,",
		"high-spin exploit rather than the desired coordinated wheel-and-jump locomotion.",
		"Under the later diagnostic cap of 10 rad/s maximum capsule spin it fails the",
		"strict credibility check, even though the captured training objective accepted",
		"its raw fitness exactly. This distinction is central to evaluating the result.",
		"",
		"TEN-SECOND MOVEMENT PHASES",
		"start_s,end_s,end_distance_DU,window_displacement_DU,average_radial_speed_DU_per_s,min_body_y,mean_body_y,max_body_y",
	])
	window_ticks = round(10 * sample_hz)
	for start_index in range(0, len(samples) - 1, window_ticks):
		end_index = min(start_index + window_ticks, len(samples) - 1)
		start_time = samples[start_index]["tick"] / sample_hz
		end_time = samples[end_index]["tick"] / sample_hz
		displacement = horizontal_distance(body_positions[start_index], body_positions[end_index])
		window_heights = heights[start_index:end_index + 1]
		lines.append(
			f"{start_time:.0f},{end_time:.0f},{distances[end_index]:.6f},{displacement:.6f},"
			f"{displacement / (end_time - start_time):.6f},{min(window_heights):.6f},"
			f"{sum(window_heights) / len(window_heights):.6f},{max(window_heights):.6f}"
		)

	columns = ["tick", "time_s", "body_x", "body_y", "body_z", "distance_DU", "step_speed_DU_per_s"]
	for index in range(len(capsules)):
		columns.extend(pose_columns(f"c{index}"))
	lines.extend([
		"",
		"COMPLETE 60 HZ POSE TRACE",
		"Each following CSV row is one replay frame. Position fields are DU. Quaternion",
		"fields use (qx,qy,qz,qw). Four decimal places bound position rounding to 0.00005",
		"DU and quaternion-component rounding to 0.00005. Capsule definitions above plus",
		"these poses are sufficient to reconstruct the complete recorded movement.",
		"The replay's body quaternion is identity throughout and is therefore omitted;",
		"body_x/y/z is the reference trajectory, while c0/c1/c2 contain actual orientation.",
		",".join(columns),
	])
	for index, sample in enumerate(samples):
		body = sample["poses"]["body"]["translation"]
		step_speed = 0.0 if index == 0 else segments[index - 1] * sample_hz
		values = [sample["tick"], sample["tick"] / sample_hz, body["x"], body["y"], body["z"], distances[index], step_speed]
		for capsule_id in capsule_ids:
			values.extend(pose_values(sample["poses"]["parts"][capsule_id]))
		lines.append(format_row(values))

	return "\n".join(lines) + "\n"


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("replay", type=Path)
	parser.add_argument("output", type=Path)
	args = parser.parse_args()
	args.output.parent.mkdir(parents=True, exist_ok=True)
	args.output.write_text(build_report(args.replay), encoding="utf-8")


if __name__ == "__main__":
	main()
