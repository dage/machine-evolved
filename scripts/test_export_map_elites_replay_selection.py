import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("export-map-elites-replay-selection.py")
SPEC = importlib.util.spec_from_file_location("export_map_elites_replay_selection", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def candidate(creature_id, morphology_id, fitness, controller_size, domain_scores=None):
	return {
		"fitness": fitness,
		"data": {
			"metadata": {
				"creatureId": creature_id,
				"morphologyId": morphology_id,
			},
			"structure": {
				"capsules": [{"id": "{}-body".format(creature_id)}],
			},
			"motorController": {
				"layers": [{"weights": list(range(controller_size)), "biases": []}],
			},
		},
		"evaluation": {
			"behavior": {"airborneFraction": 0.25, "rotationParticipation": 0.5},
			"domainScores": list(domain_scores if domain_scores is not None else [fitness]),
		},
	}


def checkpoint(creatures):
	return {
		"algorithm": {
			"type": "MapElites",
			"arguments": {
				"population": {"size": 99, "evaluations": 123},
				"archive": {"binsPerAxis": 7},
				"mutation": {"config": {"mode": "arbitrary"}},
			},
		},
		"experiment": {
			"profile": "overnight-test",
			"backend": "machine-evolved-bullet-v2",
			"physics": {"gravityZ": -321, "nested": {"unchanged": True}},
			"objective": {"id": "test-objective", "horizonTicks": 42},
			"evaluationDomains": [
				{"id": "first", "physics": {"groundFriction": 0.25}},
				{"id": "second", "objective": {"penalty": 3}},
			],
			"trainerState": {"largeAndNotReplayRelevant": list(range(20))},
		},
		"structure": {
			"generator": {"motorController": {"layers": [{"activation": "tanh"}]}},
			"templates": [{"id": "not-assumed-by-exporter"}],
			"creatures": creatures,
		},
	}


def file_sha256(path):
	return hashlib.sha256(path.read_bytes()).hexdigest()


class ExportMapElitesReplaySelectionTests(unittest.TestCase):
	def test_exports_exact_creatures_and_replay_contract_for_both_selections(self):
		creatures = [
			candidate("zeta", "morph/long α", 10, 2, [12, 8]),
			candidate("beta", "β strange morphology", 10, 17, [11, 9]),
			candidate("alpha", "morph/long α", 10, 5, [13, 7]),
			candidate("low-a", "morph/long α", 4, 1, [4, 4]),
			candidate("low-b", "β strange morphology", 3, 33, [3, 3]),
			candidate("pending", "ignored pending", None, 101, []),
		]
		source_document = checkpoint(creatures)
		with tempfile.TemporaryDirectory() as directory:
			root = Path(directory)
			checkpoint_path = root / "checkpoint.json"
			checkpoint_path.write_text(json.dumps(source_document), encoding="utf-8")
			output = root / "selection"
			manifest = MODULE.export_selection(checkpoint_path, output, top=2)

			self.assertEqual(
				[item["creatureId"] for item in manifest["topOverall"]],
				["alpha", "zeta"],
			)
			self.assertEqual(
				[
					(group["morphologyId"], [item["creatureId"] for item in group["candidates"]])
					for group in manifest["topPerMorphology"]
				],
				[
					("morph/long α", ["alpha", "zeta"]),
					("β strange morphology", ["beta", "low-b"]),
				],
			)
			self.assertEqual(manifest["selection"]["finiteCandidateCount"], 5)
			self.assertEqual(manifest["selection"]["exportedUniqueCandidateCount"], 4)
			self.assertEqual(manifest["replayContract"]["firstReplayDomainId"], "first")
			self.assertEqual(
				manifest["sourceCheckpoint"]["sha256"], file_sha256(checkpoint_path)
			)

			by_id = {item["creatureId"]: item for item in manifest["candidates"]}
			self.assertEqual(by_id["alpha"]["sourceOverallRank"], 1)
			self.assertEqual(by_id["alpha"]["sourceMorphologyRank"], 1)
			self.assertEqual(by_id["beta"]["sourceOverallRank"], 3)
			self.assertEqual(by_id["beta"]["sourceMorphologyRank"], 1)
			self.assertEqual(by_id["beta"]["expectedReplayFitness"], 11)

			source_by_id = {
				item["data"]["metadata"]["creatureId"]: item
				for item in creatures
			}
			for creature_id, manifest_entry in by_id.items():
				config_path = output / manifest_entry["config"]["path"]
				self.assertEqual(manifest_entry["config"]["sha256"], file_sha256(config_path))
				exported = json.loads(config_path.read_text(encoding="utf-8"))
				self.assertEqual(exported["algorithm"], {"type": "MapElites"})
				self.assertNotIn("crossover", json.dumps(exported["algorithm"]))
				self.assertEqual(exported["structure"]["creatures"], [source_by_id[creature_id]])
				self.assertEqual(exported["experiment"]["physics"], source_document["experiment"]["physics"])
				self.assertEqual(exported["experiment"]["objective"], source_document["experiment"]["objective"])
				self.assertEqual(
					exported["experiment"]["evaluationDomains"],
					source_document["experiment"]["evaluationDomains"],
				)
				self.assertNotIn("trainerState", exported["experiment"])
				self.assertEqual(
					exported["selectionProvenance"]["sourceCreatureId"], creature_id
				)
				self.assertEqual(
					len(exported["structure"]["creatures"][0]["data"]["motorController"]["layers"][0]["weights"]),
					len(source_by_id[creature_id]["data"]["motorController"]["layers"][0]["weights"]),
				)

	def test_tie_breaks_and_serialized_outputs_are_deterministic(self):
		creatures = [
			candidate("same-b", "morph-z", 8, 3),
			candidate("same-c", "morph-a", 8, 9),
			candidate("same-a", "morph-z", 8, 4),
			candidate("higher", "morph-z", 9, 2),
		]
		with tempfile.TemporaryDirectory() as directory:
			root = Path(directory)
			checkpoint_path = root / "checkpoint.json"
			checkpoint_path.write_text(json.dumps(checkpoint(creatures)), encoding="utf-8")
			first = root / "first"
			second = root / "second"
			first_manifest = MODULE.export_selection(checkpoint_path, first, top=4)
			second_manifest = MODULE.export_selection(checkpoint_path, second, top=4)

			self.assertEqual(
				[item["creatureId"] for item in first_manifest["topOverall"]],
				["higher", "same-c", "same-a", "same-b"],
			)
			self.assertEqual(
				(first / "selection-manifest.json").read_bytes(),
				(second / "selection-manifest.json").read_bytes(),
			)
			first_configs = sorted((first / "configs").iterdir())
			second_configs = sorted((second / "configs").iterdir())
			self.assertEqual([path.name for path in first_configs], [path.name for path in second_configs])
			self.assertEqual(
				[path.read_bytes() for path in first_configs],
				[path.read_bytes() for path in second_configs],
			)

	def test_rejects_non_map_elites_and_duplicate_creature_ids(self):
		document = checkpoint([candidate("duplicate", "m-a", 2, 1)])
		document["algorithm"]["type"] = "GeneticAlgorithm"
		with self.assertRaisesRegex(ValueError, "MapElites"):
			MODULE.load_candidates(document)

		duplicate = checkpoint([
			candidate("duplicate", "m-a", 2, 1),
			candidate("duplicate", "m-b", 1, 8),
		])
		with self.assertRaisesRegex(ValueError, "unique"):
			MODULE.load_candidates(duplicate)

	def test_selection_does_not_mutate_loaded_checkpoint(self):
		document = checkpoint([candidate("one", "m-one", 1, 7)])
		original = copy.deepcopy(document)
		MODULE.load_candidates(document)
		self.assertEqual(document, original)


if __name__ == "__main__":
	unittest.main()
