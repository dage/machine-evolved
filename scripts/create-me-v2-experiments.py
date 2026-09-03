#!/usr/bin/env python3
"""Generate the controlled ME-V2 controller/search/morphology experiment lanes."""

import copy
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "machine-evolved-trainer" / "configs"

INPUT_KEYS = [
	"root-orientation-x", "root-orientation-y", "root-orientation-z", "root-orientation-w",
	"z-position", "velocity-x", "velocity-y", "velocity-z", "oscillators",
	"capsule-position-x", "capsule-position-y", "capsule-position-z",
	"capsule-velocity-x", "capsule-velocity-y", "capsule-velocity-z",
	"capsule-angular-velocity-x", "capsule-angular-velocity-y", "capsule-angular-velocity-z",
	"motor-angle-x", "motor-angle-y", "motor-angle-z", "feedbacks",
]


def morphology(identifier, dimensions):
	capsules = []
	position_y = 0.0
	previous = None
	for index, (inner_height, radius) in enumerate(dimensions):
		capsule_id = "{}-capsule-{}".format(identifier, index)
		if previous is not None:
			position_y -= previous[0] / 2 + previous[1] + inner_height / 2 + radius
		constraint = "" if index == 0 else {
			"parentId": "{}-capsule-{}".format(identifier, index - 1),
			"x-rotation": {"range": "-1;1"},
			"y-rotation": {"range": "-1;1"},
			"z-rotation": {"range": "-1;1"},
		}
		capsules.append({
			"id": capsule_id,
			"innerHeight": inner_height,
			"radius": radius,
			"positionX": 0.0,
			"positionY": position_y,
			"positionZ": 22.0,
			"quaternionX": 0.7071067811865475,
			"quaternionY": 0.0,
			"quaternionZ": 0.0,
			"quaternionW": 0.7071067811865475,
			"constraint": constraint,
		})
		previous = (inner_height, radius)
	return capsules


MORPHOLOGIES = [
	("m0-champion-proportions", [(82.7521957076658, 18.78795045398938), (87.04240976588804, 10.421538124883625), (60.50323125672853, 10.996259171105123)]),
	("m1-balanced", [(76.0, 14.0), (76.0, 14.0), (76.0, 14.0)]),
	("m2-wheel-biased", [(48.0, 21.0), (70.0, 12.0), (48.0, 21.0)]),
]


def common_experiment(profile):
	return {
		"schemaVersion": 2,
		"backend": "machine-evolved-bullet-v2",
		"profile": profile,
		"seed": 240903,
		"coordinateSystem": {"upAxis": "z", "horizontalAxes": ["x", "y"], "units": "simulation-units"},
		"objective": {"id": "max-horizontal-distance-v1", "horizonTicks": 3600, "fixedStepHz": 60, "penalties": []},
		"physics": {
			"engine": "Bullet", "version": "2.86-v2", "controlRateHz": 60, "physicsRateHz": 120,
			"solverIterations": 20, "splitImpulse": True, "gravityX": 0, "gravityY": 0, "gravityZ": -100,
			"groundFriction": 0.8, "motorMaxForce": 5000, "motorTargetVelocityLimit": 100,
			"capsuleFriction": 0.8, "capsuleRollingFriction": 0.02, "capsuleSpinningFriction": 0.02,
			"capsuleRestitution": 0, "capsuleLinearDamping": 0, "capsuleAngularDamping": 0,
			"capsuleMassScale": 0.0001, "capsuleCcdEnabled": True,
			"ccdMotionThresholdRadiusRatio": 0.25, "ccdSweptSphereRadiusRatio": 0.2,
		},
		"evaluationDomains": [
			{"id": "nominal", "physics": {}},
			{"id": "slick", "physics": {"groundFriction": 0.45, "capsuleFriction": 0.45}},
			{"id": "rough", "physics": {"groundFriction": 1.2, "capsuleFriction": 1.2}},
		],
		"robustAggregation": "half-min-plus-geometric-mean-v1",
		"intent": ["maximize robust horizontal distance", "permit rolling and jump-assisted propulsion", "reject only numerical invalidity"],
	}


