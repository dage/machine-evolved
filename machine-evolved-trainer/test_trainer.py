import copy
import json
import math
import random
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from Trainer import GeneticAlgorithm, Trainer, randomStateFromJson, restoreRandomState, wallClockLimitReached


class GeneticAlgorithmTest(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		configPath = Path(__file__).parent / "configs" / "smoke-three-capsule.json"
		with configPath.open() as source:
			cls.config = json.load(source)

	def createAlgorithm(self, populationSize=None):
		arguments = copy.deepcopy(self.config["algorithm"]["arguments"])
		if populationSize is not None:
			arguments["population"]["size"] = populationSize
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

	def test_reproduction_winner_is_selected_from_the_sampled_tournament(self):
		algorithm = self.createAlgorithm(populationSize=3)
		algorithm.individuals[0][algorithm.FITNESS] = 100.0
		algorithm.individuals[1][algorithm.FITNESS] = -10.0
		algorithm.individuals[2][algorithm.FITNESS] = -5.0
		algorithm.pickIndividuals = lambda competitionSize, excludedIndices=None: [1, 2]

		selected = algorithm._findReproduceIndex(2)

		self.assertEqual(selected, 2)
		self.assertIn(selected, [1, 2])

	def test_elimination_loser_is_selected_from_the_sampled_tournament(self):
		algorithm = self.createAlgorithm(populationSize=3)
		algorithm.individuals[0][algorithm.FITNESS] = -100.0
		algorithm.individuals[1][algorithm.FITNESS] = 100000000001.0
		algorithm.individuals[2][algorithm.FITNESS] = 100000000002.0
		algorithm.pickIndividuals = lambda competitionSize, excludedIndices=None: [1, 2]

		selected = algorithm._findEliminateIndex(2)

		self.assertEqual(selected, 1)
		self.assertIn(selected, [1, 2])

	def test_elimination_never_selects_a_configured_elite(self):
		arguments = copy.deepcopy(self.config["algorithm"]["arguments"])
		arguments["population"]["size"] = 5
		arguments["population"]["eliteCount"] = 1
		arguments["mutation"]["competitionSize"]["eliminate"] = 2
		algorithm = GeneticAlgorithm(
			arguments["population"],
			arguments["crossover"],
			arguments["mutation"],
			copy.deepcopy(self.config["structure"]),
			{ "saveState": lambda: None },
		)
		for index, individual in enumerate(algorithm.individuals):
			individual[algorithm.FITNESS] = float(index)

		for seed in range(50):
			random.seed(seed)
			self.assertNotEqual(algorithm._findEliminateIndex(2), 4)

	def test_elite_mutation_parent_selection_uses_global_best(self):
		algorithm = self.createAlgorithm(populationSize=4)
		algorithm.mutationConfig["parentSelection"] = "elite-v1"
		for index, fitness in enumerate((-10.0, 7.0, 3.0, 6.0)):
			algorithm.individuals[index][algorithm.FITNESS] = fitness

		self.assertEqual(algorithm._findMutationParentIndex(2), 1)

	def test_checkpointed_random_state_reproduces_the_next_generation(self):
		algorithm = self.createAlgorithm(populationSize=8)
		algorithm.populationConfig["generation"] = 11
		algorithm.crossoverConfig["rate"] = 0.25
		algorithm.crossoverConfig["competitionSize"] = { "reproduce": 2, "eliminate": 2 }
		algorithm.mutationConfig["rate"] = 0.5
		algorithm.mutationConfig["competitionSize"] = { "reproduce": 2, "eliminate": 2 }
		algorithm.mutationConfig["config"] = {
			"mode": "independent-offset-v1",
			"numParameterChangedRatioRange": "0.1-0.4",
			"offsetRange": "0.01;0.2",
			"offsetExponent": 1,
			"randomizeSign": "yes",
		}
		for index, individual in enumerate(algorithm.individuals):
			individual[algorithm.FITNESS] = float(index - 4)

		checkpointCreatures = copy.deepcopy(algorithm.getCreaturesWithFitnessJson())
		checkpointState = json.loads(json.dumps(random.getstate()))
		algorithm.proceedToNextGeneration()
		expected = json.dumps(algorithm.getCreaturesWithFitnessJson(), sort_keys=True)

		arguments = copy.deepcopy(self.config["algorithm"]["arguments"])
		arguments["population"] = copy.deepcopy(algorithm.populationConfig)
		arguments["population"]["generation"] = 11
		arguments["crossover"] = copy.deepcopy(algorithm.crossoverConfig)
		arguments["mutation"] = copy.deepcopy(algorithm.mutationConfig)
		structure = copy.deepcopy(self.config["structure"])
		structure["creatures"] = checkpointCreatures
		reloaded = GeneticAlgorithm(
			arguments["population"],
			arguments["crossover"],
			arguments["mutation"],
			structure,
			{ "saveState": lambda: None },
		)
		random.setstate(randomStateFromJson(checkpointState))
		reloaded.proceedToNextGeneration()
		actual = json.dumps(reloaded.getCreaturesWithFitnessJson(), sort_keys=True)

		self.assertEqual(actual, expected)

	def test_save_and_restore_persists_rng_and_stall_counter(self):
		trainer = self.createBareTrainer()
		trainer.bestFitnessEvaluation = 17
		trainer.algorithm.populationConfig["evaluations"] = 23
		trainer.config["json"] = copy.deepcopy(self.config)
		with tempfile.TemporaryDirectory() as directory:
			trainer.config["filename"] = str(Path(directory) / "checkpoint.json")
			random.seed(712)
			expectedNextValue = random.random()
			random.seed(712)
			Trainer.saveState(trainer)

			with open(trainer.config["filename"]) as source:
				saved = json.load(source)
			trainerState = saved["experiment"]["trainerState"]
			self.assertEqual(trainerState["bestFitnessEvaluation"], 17)

			random.random()
			restoreRandomState({ "json": saved, "seed": None })
			self.assertEqual(random.random(), expectedNextValue)

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

	def test_loaded_population_expands_with_fresh_creatures(self):
		original = self.createAlgorithm()
		original.individuals[0][original.FITNESS] = 42.0
		savedCreature = original.getCreaturesWithFitnessJson()[0]

		arguments = copy.deepcopy(self.config["algorithm"]["arguments"])
		arguments["population"]["size"] = 3
		structure = copy.deepcopy(self.config["structure"])
		structure["creatures"] = [savedCreature]
		expanded = GeneticAlgorithm(
			arguments["population"],
			arguments["crossover"],
			arguments["mutation"],
			structure,
			{ "saveState": lambda: None },
		)

		self.assertEqual(len(expanded.individuals), 3)
		self.assertEqual(expanded.individuals[0][expanded.FITNESS], 42.0)
		self.assertEqual(expanded.indicesMissingFitness, [1, 2])
		self.assertNotEqual(
			expanded.individuals[0][expanded.CREATURE].id,
			expanded.individuals[1][expanded.CREATURE].id,
		)

	def test_loaded_population_cannot_be_truncated_implicitly(self):
		original = self.createAlgorithm()
		arguments = copy.deepcopy(self.config["algorithm"]["arguments"])
		arguments["population"]["size"] = 1
		structure = copy.deepcopy(self.config["structure"])
		structure["creatures"] = original.getCreaturesWithFitnessJson()

		with self.assertRaisesRegex(ValueError, "more creatures"):
			GeneticAlgorithm(
				arguments["population"],
				arguments["crossover"],
				arguments["mutation"],
				structure,
				{ "saveState": lambda: None },
			)

	def createBareTrainer(self, terminateSeconds=None):
		algorithm = self.createAlgorithm()
		trainer = Trainer.__new__(Trainer)
		trainer.algorithm = algorithm
		trainer.config = {
			"terminateEvaluations": None,
			"terminateSeconds": terminateSeconds,
			"terminateStallEvaluations": None,
		}
		trainer.stateLock = threading.RLock()
		trainer.startTime = time.monotonic()
		trainer.experimentId = "test-experiment"
		trainer.stopReason = None
		trainer.stopFinalized = False
		trainer.bestFitness = float("nan")
		trainer.bestFitnessEvaluation = 0
		trainer.statistics = {
			"accumulatedSimulatedTime": 0,
			"accumulatedFitness": {},
			"accumulatedSimulatedCreatures": {},
			"timeStamp": time.monotonic(),
		}

		class FakeCommunicator:
			isStopped = False

			def __init__(self):
				self.stopCalls = 0

			def stop(self):
				self.stopCalls += 1
				self.isStopped = True

		trainer.communicator = FakeCommunicator()
		trainer.saveState = lambda: None
		return trainer

	def test_non_finite_result_is_rejected_before_ga_mutation(self):
		for invalidField, invalidValue in (("maxDistance", math.nan), ("fitness", math.inf), ("simulatedTime", math.inf)):
			with self.subTest(invalidField=invalidField):
				trainer = self.createBareTrainer()
				creature = trainer.algorithm.getForFitness()
				evaluationId = trainer.algorithm.startEvaluation(creature.id)
				result = {
					"experimentId": trainer.experimentId,
					"id": creature.id,
					"evaluationId": evaluationId,
					"maxDistance": 1.0,
					"fitness": 1.0,
					"simulatedTime": 1.0,
				}
				result[invalidField] = invalidValue

				self.assertEqual(trainer.registerResult(result, finalizeStop=False), "FAIL")
				self.assertEqual(trainer.algorithm.populationConfig["evaluations"], 0)
				self.assertEqual(len(trainer.algorithm.indicesInFlight), 1)
				self.assertTrue(math.isnan(trainer.algorithm.getBestFitness()))

	def test_selected_fitness_is_used_when_worker_supplies_it(self):
		trainer = self.createBareTrainer()
		creature = trainer.algorithm.getForFitness()
		evaluationId = trainer.algorithm.startEvaluation(creature.id)
		result = {
			"experimentId": trainer.experimentId,
			"id": creature.id,
			"evaluationId": evaluationId,
			"maxDistance": 123.0,
			"fitness": 0.0,
			"simulatedTime": 1.0,
		}

		self.assertEqual(trainer.registerResult(result, finalizeStop=False), "OK")
		self.assertEqual(trainer.algorithm.getBestFitness(), 0.0)

	def test_work_requests_finalize_an_already_reached_stop(self):
		for request in (
			lambda trainer: trainer.getWork(),
			lambda trainer: trainer.getWorkBatch({"maxWorkUnits": 1}),
		):
			trainer = self.createBareTrainer(terminateSeconds=0)
			response = json.loads(request(trainer))
			if "status" in response:
				self.assertEqual(response["status"], "NO_WORK")
			else:
				self.assertEqual(response["workUnits"], [])
			self.assertEqual(trainer.stopReason, "wall-clock-limit")
			self.assertTrue(trainer.stopFinalized)
			self.assertEqual(trainer.communicator.stopCalls, 1)


if __name__ == "__main__":
	unittest.main()
