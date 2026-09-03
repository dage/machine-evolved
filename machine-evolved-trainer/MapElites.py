import copy
import math
import random
import time
import uuid

from AdaptiveEmitterSelector import AdaptiveEmitterSelector
from Creature import Creature


class MapElitesAlgorithm:
	"""Small steady-state MAP-Elites implementation for fixed morphology templates."""

	def __init__(self, populationConfig, mutationConfig, structureConfig, archiveConfig, callbacks):
		self.populationConfig = populationConfig
		self.mutationConfig = mutationConfig
		self.structureConfig = structureConfig
		self.archiveConfig = archiveConfig
		self.callbacks = callbacks
		self.saveStateTimestamp = time.monotonic()
		self.pending = {}
		self.inFlight = {}
		self.activeEvaluationIds = {}
		self.archive = {}
		self.lastInsertionResult = None
		selectorConfig = mutationConfig.get("adaptiveSelector")
		self.adaptiveSelector = AdaptiveEmitterSelector(selectorConfig) if selectorConfig and selectorConfig.get("enabled") is True else None
		if self.adaptiveSelector is not None and mutationConfig.get("largeConfig") is None:
			raise ValueError("adaptiveSelector requires mutation.largeConfig")
		self.templates = structureConfig.get("templates", [])
		if not self.templates:
			raise ValueError("MapElites requires structure.templates")
		self.bins = int(archiveConfig.get("binsPerAxis", 8))
		if self.bins < 2:
			raise ValueError("MapElites binsPerAxis must be at least 2")

		for saved in structureConfig.get("creatures", []):
			creature = Creature(saved["data"], structureConfig["generator"])
			fitness = saved.get("fitness")
			evaluation = saved.get("evaluation", {})
			if fitness is None or "behavior" not in evaluation:
				self.pending[creature.id] = creature
			else:
				self._insertArchive(creature, float(fitness), evaluation["behavior"], evaluation.get("domainScores", []))
		self.lastInsertionResult = None
		if self.adaptiveSelector is not None:
			self.adaptiveSelector.observeFitness(self.getBestFitness())

		initialSize = int(populationConfig.get("size", 192))
		while len(self.pending) + len(self.archive) < initialSize:
			self._queueRandomTemplate()

	def _template(self, index):
		entry = self.templates[index % len(self.templates)]
		return entry["id"], entry["structure"]

	def _newAdaptiveId(self):
		return str(uuid.UUID(int=random.getrandbits(128), version=4))

	def _queueRandomTemplate(self, emitterId=None):
		morphologyId, structure = self._template(len(self.pending) + len(self.archive))
		creature = Creature(None, self.structureConfig["generator"], structure, morphologyId)
		self._initializeController(creature)
		if self.adaptiveSelector is not None:
			creature.id = self._newAdaptiveId()
		if emitterId is not None:
			creature.emitterId = emitterId
		self.pending[creature.id] = creature

	def _initializeController(self, creature):
		initialization = self.structureConfig["generator"]["motorController"].get("initialization", {})
		if initialization.get("mode") != "mixed-curl-v1" or not creature.motorController.layers:
			return
		roll = random.random()
		if roll >= float(initialization.get("curlFraction", 0.5)):
			return
		sign = -1.0 if random.random() < 0.5 else 1.0
		target = float(initialization.get("curlTargetRadians", 2.05))
		angleRange = float(creature.motorController.servo.get("targetAngleRangeRadians", math.pi * 0.9))
		bias = math.atanh(max(-0.999, min(0.999, target / angleRange))) * sign
		creature.motorController.layers[-1]["biases"] = [bias] * len(creature.motorController.layers[-1]["biases"])
		creature.generatorType = "curl-left" if sign < 0 else "curl-right"

	def _cell(self, behavior, morphologyId):
		airborne = max(0.0, min(1.0, float(behavior["airborneFraction"])))
		rotation = max(0.0, min(1.0, float(behavior["rotationParticipation"])))
		return "{}:{}:{}".format(
			morphologyId or "unknown",
			min(self.bins - 1, int(airborne * self.bins)),
			min(self.bins - 1, int(rotation * self.bins)))

	def _insertArchive(self, creature, fitness, behavior, domainScores):
		cell = self._cell(behavior, creature.morphologyId)
		current = self.archive.get(cell)
		previousBest = self.getBestFitness()
		inserted = current is None or fitness > current["fitness"]
		oldCellFitness = float(current["fitness"]) if current is not None else 0.0
		coverageGain = inserted and current is None
		replacement = inserted and current is not None
		if inserted:
			self.archive[cell] = {
				"fitness": fitness,
				"creature": copy.deepcopy(creature),
				"behavior": copy.deepcopy(behavior),
				"domainScores": list(domainScores),
			}
		qdDelta = float(fitness) - oldCellFitness if inserted else 0.0
		newGlobalBest = inserted and (math.isnan(previousBest) or fitness > previousBest)
		if not inserted:
			outcome = "rejected"
		elif newGlobalBest:
			outcome = "new-global-best"
		elif coverageGain:
			outcome = "new-cell"
		else:
			outcome = "replacement"
		self.lastInsertionResult = {
			"inserted": inserted,
			"outcome": outcome,
			"qdDelta": qdDelta,
			"qdScore": self.getQdScore(),
			"coverageGain": coverageGain,
			"replacement": replacement,
			"newGlobalBest": newGlobalBest,
			"oldCellFitness": oldCellFitness,
			"cell": cell,
		}
		return inserted

	def _queueLegacyChild(self):
		randomInjectionRate = float(self.mutationConfig.get("randomInjectionRate", 0.0))
		if not self.archive or random.random() < randomInjectionRate:
			self._queueRandomTemplate()
			return
		parent = random.choice(list(self.archive.values()))["creature"]
		child = copy.deepcopy(parent)
		largeMutationRate = float(self.mutationConfig.get("largeMutationRate", 0.0))
		largeMutation = largeMutationRate > 0 and random.random() < largeMutationRate
		mutation = self.mutationConfig.get("largeConfig") if largeMutation else self.mutationConfig["config"]
		if mutation is None:
			raise ValueError("largeMutationRate requires mutation.largeConfig")
		child.mutate(mutation)
		child.generatorType = "qd-large-mutate" if largeMutation else "qd-mutate"
		self.pending[child.id] = child

	def _queueAdaptiveChild(self, controllerSignatureOrLength=None, morphologyId=None):
		emitterId = self.adaptiveSelector.selectEmitter(controllerSignatureOrLength, morphologyId)
		if emitterId == "fresh-template":
			self._queueRandomTemplate(emitterId)
			return
		parent = random.choice(list(self.archive.values()))["creature"]
		child = copy.deepcopy(parent)
		mutation = self._mutationConfigForEmitter(emitterId)
		child.mutate(mutation)
		child.id = self._newAdaptiveId()
		child.emitterId = emitterId
		child.generatorType = "qd-{}".format(emitterId)
		self.pending[child.id] = child

	def _mutationConfigForEmitter(self, emitterId):
		if emitterId == "large-independent":
			mutation = copy.deepcopy(self.mutationConfig["largeConfig"])
			mutation["mode"] = "independent-offset-v1"
		elif emitterId == "small-shared":
			mutation = copy.deepcopy(self.mutationConfig["config"])
			mutation["mode"] = "shared-offset-v1"
		elif emitterId == "small-independent":
			mutation = copy.deepcopy(self.mutationConfig["config"])
			mutation["mode"] = "independent-offset-v1"
		else:
			raise ValueError("Emitter does not use mutation bounds: {}".format(emitterId))
		return mutation

	def _queueChild(self, controllerSignatureOrLength=None, morphologyId=None):
		if self.adaptiveSelector is None:
			self._queueLegacyChild()
		else:
			self._queueAdaptiveChild(controllerSignatureOrLength, morphologyId)

	def maintainPopulation(self):
		timeout = float(self.populationConfig.get("evaluationTimeoutSeconds", 300))
		for creatureId, started in list(self.inFlight.items()):
			if time.monotonic() - started > timeout:
				creature = self.pending.get(creatureId)
				if creature is not None and self.adaptiveSelector is not None:
					self.adaptiveSelector.recordFailure(creature.emitterId)
				self.inFlight.pop(creatureId, None)
				self.activeEvaluationIds.pop(creatureId, None)
		if time.monotonic() - self.saveStateTimestamp > float(self.populationConfig.get("checkpointIntervalSeconds", 60)):
			self.saveStateTimestamp = time.monotonic()
			self.callbacks["saveState"]()

	def getForFitness(self):
		for creatureId, creature in self.pending.items():
			if creatureId not in self.inFlight:
				self.inFlight[creatureId] = time.monotonic()
				return creature
		return None

	def reserveEvaluation(self, creatureId):
		if creatureId in self.pending:
			self.inFlight[creatureId] = time.monotonic()

	def startEvaluation(self, creatureId):
		evaluationId = str(uuid.uuid4())
		self.activeEvaluationIds[creatureId] = evaluationId
		return evaluationId

	def isCurrentEvaluation(self, creatureId, evaluationId):
		return self.activeEvaluationIds.get(creatureId) == evaluationId

	def continueEvaluation(self, creatureId):
		self.activeEvaluationIds.pop(creatureId, None)

	def recordEmitterAttempt(self, emitterId):
		if self.adaptiveSelector is not None:
			return self.adaptiveSelector.recordAttempt(emitterId)
		return False

	def recordEmitterFailure(self, emitterId, invalidOutcome=False):
		if self.adaptiveSelector is not None:
			return self.adaptiveSelector.recordFailure(emitterId, invalidOutcome)
		return False

	def setCreatureEvaluation(self, creatureId, fitness, behavior, domainScores):
		creature = self.pending.pop(creatureId, None)
		if creature is None:
			return False
		self.inFlight.pop(creatureId, None)
		self.activeEvaluationIds.pop(creatureId, None)
		inserted = self._insertArchive(creature, fitness, behavior, domainScores)
		insertionResult = self.lastInsertionResult
		if self.adaptiveSelector is not None:
			self.adaptiveSelector.recordOutcome(
				creature.motorController.getNumParameters(), creature.morphologyId, fitness,
				behavior, insertionResult, insertionResult["qdDelta"], creature.emitterId)
		self._queueChild(creature.motorController.getNumParameters(), creature.morphologyId)
		self.populationConfig["generation"] = int(self.populationConfig.get("evaluations", 0)) // max(1, int(self.populationConfig.get("size", 1)))
		return inserted

	def setCreatureFitness(self, creatureId, fitness):
		return self.setCreatureEvaluation(creatureId, fitness, {"airborneFraction": 0, "rotationParticipation": 0}, [fitness])

	def getCreature(self, creatureId):
		return self.pending.get(creatureId)

	def getBestCreature(self):
		if self.archive:
			return max(self.archive.values(), key=lambda item: item["fitness"])["creature"]
		return next(iter(self.pending.values()))

	def getBestFitness(self):
		return max((item["fitness"] for item in self.archive.values()), default=float("nan"))

	def getAverageFitness(self):
		return sum(item["fitness"] for item in self.archive.values()) / len(self.archive) if self.archive else 0.0

	def getQdScore(self):
		return sum(item["fitness"] for item in self.archive.values())

	def getLastInsertionResult(self):
		return copy.deepcopy(self.lastInsertionResult)

	def getPopulationSize(self):
		return len(self.archive) + len(self.pending)

	def getNumWithFitness(self):
		return len(self.archive)

	def getCreaturesWithFitnessJson(self):
		def savedData(creature):
			data = creature.getJson()
			data.setdefault("metadata", {})["creatureId"] = creature.id
			return data

		result = []
		for item in self.archive.values():
			result.append({
				"fitness": item["fitness"],
				"data": savedData(item["creature"]),
				"evaluation": {"behavior": item["behavior"], "domainScores": item["domainScores"]},
			})
		for creature in self.pending.values():
			result.append({"fitness": None, "data": savedData(creature)})
		return result

	def getStatusNumeric(self):
		return {
			"numInFlight": len(self.inFlight),
			"numWithFitness": len(self.archive),
			"populationSize": self.getPopulationSize(),
			"qdScore": self.getQdScore(),
		}

	def getStatus(self):
		return "MAP-Elites({}x{}, morphologies={}): occupied={}, pending={}, in flight={}, QD score={:.3f}".format(
			self.bins, self.bins, len(self.templates), len(self.archive), len(self.pending), len(self.inFlight), self.getQdScore())
