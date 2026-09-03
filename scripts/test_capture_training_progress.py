import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("capture-training-progress.py")
SPEC = importlib.util.spec_from_file_location("capture_training_progress", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CaptureTrainingProgressTests(unittest.TestCase):
	def config(self, include_selector=True):
		arms = {
			"small-independent": {
				"selections": 7, "attempts": 6, "outcomes": 5,
				"failures": 1, "invalidOutcomes": 1, "terminalFailures": 0,
				"coverageGains": 2, "replacements": 1, "rejections": 2,
				"globalBests": 1, "positiveQdGain": 4.5, "normalizedReward": 0.45,
			},
			"large-independent": {
				"selections": 3, "attempts": 3, "outcomes": 2,
				"failures": 0, "invalidOutcomes": 0, "terminalFailures": 0,
				"coverageGains": 1, "replacements": 1, "rejections": 0,
				"globalBests": 0, "positiveQdGain": 2.0, "normalizedReward": 0.2,
			},
		}
		mutation = {}
		if include_selector:
			mutation["adaptiveSelector"] = {
				"enabled": True,
				"state": {
					"schemaVersion": 1,
					"totalSelections": 10,
					"totalAttempts": 9,
					"totalOutcomes": 7,
					"totalFailures": 1,
					"totalInvalidOutcomes": 1,
					"totalTerminalFailures": 0,
					"totalPositiveQdGain": 6.5,
					"totalNormalizedReward": 0.65,
					"telemetryBaseline": {
						"kind": "fresh-run", "selection": 0, "outcome": 0,
						"completeBeforeBaseline": True,
					},
					"arms": arms,
				},
			}
		def creature(fitness, morphology):
			return {
				"fitness": fitness,
				"data": {"metadata": {"morphologyId": morphology}},
			}
		return {
			"algorithm": {"arguments": {
				"population": {"generation": 3, "evaluations": 27},
				"archive": {"binsPerAxis": 2, "axes": ["airborneFraction", "rotationParticipation"]},
				"mutation": mutation,
			}},
			"experiment": {"trainerState": {
				"evaluationSimulations": 81,
				"bestFitnessEvaluation": 21,
				"domainProgress": {"pending": {}},
			}},
			"structure": {
				"templates": [{"id": "m-a"}, {"id": "m-b"}],
				"creatures": [
					creature(10.0, "m-a"), creature(6.0, "m-a"),
					creature(8.0, "m-b"), creature(-2.0, "m-b"),
					{"fitness": None, "data": {"metadata": {"morphologyId": "m-a"}}},
				],
			},
		}

	def test_summary_reports_qd_top_sets_emitters_and_morphologies(self):
		summary = MODULE.summarize(self.config())
		self.assertEqual(summary["qdScore"], 22.0)
		self.assertIsNone(summary["normalizedQdScore"])
		self.assertAlmostEqual(summary["sampleRelativeNormalizedQdScore"], 0.3)
		self.assertFalse(summary["normalizedQdDefinition"]["comparableAcrossSamples"])
		self.assertEqual(summary["normalizedQdDefinition"]["kind"], "sample-relative-diagnostic")
		self.assertEqual(summary["normalizedQdDefinition"]["totalArchiveCells"], 8)
		self.assertEqual(summary["normalizedQdDefinition"]["emptyCellFitness"], 0.0)
		self.assertEqual(summary["top5"]["fitnesses"], [10.0, 8.0, 6.0, -2.0])
		self.assertEqual(summary["top12"]["meanRobustFitness"], 5.5)
		self.assertEqual(summary["morphologies"]["m-a"]["qdScore"], 16.0)
		self.assertIsNone(summary["morphologies"]["m-a"]["normalizedQdScore"])
		self.assertAlmostEqual(summary["morphologies"]["m-a"]["sampleRelativeNormalizedQdScore"], 0.2)
		self.assertEqual(summary["morphologies"]["m-b"]["top5"]["fitnesses"], [8.0, -2.0])

		selector = summary["adaptiveEmitterSelector"]
		self.assertTrue(selector["enabled"])
		self.assertEqual(selector["totalSelections"], 10)
		self.assertEqual(selector["totalAttempts"], 9)
		self.assertEqual(selector["totalInvalidOutcomes"], 1)
		self.assertEqual(selector["totalPositiveQdGain"], 6.5)
		self.assertEqual(selector["telemetryBaseline"]["kind"], "fresh-run")
		self.assertEqual(selector["outcomes"], {
			"coverageGains": 3, "replacements": 2, "rejections": 2, "globalBests": 1,
		})
		self.assertEqual(selector["emitters"]["small-independent"]["failures"], 1)

	def test_explicit_frozen_reference_makes_normalized_qd_comparable(self):
		summary = MODULE.summarize(self.config(), qd_normalization_reference=800.0)
		self.assertAlmostEqual(summary["normalizedQdScore"], 0.03)
		self.assertAlmostEqual(summary["sampleRelativeNormalizedQdScore"], 0.3)
		self.assertTrue(summary["normalizedQdDefinition"]["comparableAcrossSamples"])
		self.assertEqual(summary["normalizedQdDefinition"]["kind"], "frozen-shared")
		self.assertEqual(summary["normalizedQdDefinition"]["denominator"], 800.0)
		self.assertAlmostEqual(summary["morphologies"]["m-a"]["normalizedQdScore"], 0.02)

	def test_legacy_config_has_empty_zeroed_selector_summary(self):
		summary = MODULE.summarize(self.config(include_selector=False))
		selector = summary["adaptiveEmitterSelector"]
		self.assertFalse(selector["enabled"])
		self.assertEqual(selector["totalSelections"], 0)
		self.assertEqual(selector["totalPositiveQdGain"], 0.0)
		self.assertEqual(selector["emitters"], {})

	def test_normalized_qd_is_undefined_without_a_positive_reference(self):
		config = self.config(include_selector=False)
		for item in config["structure"]["creatures"]:
			if item.get("fitness") is not None:
				item["fitness"] = -1.0
		summary = MODULE.summarize(config)
		self.assertEqual(summary["qdScore"], -4.0)
		self.assertIsNone(summary["normalizedQdScore"])
		self.assertIsNone(summary["sampleRelativeNormalizedQdScore"])

	def test_frozen_reference_must_be_positive(self):
		with self.assertRaisesRegex(ValueError, "must be positive"):
			MODULE.summarize(self.config(), qd_normalization_reference=0.0)


if __name__ == "__main__":
	unittest.main()
