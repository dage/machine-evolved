#!/usr/bin/env python3

import json
import pathlib
import subprocess
import tempfile
import unittest


SCRIPT = pathlib.Path(__file__).with_name("prepare-population-robustness.py")


def source_config():
	return {
		"experiment": {
			"profile": "source",
			"seed": 1,
			"physics": {
				"gravityZ": -100,
				"groundFriction": 0.8,
				"capsuleFriction": 0.8,
			},
			"evaluationDomains": [
				{ "id": "nominal", "physics": {} },
				{ "id": "slick", "physics": { "groundFriction": 0.45 } },
				{ "id": "rough", "physics": { "groundFriction": 1.2 } },
			],
			"trainerState": { "discard": True },
		},
		"algorithm": {
			"arguments": {
				"population": { "size": 2, "generation": 7, "evaluations": 14 },
				"crossover": { "rate": 0.5 },
				"mutation": { "rate": 0.5 },
			}
		},
		"structure": {
			"creatures": [
				{ "fitness": 10.0, "data": { "metadata": { "creatureId": "a" } } },
				{ "fitness": 20.0, "data": { "metadata": { "creatureId": "b" } } },
			]
		},
	}


class PreparePopulationRobustnessTests(unittest.TestCase):
	def run_prepare(self, single_domain, config=None):
		with tempfile.TemporaryDirectory() as directory:
			root = pathlib.Path(directory)
			checkpoint = root / "checkpoint.json"
			output = root / "output.json"
			checkpoint.write_text(json.dumps(config or source_config()))
			command = [
				"python3", str(SCRIPT),
				"--checkpoint", str(checkpoint),
				"--case", "gravity-99",
				"--top", "2",
				"--physics", "gravityZ=-99",
				"--seed", "240909",
				"--output", str(output),
			]
			if single_domain:
				command.append("--single-domain")
			subprocess.run(command, check=True, capture_output=True, text=True)
			return json.loads(output.read_text())

	def test_default_preserves_training_domain_ring(self):
		result = self.run_prepare(single_domain=False)
		self.assertEqual(result["experiment"]["evaluationDomains"], source_config()["experiment"]["evaluationDomains"])
		self.assertNotIn("evaluationMode", result["experiment"]["populationRobustness"])

	def test_single_domain_isolates_requested_holdout(self):
		result = self.run_prepare(single_domain=True)
		self.assertEqual(
			result["experiment"]["evaluationDomains"],
			[{ "id": "gravity-99", "physics": {} }],
		)
		metadata = result["experiment"]["populationRobustness"]
		self.assertEqual(metadata["evaluationMode"], "single-domain-v1")
		self.assertEqual(len(metadata["sourceEvaluationDomainsSha256"]), 64)
		self.assertEqual([item["creatureId"] for item in metadata["candidates"]], ["b", "a"])
		self.assertEqual(result["experiment"]["physics"]["gravityZ"], -99.0)
		self.assertNotIn("trainerState", result["experiment"])
		self.assertEqual(result["algorithm"]["arguments"]["population"]["size"], 2)

	def test_absent_crossover_is_already_disabled(self):
		config = source_config()
		del config["algorithm"]["arguments"]["crossover"]
		result = self.run_prepare(single_domain=True, config=config)
		arguments = result["algorithm"]["arguments"]
		self.assertNotIn("crossover", arguments)
		self.assertEqual(arguments["mutation"]["rate"], 0)


if __name__ == "__main__":
	unittest.main()