def controller(kind):
	if kind == "harmonic":
		return {
			"schemaVersion": 2,
			"commandMode": "target-angle-servo-v1",
			"servo": {"targetAngleRangeRadians": 2.827433388, "kp": 10, "kd": 0.75, "settlingSeconds": 1, "rampSeconds": 1},
			"initialization": {"mode": "mixed-curl-v1", "curlFraction": 0.5, "curlTargetRadians": 2.05},
			"layers": [{"activation": "tanh"}],
		}
	return {
		"schemaVersion": 2,
		"commandMode": "target-angle-servo-v1",
		"servo": {"targetAngleRangeRadians": 2.827433388, "kp": 10, "kd": 0.75, "settlingSeconds": 1, "rampSeconds": 1},
		"layers": [{"neurons": 50, "activation": "tanh"}, {"neurons": 10, "activation": "tanh"}, {"activation": "tanh"}],
	}


def generator(kind):
	inputs = {key: 0 for key in INPUT_KEYS}
	if kind == "harmonic":
		inputs["oscillators"] = 1
		oscillators = {"start": 0.05, "multiplier": 1.35, "count": 16, "mode": "sin-cos-v1"}
	else:
		inputs = {key: int(key != "feedbacks") for key in INPUT_KEYS}
		oscillators = {"start": 0.1, "multiplier": 2, "count": 9}
	return {
		"capsuleRadiusRange": "10-20", "capsuleInnerHeightRange": "50-100", "numCapsules": 3,
		"motors": {axis: {"range": "-1;1"} for axis in ("x-rotation", "y-rotation", "z-rotation")},
		"feedbacks": 0, "oscillators": oscillators, "inputs": inputs, "motorController": controller(kind),
	}


def ga_config(profile, kind):
	return {
		"algorithm": {"type": "GeneticAlgorithm", "arguments": {
			"population": {"size": 96, "generation": 0, "evaluations": 0, "eliteCount": 4, "evaluationTimeoutSeconds": 180, "checkpointIntervalSeconds": 60},
			"crossover": {"rate": 0.1, "competitionSize": {"reproduce": 3, "eliminate": 3}, "numParameterChangedRatioRange": "0.05-0.3", "changeRatioRange": "0.25-0.75"},
			"mutation": {"rate": 0.5, "competitionSize": {"reproduce": 3, "eliminate": 3}, "parentSelection": "tournament-v1", "config": {"mode": "shared-offset-v1" if kind == "mlp" else "independent-offset-v1", "numParameterChangedRatioRange": "0.01-0.15", "offsetRange": "0.001;0.2", "offsetSampling": "log-uniform-v1", "offsetExponent": 1, "randomizeSign": "yes"}},
		}},
		"experiment": common_experiment(profile),
		"structure": {"generator": generator(kind), "templates": [{"id": MORPHOLOGIES[0][0], "structure": structure(MORPHOLOGIES[0], kind)}], "creatures": []},
	}


def structure(morphology_spec, kind="harmonic"):
	identifier, dimensions = morphology_spec
	base = generator(kind)
	return {"capsules": morphology(identifier, dimensions), "feedbacks": 0, "oscillators": base["oscillators"], "inputs": base["inputs"]}


def qd_config():
	profile = "me-v2-harmonic-qd-01"
	return {
		"algorithm": {"type": "MapElites", "arguments": {
			"population": {"size": 192, "generation": 0, "evaluations": 0, "evaluationTimeoutSeconds": 180, "checkpointIntervalSeconds": 60},
			"archive": {"binsPerAxis": 8, "axes": ["airborneFraction", "rotationParticipation"]},
			"mutation": {"config": {"mode": "independent-offset-v1", "numParameterChangedRatioRange": "0.01-0.15", "offsetRange": "0.001;0.2", "offsetSampling": "log-uniform-v1", "offsetExponent": 1, "randomizeSign": "yes"}},
		}},
		"experiment": common_experiment(profile),
		"structure": {"generator": generator("harmonic"), "templates": [{"id": identifier, "structure": structure(spec)} for spec in MORPHOLOGIES for identifier in [spec[0]]], "creatures": []},
	}


def write(name, config):
	path = CONFIG_DIR / name
	path.write_text(json.dumps(config, indent=2) + "\n")
	print(path)


write("me-v2-mlp-ga-m0.json", ga_config("me-v2-mlp-ga-m0", "mlp"))
write("me-v2-harmonic-ga-m0.json", ga_config("me-v2-harmonic-ga-m0", "harmonic"))
write("me-v2-harmonic-qd-01.json", qd_config())
