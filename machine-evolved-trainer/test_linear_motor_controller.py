import copy
import math
import random
import unittest

from LinearMotorController import LinearMotorController


class LinearMotorControllerTest(unittest.TestCase):
	GENERATOR = {
		"schemaVersion": 2,
		"layers": [
			{ "neurons": 3, "activation": "tanh" },
			{ "activation": "linear" },
		],
	}

	MUTATION_CONFIG = {
		"numParameterChangedRatioRange": "0.5-0.5",
		"offsetRange": "0.1;0.3",
		"offsetExponent": 1,
		"randomizeSign": "yes",
	}

	def createMutationController(self):
		return LinearMotorController(4, 2, generatorJson=copy.deepcopy(self.GENERATOR))

	@staticmethod
	def flattenParameters(controller):
		return [
			value
			for layer in controller.layers
			for key in ("weights", "biases")
			for value in layer[key]
		]

	def test_v2_has_one_bias_per_output_and_scaled_weights(self):
		random.seed(7)
		controller = LinearMotorController(
			4,
			2,
			generatorJson={
				"schemaVersion": 2,
				"layers": [
					{ "neurons": 3, "activation": "tanh" },
					{ "activation": "linear" },
				],
			},
		)
		self.assertEqual(controller.schemaVersion, 2)
		self.assertEqual([len(layer["weights"]) for layer in controller.layers], [12, 6])
		self.assertEqual([len(layer["biases"]) for layer in controller.layers], [3, 2])
		self.assertTrue(all(bias == 0 for layer in controller.layers for bias in layer["biases"]))
		self.assertEqual(controller.getNumParameters(), 23)
		self.assertEqual(len({controller.transformWeightIndex(i) for i in range(23)}), 23)

	def test_unversioned_state_remains_v1_compatible(self):
		state = {
			"layers": [{
				"activation": "linear",
				"weights": [1.0, 2.0, 3.0, 4.0],
				"biases": [0.0, 0.0, 0.0, 0.0],
			}],
		}
		controller = LinearMotorController(2, 2, stateJson=state)
		self.assertEqual(controller.schemaVersion, 1)
		self.assertEqual(controller.getNumParameters(), 8)

	def test_mutation_defaults_to_legacy_shared_offset_behavior(self):
		defaultController = self.createMutationController()
		explicitController = copy.deepcopy(defaultController)
		before = self.flattenParameters(defaultController)

		random.seed(19)
		defaultController.mutate(copy.deepcopy(self.MUTATION_CONFIG))
		random.seed(19)
		explicitConfig = copy.deepcopy(self.MUTATION_CONFIG)
		explicitConfig["mode"] = LinearMotorController.SHARED_OFFSET_MODE
		explicitController.mutate(explicitConfig)

		self.assertEqual(defaultController.getJson(), explicitController.getJson())

		after = self.flattenParameters(defaultController)
		deltas = [new - old for old, new in zip(before, after) if new != old]
		self.assertEqual(len(deltas), int(0.5 * defaultController.getNumParameters()))
		self.assertTrue(all(math.isclose(delta, deltas[0]) for delta in deltas))

	def test_independent_mutation_changes_selected_count_with_mixed_offsets(self):
		controller = self.createMutationController()
		before = self.flattenParameters(controller)
		config = copy.deepcopy(self.MUTATION_CONFIG)
		config["mode"] = LinearMotorController.INDEPENDENT_OFFSET_MODE

		random.seed(19)
		controller.mutate(config)

		after = self.flattenParameters(controller)
		deltas = [new - old for old, new in zip(before, after) if new != old]
		self.assertEqual(len(deltas), int(0.5 * controller.getNumParameters()))
		self.assertTrue(any(delta < 0 for delta in deltas))
		self.assertTrue(any(delta > 0 for delta in deltas))
		self.assertGreater(len({abs(delta) for delta in deltas}), 1)

	def test_log_uniform_offsets_span_small_and_large_scales_symmetrically(self):
		controller = self.createMutationController()
		config = copy.deepcopy(self.MUTATION_CONFIG)
		config["offsetRange"] = "0.0001;0.5"
		config["offsetSampling"] = LinearMotorController.LOG_UNIFORM_OFFSET_SAMPLING
		random.seed(71)
		offsets = [controller._sampleMutationOffset(config) for _ in range(1000)]

		self.assertTrue(any(offset < 0 for offset in offsets))
		self.assertTrue(any(offset > 0 for offset in offsets))
		self.assertLess(min(abs(offset) for offset in offsets), 0.0002)
		self.assertGreater(max(abs(offset) for offset in offsets), 0.4)

	def test_log_uniform_offsets_reject_non_positive_bounds(self):
		controller = self.createMutationController()
		config = copy.deepcopy(self.MUTATION_CONFIG)
		config["offsetRange"] = "0;0.5"
		config["offsetSampling"] = LinearMotorController.LOG_UNIFORM_OFFSET_SAMPLING
		with self.assertRaisesRegex(ValueError, "positive ascending bounds"):
			controller._sampleMutationOffset(config)

	def test_target_angle_metadata_round_trips_for_harmonic_controller(self):
		generator = {
			"schemaVersion": 2,
			"commandMode": "target-angle-servo-v1",
			"servo": {"targetAngleRangeRadians": 2.8, "kp": 10, "kd": 0.75},
			"layers": [{"activation": "tanh"}],
		}
		controller = LinearMotorController(32, 6, generatorJson=generator)
		self.assertEqual(controller.getNumParameters(), 198)
		serialized = controller.getJson()
		restored = LinearMotorController(32, 6, stateJson=serialized)
		self.assertEqual(restored.getJson(), serialized)


if __name__ == "__main__":
	unittest.main()
