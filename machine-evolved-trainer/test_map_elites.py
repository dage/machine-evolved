import copy
import json
import random
import unittest
from unittest import mock
from pathlib import Path

from MapElites import MapElitesAlgorithm


class MapElitesTest(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		path = Path(__file__).parent / "configs" / "me-v2-harmonic-qd-01.json"
		with path.open() as source:
			cls.config = json.load(source)

	def createAlgorithm(self):
		config = copy.deepcopy(self.config)
		arguments = config["algorithm"]["arguments"]
		arguments["population"]["size"] = 3
		random.seed(11)
		return MapElitesAlgorithm(
			arguments["population"], arguments["mutation"], config["structure"],
			arguments["archive"], {"saveState": lambda: None})

	def test_templates_create_198_parameter_harmonic_controllers(self):
		algorithm = self.createAlgorithm()
		self.assertEqual({creature.morphologyId for creature in algorithm.pending.values()}, {
			"m0-champion-proportions", "m1-balanced", "m2-wheel-biased"})
		for creature in algorithm.pending.values():
			self.assertEqual(creature.structure.getNumInputs(), 32)
			self.assertEqual(creature.structure.getNumOutputs(), 6)
			self.assertEqual(creature.motorController.getNumParameters(), 198)

	def test_cell_replacement_is_quality_monotonic(self):
		algorithm = self.createAlgorithm()
		creature = algorithm.getForFitness()
		firstId = creature.id
		algorithm.setCreatureEvaluation(firstId, 10, {"airborneFraction": .2, "rotationParticipation": .3}, [10, 10, 10])
		cell = next(iter(algorithm.archive))
		incumbent = algorithm.archive[cell]["creature"]
		challenger = copy.deepcopy(incumbent)
		challenger.id = "challenger"
		algorithm.pending[challenger.id] = challenger
		algorithm.inFlight[challenger.id] = 0
		algorithm.setCreatureEvaluation(challenger.id, 9, {"airborneFraction": .2, "rotationParticipation": .3}, [9, 9, 9])
		self.assertEqual(algorithm.archive[cell]["fitness"], 10)

	def test_resumed_partial_domain_candidate_is_not_dispatched_twice(self):
		algorithm = self.createAlgorithm()
		reservedId = next(iter(algorithm.pending))
		algorithm.reserveEvaluation(reservedId)
		self.assertNotEqual(algorithm.getForFitness().id, reservedId)

	def test_random_injection_emitter_adds_a_fresh_template(self):
		algorithm = self.createAlgorithm()
		algorithm.mutationConfig["randomInjectionRate"] = 1.0
		before = set(algorithm.pending)
		with mock.patch("MapElites.random.random", return_value=0.0):
			algorithm._queueChild()
		created = [algorithm.pending[key] for key in set(algorithm.pending) - before]
		self.assertEqual(len(created), 1)
		self.assertTrue(created[0].generatorType.startswith(("template-", "curl-")))


if __name__ == "__main__":
	unittest.main()
