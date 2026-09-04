#!/usr/bin/env python3

import json
import pathlib
import subprocess
import tempfile
import unittest


SCRIPT = pathlib.Path(__file__).with_name("summarize-population-robustness.py")


class SummarizePopulationRobustnessTests(unittest.TestCase):
	def test_map_elites_history_is_joined_by_original_creature_id(self):
		with tempfile.TemporaryDirectory() as directory:
			root = pathlib.Path(directory)
			config = root / "case.json"
			output = root / "summary.json"
			config.write_text(json.dumps({
				"experiment": {
					"populationRobustness": {
						"case": "nominal",
						"candidates": [
							{"index": 0, "creatureId": "a", "creatureSha256": "ha", "baselineFitness": 10.0},
							{"index": 1, "creatureId": "b", "creatureSha256": "hb", "baselineFitness": 20.0},
						],
					},
					"trainerState": {"evaluationHistory": [
						{"creatureId": "b", "robustFitness": 18.0},
						{"creatureId": "a", "robustFitness": 9.0},
						{"creatureId": "generated", "robustFitness": 999.0},
					]},
				},
				"structure": {"creatures": [
					{"fitness": None},
					{"fitness": 999.0},
				]},
			}))
			subprocess.run(
				["python3", str(SCRIPT), "--config", str(config), "--output", str(output)],
				check=True,
				capture_output=True,
				text=True,
			)
			result = json.loads(output.read_text())
			by_index = {item["index"]: item for item in result["candidates"]}
			self.assertEqual(by_index[0]["cases"]["nominal"], 9.0)
			self.assertEqual(by_index[1]["cases"]["nominal"], 18.0)

	def test_duplicate_candidate_ids_fail_closed(self):
		with tempfile.TemporaryDirectory() as directory:
			root = pathlib.Path(directory)
			config = root / "case.json"
			config.write_text(json.dumps({
				"experiment": {
					"populationRobustness": {
						"case": "nominal",
						"candidates": [
							{"index": 0, "creatureId": "a", "creatureSha256": "ha", "baselineFitness": 10.0},
							{"index": 1, "creatureId": "a", "creatureSha256": "hb", "baselineFitness": 20.0},
						],
					},
					"trainerState": {"evaluationHistory": [{"creatureId": "a", "robustFitness": 9.0}]},
				},
				"structure": {"creatures": []},
			}))
			result = subprocess.run(
				["python3", str(SCRIPT), "--config", str(config), "--output", str(root / "summary.json")],
				capture_output=True,
				text=True,
			)
			self.assertNotEqual(result.returncode, 0)
			self.assertIn("duplicate candidate IDs", result.stderr)


if __name__ == "__main__":
	unittest.main()
