#!/usr/bin/env python3

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("export-movement-dossier.py")
SPEC = importlib.util.spec_from_file_location("export_movement_dossier", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def pose(x=0.0, y=0.0, z=0.0):
	return {
		"translation": {"x": x, "y": y, "z": z},
		"rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
	}


class ExportMovementDossierTests(unittest.TestCase):
	def test_report_is_selected_creature_measurement_not_stale_champion_opinion(self):
		with tempfile.TemporaryDirectory() as directory:
			path = Path(directory) / "replay.json"
			parts0 = {"a": pose(), "b": pose(), "c": pose()}
			parts1 = {"a": pose(x=1.0), "b": pose(x=1.0), "c": pose(x=1.0)}
			path.write_text(json.dumps({
				"kind": "machine-evolved-replay",
				"schemaVersion": 1,
				"profile": "test-selected",
				"creatureId": "candidate-a",
				"sampleHz": 1,
				"durationSeconds": 1,
				"displayScale": 1,
				"configuredFitness": 1,
				"measuredFitness": 1,
				"fitnessParity": {"verified": True},
				"coordinateSystem": {"upAxis": "Y", "horizontalAxes": ["X", "Z"]},
				"sourceCoordinateSystem": {"upAxis": "Y", "horizontalAxes": ["X", "Z"], "units": "simulation"},
				"capsules": [
					{"id": "a", "innerHeight": 1, "radius": 0.1},
					{"id": "b", "innerHeight": 1, "radius": 0.1},
					{"id": "c", "innerHeight": 1, "radius": 0.1},
				],
				"physics": {
					"gravityX": 0, "gravityY": 0, "gravityZ": -100,
					"groundFriction": 0.8, "capsuleFriction": 0.8,
					"capsuleRollingFriction": 0.02, "capsuleSpinningFriction": 0.02,
					"capsuleLinearDamping": 0, "capsuleAngularDamping": 0,
					"capsuleMassScale": 0.0001, "motorMaxForce": 5000,
				},
				"objective": {"id": "distance", "metric": "horizontal"},
				"motionMetrics": {
					"finalDistanceSimulationUnits": 1,
					"pathLengthSimulationUnits": 1,
					"finalToMaxDistanceRatio": 1,
					"nearGroundTimeFraction": 1,
					"unsupportedPathFraction": 0,
					"longestUnsupportedSeconds": 0,
					"rollingExplainedFraction": 0.1,
					"rootRollingCoupling": 0.1,
					"rootTransverseTravelFraction": 0.1,
					"rootAxisStability": 1,
					"rootSpinRateRadiansPerSecond": 0,
				},
				"samples": [
					{"tick": 0, "poses": {"body": pose(), "parts": parts0}},
					{"tick": 1, "poses": {"body": pose(x=1.0), "parts": parts1}},
				],
			}))
			report = MODULE.build_report(path)
			self.assertIn("selected creature", report)
			self.assertIn("1 Hz pose", report)
			self.assertIn("COMPLETE 1 HZ POSE TRACE", report)
			self.assertIn("without classifying the gait", report.replace("\n", " "))
			self.assertNotIn("current raw-distance champion", report)
			self.assertNotIn("About 72.9%", report)


if __name__ == "__main__":
	unittest.main()
