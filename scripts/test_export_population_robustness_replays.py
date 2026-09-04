#!/usr/bin/env python3

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("export-population-robustness-replays.py")
SPEC = importlib.util.spec_from_file_location("export_population_robustness_replays", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ExportPopulationRobustnessReplaysTests(unittest.TestCase):
	def test_joins_history_by_creature_id_and_preserves_candidate_order(self):
		with tempfile.TemporaryDirectory() as directory:
			root = Path(directory)
			data_a = {"metadata": {"creatureId": "a"}, "value": 1}
			data_b = {"metadata": {"creatureId": "b"}, "value": 2}
			candidates = [
				{"index": 0, "creatureId": "a", "creatureSha256": MODULE.canonical_sha256(data_a), "baselineFitness": 10.0},
				{"index": 1, "creatureId": "b", "creatureSha256": MODULE.canonical_sha256(data_b), "baselineFitness": 20.0},
			]
			experiment = {
				"physics": {"gravityZ": -99},
				"objective": {"id": "distance"},
				"evaluationDomains": [{"id": "gravity-99", "physics": {}}],
				"populationRobustness": {"case": "gravity-99", "candidates": candidates},
			}
			source = {"algorithm": {"type": "MapElites"}, "experiment": experiment, "structure": {"creatures": [
				{"fitness": None, "data": data_a}, {"fitness": None, "data": data_b},
			]}}
			result = json.loads(json.dumps(source))
			result["experiment"]["trainerState"] = {"evaluationHistory": [
				{"creatureId": "b", "robustFitness": 18.0, "domainScores": [18.0]},
				{"creatureId": "a", "robustFitness": 9.0, "domainScores": [9.0]},
			]}
			source_path = root / "source.json"
			result_path = root / "result.json"
			source_path.write_text(json.dumps(source))
			result_path.write_text(json.dumps(result))
			manifest = MODULE.export_replays(source_path, result_path, root / "out")
			self.assertEqual([item["creatureId"] for item in manifest["candidates"]], ["a", "b"])
			first = json.loads((root / "out" / manifest["candidates"][0]["config"]).read_text())
			self.assertEqual(first["structure"]["creatures"][0]["fitness"], 9.0)
			self.assertNotIn("trainerState", first["experiment"])

	def test_duplicate_candidate_ids_fail_closed(self):
		with tempfile.TemporaryDirectory() as directory:
			root = Path(directory)
			data_a = {"metadata": {"creatureId": "a"}, "value": 1}
			candidates = [
				{"index": 0, "creatureId": "a", "creatureSha256": MODULE.canonical_sha256(data_a), "baselineFitness": 10.0},
				{"index": 1, "creatureId": "a", "creatureSha256": MODULE.canonical_sha256(data_a), "baselineFitness": 10.0},
			]
			experiment = {
				"physics": {"gravityZ": -99},
				"objective": {"id": "distance"},
				"evaluationDomains": [{"id": "gravity-99", "physics": {}}],
				"populationRobustness": {"case": "gravity-99", "candidates": candidates},
			}
			source = {"algorithm": {"type": "MapElites"}, "experiment": experiment, "structure": {"creatures": [
				{"fitness": None, "data": data_a},
			]}}
			result = json.loads(json.dumps(source))
			result["experiment"]["trainerState"] = {"evaluationHistory": [{"creatureId": "a", "robustFitness": 9.0}]}
			source_path = root / "source.json"
			result_path = root / "result.json"
			source_path.write_text(json.dumps(source))
			result_path.write_text(json.dumps(result))
			with self.assertRaisesRegex(ValueError, "duplicate creature IDs"):
				MODULE.export_replays(source_path, result_path, root / "out")


if __name__ == "__main__":
	unittest.main()
