import copy
import json
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from Trainer import GeneticAlgorithm, wallClockLimitReached


class GeneticAlgorithmTest(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		configPath = Path(__file__).parent / "configs" / "smoke-three-capsule.json"
		with configPath.open() as source:
			cls.config = json.load(source)

	def createAlgorithm(self):
		arguments = copy.deepcopy(self.config["algorithm"]["arguments"])
		structure = copy.deepcopy(self.config["structure"])
		return GeneticAlgorithm(
			arguments["population"],
			arguments["crossover"],
			arguments["mutation"],
			structure,
			{ "saveState": lambda: None },
		)

	def test_instances_do_not_share_population_state(self):
		random.seed(1)
		first = self.createAlgorithm()
		random.seed(1)
		second = self.createAlgorithm()

		self.assertEqual(len(first.individuals), 2)
		self.assertEqual(len(second.individuals), 2)
		self.assertIsNot(first.individuals, second.individuals)
		self.assertEqual(
			first.individuals[0][first.CREATURE].motorController.layers,
			second.individuals[0][second.CREATURE].motorController.layers,
		)

	def test_best_index_can_be_the_first_individual(self):
		algorithm = self.createAlgorithm()
		algorithm.individuals[0][algorithm.FITNESS] = 10.0
		algorithm.individuals[1][algorithm.FITNESS] = 5.0

		self.assertEqual(algorithm.getIndexBestCreature(), 0)

	def test_reissued_evaluation_invalidates_the_previous_token(self):
		algorithm = self.createAlgorithm()
		creatureId = algorithm.individuals[0][algorithm.CREATURE].id
		first = algorithm.startEvaluation(creatureId)
		second = algorithm.startEvaluation(creatureId)

		self.assertNotEqual(first, second)
		self.assertFalse(algorithm.isCurrentEvaluation(creatureId, first))
		self.assertTrue(algorithm.isCurrentEvaluation(creatureId, second))

	def test_invalid_replacement_fraction_fails_instead_of_spinning(self):
		arguments = copy.deepcopy(self.config["algorithm"]["arguments"])
		arguments["population"]["size"] = 16
		arguments["crossover"]["rate"] = 0.25
		arguments["crossover"]["competitionSize"] = { "reproduce": 4, "eliminate": 4 }
		arguments["mutation"]["rate"] = 0.75
		arguments["mutation"]["competitionSize"] = { "reproduce": 4, "eliminate": 4 }

		with self.assertRaisesRegex(ValueError, "replace too much"):
			GeneticAlgorithm(
				arguments["population"],
				arguments["crossover"],
				arguments["mutation"],
				copy.deepcopy(self.config["structure"]),
				{ "saveState": lambda: None },
			)

	def test_wall_clock_limit_uses_elapsed_seconds(self):
		self.assertFalse(wallClockLimitReached(10.0, None, 100.0))
		self.assertFalse(wallClockLimitReached(10.0, 30.0, 39.999))
		self.assertTrue(wallClockLimitReached(10.0, 30.0, 40.0))

	def test_missing_fitness_serializes_as_null_and_reloads(self):
		algorithm = self.createAlgorithm()
		serialized = algorithm.getCreaturesWithFitnessJson()
		self.assertEqual([item["fitness"] for item in serialized], [None, None])
		json.dumps(serialized, allow_nan=False)

		arguments = copy.deepcopy(self.config["algorithm"]["arguments"])
		structure = copy.deepcopy(self.config["structure"])
		structure["creatures"] = serialized
		reloaded = GeneticAlgorithm(
			arguments["population"],
			arguments["crossover"],
			arguments["mutation"],
			structure,
			{ "saveState": lambda: None },
		)
		self.assertEqual(reloaded.indicesMissingFitness, [0, 1])


if __name__ == "__main__":
	unittest.main()
