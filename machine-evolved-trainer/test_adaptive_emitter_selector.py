import copy
import json
import math
import random
import threading
import time
import unittest
from pathlib import Path

from AdaptiveEmitterSelector import AdaptiveEmitterSelector
from MapElites import MapElitesAlgorithm
from Trainer import Trainer, randomStateFromJson


class AdaptiveEmitterSelectorTest(unittest.TestCase):
	def createSelector(self, **overrides):
		config = {
			"enabled": True,
			"strategy": "sliding-window-ucb-v1",
			"windowSize": 32,
			"warmupSelectionsPerArm": 1,
			"minExplorationRate": 0.05,
			"ucbExploration": 0.35,
			"rewardClip": 1.0,
		}
		config.update(overrides)
		return AdaptiveEmitterSelector(config)

	def record(self, selector, emitterId, qdDelta, coverageGain=False, replacement=False, fitness=100.0):
		return selector.recordOutcome(
			198, "opaque-morphology", fitness,
			{"airborneFraction": 0.2, "rotationParticipation": 0.3},
			{"coverageGain": coverageGain, "replacement": replacement},
			qdDelta, emitterId)

	def test_equal_warmup_visits_every_arm_once(self):
		selector = self.createSelector()
		selected = [selector.selectEmitter(198, "morphology") for _ in selector.ARMS]
		self.assertEqual(selected, list(selector.ARMS))

	def test_productive_arm_receives_most_post_warmup_allocations(self):
		selector = self.createSelector(ucbExploration=0.15)
		for _ in range(300):
			emitterId = selector.selectEmitter(198, "morphology")
			self.record(selector, emitterId, 100.0 if emitterId == "large-independent" else 0.0)
		counts = {emitterId: selector.state["arms"][emitterId]["selections"] for emitterId in selector.ARMS}
		self.assertEqual(max(counts, key=counts.get), "large-independent")
		self.assertGreater(counts["large-independent"], 2 * max(counts[emitterId] for emitterId in selector.ARMS if emitterId != "large-independent"))

	def test_minimum_exploration_prevents_starvation(self):
		selector = self.createSelector(ucbExploration=0.0)
		for _ in range(400):
			emitterId = selector.selectEmitter(7, "any-id")
			self.record(selector, emitterId, 100.0 if emitterId == "small-independent" else 0.0)
		minimum = math.floor(400 * 0.05)
		for emitterId in selector.ARMS:
			self.assertGreaterEqual(selector.state["arms"][emitterId]["selections"], minimum)

	def test_zero_gain_arms_still_receive_the_exploration_floor(self):
		selector = self.createSelector(ucbExploration=0.0)
		for _ in range(200):
			emitterId = selector.selectEmitter(0, "zero-gain")
			self.record(selector, emitterId, 0.0)
		for emitterId in selector.ARMS:
			self.assertGreaterEqual(selector.state["arms"][emitterId]["selections"], 10)
		self.assertEqual({observation["reward"] for observation in selector.state["rewardWindow"]}, {0.0})

	def test_reward_is_positive_qd_gain_normalized_by_best_and_clipped(self):
		selector = self.createSelector(rewardClip=0.25)
		selector.observeFitness(20.0)
		emitterId = selector.selectEmitter(1, "m")
		self.assertEqual(self.record(selector, emitterId, 10.0, coverageGain=True, fitness=20.0), 0.25)
		emitterId = selector.selectEmitter(1, "m")
		self.assertEqual(self.record(selector, emitterId, -5.0, replacement=True, fitness=20.0), 0.0)
		self.assertEqual(selector.state["arms"]["small-independent"]["coverageGains"], 1)
		self.assertEqual(selector.state["arms"]["large-independent"]["replacements"], 1)

	def test_state_round_trips_without_changing_the_next_choice(self):
		selector = self.createSelector()
		for _ in range(19):
			emitterId = selector.selectEmitter(13, "morph")
			self.record(selector, emitterId, 3.0 if emitterId == "small-shared" else 0.0)
		serializedConfig = json.loads(json.dumps(selector.config))
		first = selector.selectEmitter(13, "morph")
		reloaded = AdaptiveEmitterSelector(serializedConfig)
		second = reloaded.selectEmitter(13, "morph")
		self.assertEqual(first, second)

	def test_opaque_controller_and_morphology_context_is_not_inspected(self):
		class Opaque:
			def __getattribute__(self, name):
				raise AssertionError("selector inspected opaque context: {}".format(name))

		selector = self.createSelector()
		emitterId = selector.selectEmitter(Opaque(), Opaque())
		reward = selector.recordOutcome(
			Opaque(), Opaque(), 1.0, {},
			{"coverageGain": False, "replacement": False}, 0.0, emitterId)
		self.assertEqual(reward, 0.0)

	def test_arbitrary_parameter_counts_and_morphology_ids_are_accepted(self):
		selector = self.createSelector()
		for parameterCount, morphologyId in ((0, ""), (1, "m/0"), (198, 1234), (1000003, ("opaque", 9))):
			self.assertIn(selector.selectEmitter(parameterCount, morphologyId), selector.ARMS)


