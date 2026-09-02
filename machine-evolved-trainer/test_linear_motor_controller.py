import random
import unittest

from LinearMotorController import LinearMotorController


class LinearMotorControllerTest(unittest.TestCase):
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


if __name__ == "__main__":
	unittest.main()
