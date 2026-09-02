import importlib.util
import math
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("analyze-replay.py")
SPEC = importlib.util.spec_from_file_location("analyze_replay", MODULE_PATH)
ANALYZER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYZER)


def quaternion_roll(angle):
	# Start with the capsule's long axis along display X, then roll around
	# that fixed axis while the body travels along display Z.
	half = angle / 2.0
	diagonal = math.sqrt(0.5)
	return {
		"x": math.sin(half) * diagonal,
		"y": math.sin(half) * diagonal,
		"z": -math.cos(half) * diagonal,
		"w": math.cos(half) * diagonal,
	}


def rolling_replay():
	capsule_id = "root"
	samples = []
	for tick in range(5):
		angle = tick * math.pi / 2.0
		position = {"x": 0.0, "y": 0.0, "z": angle}
		pose = {"translation": position, "rotation": quaternion_roll(angle)}
		samples.append({
			"tick": tick,
			"poses": {"body": pose, "parts": {capsule_id: pose}},
		})
	return {
		"durationSeconds": 4.0 / 60.0,
		"sampleHz": 60,
		"displayScale": 0.01,
		"configuredFitness": 1.0,
		"measuredMaxDistanceSimulationUnits": 1.0,
		"capsules": [{"id": capsule_id, "innerHeight": 0.0, "radius": 1.0}],
		"samples": samples,
	}


def nonrolling_replay():
	replay = rolling_replay()
	fixed_rotation = replay["samples"][0]["poses"]["body"]["rotation"]
	for sample in replay["samples"]:
		position = sample["poses"]["body"]["translation"]
		pose = {"translation": position, "rotation": fixed_rotation}
		sample["poses"] = {"body": pose, "parts": {"root": pose}}
	return replay


class RollingSignatureTest(unittest.TestCase):
	def analyze(self, replay, rolling=None, discount=None):
		return ANALYZER.analyze(replay, 0.02, 200.0, 200.0, 1.0, 0.0, rolling, discount)

	def test_signature_is_disabled_without_opt_in(self):
		result = self.analyze(rolling_replay())
		self.assertAlmostEqual(result["rootRollingCoupling"], 1.0, places=9)
		self.assertAlmostEqual(result["rootTransverseTravelFraction"], 1.0, places=9)
		self.assertAlmostEqual(result["rootAxisStability"], 0.0, places=9)
		self.assertFalse(result["rollingSignatureEnabled"])
		self.assertFalse(result["rollingSignature"])
		self.assertTrue(result["credibility"]["passes"])
		self.assertFalse(result["rollingDiscountEnabled"])
		self.assertAlmostEqual(result["selectedFitnessSimulationUnits"], result["rawMaxDistanceSimulationUnits"])

	def test_opted_in_signature_rejects_circumference_matched_roll(self):
		result = self.analyze(rolling_replay(), {"enabled": True})
		self.assertTrue(result["rollingSignatureEnabled"])
		self.assertTrue(result["rollingSignature"])
		self.assertFalse(result["credibility"]["passes"])

	def test_replay_config_is_used_for_parity(self):
		replay = rolling_replay()
		replay["motionMetrics"] = {"rollingSignatureConfig": {"enabled": True}}
		result = self.analyze(replay)
		self.assertTrue(result["rollingSignature"])
		self.assertFalse(result["credibility"]["passes"])

	def test_opted_in_discount_reduces_pure_transverse_roll(self):
		result = self.analyze(rolling_replay(), discount={"enabled": True})
		self.assertTrue(result["rollingDiscountEnabled"])
		self.assertAlmostEqual(result["rollingDiscountLambda"], 1.0)
		self.assertGreater(result["rollingExplainedFraction"], 0.5)
		self.assertLess(result["selectedFitnessSimulationUnits"], result["rawMaxDistanceSimulationUnits"])
		self.assertAlmostEqual(
			result["selectedFitnessSimulationUnits"],
			result["rawMaxDistanceSimulationUnits"] * (1.0 - result["rollingExplainedFraction"]),
			places=12,
		)

	def test_opted_in_discount_retains_nonrolling_travel(self):
		result = self.analyze(nonrolling_replay(), discount={"enabled": True})
		self.assertTrue(result["rollingDiscountEnabled"])
		self.assertAlmostEqual(result["rollingExplainedFraction"], 0.0, places=12)
		self.assertAlmostEqual(result["selectedFitnessSimulationUnits"], result["rawMaxDistanceSimulationUnits"])

	def test_replay_discount_config_preserves_nondefault_lambda(self):
		replay = rolling_replay()
		replay["motionMetrics"] = {
			"rollingDiscountEnabled": True,
			"rollingDiscountLambda": 0.25,
			"rollingDiscountEpsilonSimulationUnits": 1e-6,
		}
		result = self.analyze(replay)
		self.assertTrue(result["rollingDiscountEnabled"])
		self.assertAlmostEqual(result["rollingDiscountLambda"], 0.25)
		self.assertAlmostEqual(
			result["selectedFitnessSimulationUnits"],
			result["rawMaxDistanceSimulationUnits"] * (1.0 - 0.25 * result["rollingExplainedFraction"]),
			places=12,
		)


if __name__ == "__main__":
	unittest.main()