class AdaptiveMapElitesIntegrationTest(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		path = Path(__file__).parent / "configs" / "me-v2-harmonic-qd-01.json"
		with path.open() as source:
			cls.config = json.load(source)

	def adaptiveConfig(self, populationSize=1):
		config = copy.deepcopy(self.config)
		arguments = config["algorithm"]["arguments"]
		arguments["population"]["size"] = populationSize
		arguments["mutation"]["largeConfig"] = {
			"mode": "independent-offset-v1",
			"numParameterChangedRatioRange": "0.15-0.50",
			"offsetRange": "0.02;1.0",
			"offsetSampling": "log-uniform-v1",
			"offsetExponent": 1,
			"randomizeSign": "yes",
		}
		arguments["mutation"]["adaptiveSelector"] = {
			"enabled": True,
			"strategy": "sliding-window-ucb-v1",
			"windowSize": 32,
			"warmupSelectionsPerArm": 1,
			"minExplorationRate": 0.05,
			"ucbExploration": 0.35,
			"rewardClip": 1.0,
		}
		return config

	def createAlgorithm(self, config):
		arguments = config["algorithm"]["arguments"]
		return MapElitesAlgorithm(
			arguments["population"], arguments["mutation"], config["structure"],
			arguments["archive"], {"saveState": lambda: None})

	def evaluateNext(self, algorithm, fitness, behavior=None):
		creature = algorithm.getForFitness()
		if behavior is None:
			behavior = {"airborneFraction": 0.2, "rotationParticipation": 0.3}
		algorithm.setCreatureEvaluation(creature.id, fitness, behavior, [fitness])
		return creature

	def test_config_gate_leaves_legacy_emitter_path_and_rng_sequence_intact(self):
		config = copy.deepcopy(self.config)
		arguments = config["algorithm"]["arguments"]
		arguments["population"]["size"] = 1
		arguments["mutation"]["randomInjectionRate"] = 0.1
		arguments["mutation"]["largeMutationRate"] = 0.25
		arguments["mutation"]["largeConfig"] = {
			"mode": "independent-offset-v1",
			"numParameterChangedRatioRange": "0.15-0.50",
			"offsetRange": "0.02;1.0",
			"offsetSampling": "log-uniform-v1",
			"offsetExponent": 1,
			"randomizeSign": "yes",
		}
		random.seed(913)
		algorithm = self.createAlgorithm(config)
		self.assertIsNone(algorithm.adaptiveSelector)
		creature = next(iter(algorithm.pending.values()))
		algorithm.pending.pop(creature.id)
		algorithm._insertArchive(creature, 10.0, {"airborneFraction": 0.2, "rotationParticipation": 0.3}, [10.0])
		randomState = random.getstate()
		algorithm._queueChild()
		actual = next(iter(algorithm.pending.values()))
		actualState = random.getstate()

		random.setstate(randomState)
		self.assertGreaterEqual(random.random(), 0.1)
		parent = random.choice(list(algorithm.archive.values()))["creature"]
		expected = copy.deepcopy(parent)
		large = random.random() < 0.25
		expected.mutate(arguments["mutation"]["largeConfig"] if large else arguments["mutation"]["config"])
		self.assertEqual(actual.motorController.layers, expected.motorController.layers)
		self.assertEqual(actual.generatorType, "qd-large-mutate" if large else "qd-mutate")
		self.assertEqual(actualState, random.getstate())

	def test_same_seed_creates_identical_adaptive_population_and_ids(self):
		firstConfig = self.adaptiveConfig(populationSize=4)
		secondConfig = self.adaptiveConfig(populationSize=4)
		random.seed(222)
		first = self.createAlgorithm(firstConfig)
		random.seed(222)
		second = self.createAlgorithm(secondConfig)
		self.assertEqual(
			json.dumps(first.getCreaturesWithFitnessJson(), sort_keys=True),
			json.dumps(second.getCreaturesWithFitnessJson(), sort_keys=True))

	def test_pending_child_serializes_and_restores_emitter_id(self):
		config = self.adaptiveConfig()
		random.seed(88)
		algorithm = self.createAlgorithm(config)
		self.evaluateNext(algorithm, 10.0)
		saved = algorithm.getCreaturesWithFitnessJson()
		pending = next(item for item in saved if item["fitness"] is None)
		self.assertEqual(pending["data"]["metadata"]["emitterId"], "small-independent")

		reloadConfig = self.adaptiveConfig()
		reloadConfig["algorithm"]["arguments"]["mutation"]["adaptiveSelector"] = copy.deepcopy(
			config["algorithm"]["arguments"]["mutation"]["adaptiveSelector"])
		reloadConfig["structure"]["creatures"] = saved
		reloaded = self.createAlgorithm(reloadConfig)
		restored = next(creature for creature in reloaded.pending.values() if creature.id == pending["data"]["metadata"]["creatureId"])
		self.assertEqual(restored.emitterId, "small-independent")

	def test_checkpoint_resume_matches_uninterrupted_next_emission(self):
		config = self.adaptiveConfig()
		random.seed(144)
		uninterrupted = self.createAlgorithm(config)
		self.evaluateNext(uninterrupted, 10.0)
		checkpointCreatures = copy.deepcopy(uninterrupted.getCreaturesWithFitnessJson())
		checkpointMutation = copy.deepcopy(config["algorithm"]["arguments"]["mutation"])
		checkpointRandom = json.loads(json.dumps(random.getstate()))

		self.evaluateNext(uninterrupted, 12.0, {"airborneFraction": 0.7, "rotationParticipation": 0.2})
		expectedCreatures = json.dumps(uninterrupted.getCreaturesWithFitnessJson(), sort_keys=True)
		expectedState = copy.deepcopy(uninterrupted.adaptiveSelector.getState())

		reloadConfig = self.adaptiveConfig()
		reloadConfig["algorithm"]["arguments"]["mutation"] = checkpointMutation
		reloadConfig["structure"]["creatures"] = checkpointCreatures
		random.setstate(randomStateFromJson(checkpointRandom))
		reloaded = self.createAlgorithm(reloadConfig)
		self.evaluateNext(reloaded, 12.0, {"airborneFraction": 0.7, "rotationParticipation": 0.2})
		self.assertEqual(json.dumps(reloaded.getCreaturesWithFitnessJson(), sort_keys=True), expectedCreatures)
		self.assertEqual(reloaded.adaptiveSelector.getState(), expectedState)

	def test_four_warmup_emitters_use_existing_generation_operations(self):
		config = self.adaptiveConfig()
		random.seed(812)
		algorithm = self.createAlgorithm(config)
		seed = next(iter(algorithm.pending.values()))
		algorithm.pending.pop(seed.id)
		algorithm._insertArchive(seed, 10.0, {"airborneFraction": 0.2, "rotationParticipation": 0.3}, [10.0])
		for _ in AdaptiveEmitterSelector.ARMS:
			algorithm._queueChild(seed.motorController.getNumParameters(), seed.morphologyId)
		self.assertEqual(
			{creature.emitterId for creature in algorithm.pending.values()},
			set(AdaptiveEmitterSelector.ARMS))
		normal = config["algorithm"]["arguments"]["mutation"]["config"]
		broad = config["algorithm"]["arguments"]["mutation"]["largeConfig"]
		smallIndependent = algorithm._mutationConfigForEmitter("small-independent")
		largeIndependent = algorithm._mutationConfigForEmitter("large-independent")
		smallShared = algorithm._mutationConfigForEmitter("small-shared")
		self.assertEqual(smallIndependent["offsetRange"], normal["offsetRange"])
		self.assertEqual(smallIndependent["numParameterChangedRatioRange"], normal["numParameterChangedRatioRange"])
		self.assertEqual(smallIndependent["mode"], "independent-offset-v1")
		self.assertEqual(largeIndependent["offsetRange"], broad["offsetRange"])
		self.assertEqual(largeIndependent["numParameterChangedRatioRange"], broad["numParameterChangedRatioRange"])
		self.assertEqual(largeIndependent["mode"], "independent-offset-v1")
		self.assertEqual(smallShared["offsetRange"], normal["offsetRange"])
		self.assertEqual(smallShared["numParameterChangedRatioRange"], normal["numParameterChangedRatioRange"])
		self.assertEqual(smallShared["mode"], "shared-offset-v1")

	def test_qd_score_delta_uses_zero_for_an_empty_cell_and_reports_outcomes(self):
		config = self.adaptiveConfig()
		random.seed(22)
		algorithm = self.createAlgorithm(config)
		creature = algorithm.getForFitness()
		creature.morphologyId = "fixed-morphology"
		algorithm.setCreatureEvaluation(creature.id, 10.0, {"airborneFraction": 0.2, "rotationParticipation": 0.3}, [10.0])
		first = algorithm.getLastInsertionResult()
		self.assertEqual((first["outcome"], first["oldCellFitness"], first["qdDelta"], first["qdScore"]),
			("new-global-best", 0.0, 10.0, 10.0))

		creature = algorithm.getForFitness()
		creature.morphologyId = "fixed-morphology"
		algorithm.setCreatureEvaluation(creature.id, 4.0, {"airborneFraction": 0.8, "rotationParticipation": 0.8}, [4.0])
		newCell = algorithm.getLastInsertionResult()
		self.assertEqual((newCell["outcome"], newCell["qdDelta"], newCell["qdScore"]), ("new-cell", 4.0, 14.0))

		creature = algorithm.getForFitness()
		creature.morphologyId = "fixed-morphology"
		algorithm.setCreatureEvaluation(creature.id, 6.0, {"airborneFraction": 0.8, "rotationParticipation": 0.8}, [6.0])
		replacement = algorithm.getLastInsertionResult()
		self.assertEqual((replacement["outcome"], replacement["qdDelta"], replacement["qdScore"]), ("replacement", 2.0, 16.0))

		creature = algorithm.getForFitness()
		creature.morphologyId = "fixed-morphology"
		algorithm.setCreatureEvaluation(creature.id, 5.0, {"airborneFraction": 0.8, "rotationParticipation": 0.8}, [5.0])
		rejected = algorithm.getLastInsertionResult()
		self.assertEqual((rejected["outcome"], rejected["qdDelta"], rejected["qdScore"]), ("rejected", 0.0, 16.0))

		creature = algorithm.getForFitness()
		creature.morphologyId = "fixed-morphology"
		algorithm.setCreatureEvaluation(creature.id, 11.0, {"airborneFraction": 0.8, "rotationParticipation": 0.8}, [11.0])
		best = algorithm.getLastInsertionResult()
		self.assertEqual((best["outcome"], best["qdDelta"], best["qdScore"]), ("new-global-best", 5.0, 21.0))

	def test_trainer_history_reports_qd_score_delta_outcome_and_emitter(self):
		config = self.adaptiveConfig()
		config.setdefault("experiment", {})["evaluationDomains"] = [{"id": "nominal"}]
		random.seed(91)
		algorithm = self.createAlgorithm(config)
		trainer = Trainer.__new__(Trainer)
		trainer.algorithm = algorithm
		trainer.config = {
			"json": config,
			"terminateEvaluations": None,
			"terminateSeconds": None,
			"terminateStallEvaluations": None,
		}
		trainer.stateLock = threading.RLock()
		trainer.startTime = time.monotonic()
		trainer.experimentId = "adaptive-test"
		trainer.stopReason = None
		trainer.stopFinalized = False
		trainer.bestFitness = float("nan")
		trainer.bestFitnessEvaluation = 0
		trainer.domainProgress = {}
		trainer.domainQueue = []
		trainer.evaluationContexts = {}
		trainer.evaluationHistory = []
		trainer.evaluationSimulations = 0
		trainer.statistics = {
			"accumulatedSimulatedTime": 0,
			"accumulatedFitness": {},
			"accumulatedSimulatedCreatures": {},
			"timeStamp": time.monotonic(),
		}
		trainer.finalizeStop = lambda: None

		creature = algorithm.getForFitness()
		evaluationId = algorithm.startEvaluation(creature.id)
		trainer.evaluationContexts[evaluationId] = {"creatureId": creature.id, "domainId": "nominal"}
		result = {
			"experimentId": trainer.experimentId,
			"evaluationId": evaluationId,
			"id": creature.id,
			"maxDistance": 8.0,
			"fitness": 8.0,
			"simulatedTime": 1.0,
			"motion": {"nearGroundTimeFraction": 0.8, "rollingExplainedFraction": 0.3},
		}
		self.assertEqual(trainer.registerResult(result, finalizeStop=False), "OK")
		self.assertEqual(
			{key: trainer.evaluationHistory[0][key] for key in ("emitterId", "insertionOutcome", "qdDelta", "qdScore")},
			{"emitterId": None, "insertionOutcome": "new-global-best", "qdDelta": 8.0, "qdScore": 8.0})
		self.assertEqual(algorithm.getStatusNumeric()["qdScore"], 8.0)


if __name__ == "__main__":
	unittest.main()
