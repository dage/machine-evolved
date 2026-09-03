from Communicator import Communicator
from Creature import Creature
from MapElites import MapElitesAlgorithm
import json
import uuid
import time
import copy
import random
import math
import gc
import os
import argparse
from pprint import pprint
import sys
import signal
import threading

def wallClockLimitReached(startTime, limitSeconds, currentTime=None):
	if limitSeconds is None:
		return False
	if currentTime is None:
		currentTime = time.monotonic()
	return currentTime - startTime >= limitSeconds

def randomStateFromJson(value):
	"""Convert JSON arrays back to the tuples required by random.setstate()."""
	if isinstance(value, list):
		return tuple(randomStateFromJson(item) for item in value)
	return value

def restoreRandomState(config):
	trainerState = config["json"].get("experiment", {}).get("trainerState", {})
	serializedState = trainerState.get("pythonRandomState")
	if serializedState is not None:
		random.setstate(randomStateFromJson(serializedState))
		return "checkpoint"
	if config["seed"] is not None:
		random.seed(config["seed"])
		return "seed"
	return "system"

class GeneticAlgorithm():
	FITNESS = 0		# Key into individuals item tuple
	CREATURE = 1	# Key into individuals item tuple
	IN_FLIGHT = 2	# Key into individuals item tuple

	def __init__(self, populationConfig, crossoverConfig, mutationConfig, structureConfig, callbacks):
		self.individuals = []
		self.indicesMissingFitness = []
		self.indicesInFlight = []
		self.creatureIndexLookup = {}	# Maps creature.id to its index in individuals.
		self.activeEvaluationIds = {}
		self.populationConfig = populationConfig
		self.crossoverConfig = crossoverConfig
		self.mutationConfig = mutationConfig
		self.structureConfig = structureConfig
		self.saveStateTimestamp = time.monotonic()
		self.callbacks = callbacks
		self.validateConfiguration()

		if not structureConfig["creatures"]:
			# Create new creatures
			self.indicesMissingFitness = list(range(0, int(self.populationConfig["size"])))
			for i in self.indicesMissingFitness:
				templates = structureConfig.get("templates", [])
				if templates:
					template = templates[i % len(templates)]
					creature = Creature(None, structureConfig["generator"], template["structure"], template["id"])
				else:
					creature = Creature(None, structureConfig["generator"])
				self.individuals.append([float("nan"), creature, float("nan")])
				self.creatureIndexLookup[creature.id] = i
		else:
			# Deserialize existing creatures
			creatures = structureConfig["creatures"]
			populationSize = int(self.populationConfig["size"])
			if len(creatures) > populationSize:
				raise ValueError(
					"Saved population has more creatures than the configured population size."
				)
			for i in range(0, len(creatures)):
				creatureJson = creatures[i]["data"]
				rawFitness = creatures[i].get("fitness")
				fitness = float("nan") if rawFitness is None else float(rawFitness)
				creature = Creature(creatureJson, structureConfig["generator"])
				self.individuals.append([fitness, creature, float("nan")])
				self.creatureIndexLookup[creature.id] = i

				if math.isnan(fitness):
					self.indicesMissingFitness.append(i)

			# A larger configured population is an explicit request for fresh
			# diversity around a saved checkpoint. Preserve every loaded creature,
			# then fill the new slots from the same structure generator rather than
			# silently training at the checkpoint's old population size.
			for i in range(len(creatures), populationSize):
				creature = Creature(None, structureConfig["generator"])
				self.individuals.append([float("nan"), creature, float("nan")])
				self.creatureIndexLookup[creature.id] = i
				self.indicesMissingFitness.append(i)

	def validateConfiguration(self):
		populationSize = int(self.populationConfig["size"])
		eliteCount = int(self.populationConfig.get("eliteCount", 0))
		competitionSizes = [
			int(self.crossoverConfig["competitionSize"]["reproduce"]),
			int(self.crossoverConfig["competitionSize"]["eliminate"]),
			int(self.mutationConfig["competitionSize"]["reproduce"]),
			int(self.mutationConfig["competitionSize"]["eliminate"]),
		]
		if populationSize < 1 or eliteCount < 0 or eliteCount >= populationSize:
			raise ValueError("Population size must be positive and eliteCount must leave at least one replaceable individual.")
		if min(competitionSizes) < 1 or max(competitionSizes) > populationSize:
			raise ValueError("Population and tournament sizes must be positive, and tournaments cannot exceed the population.")
		numChildren = int(float(self.crossoverConfig["rate"]) * populationSize)
		numChildren += int(float(self.mutationConfig["rate"]) * populationSize)
		largestReproductionTournament = max(
			int(self.crossoverConfig["competitionSize"]["reproduce"]),
			int(self.mutationConfig["competitionSize"]["reproduce"]),
		)
		largestEliminationTournament = max(
			int(self.crossoverConfig["competitionSize"]["eliminate"]),
			int(self.mutationConfig["competitionSize"]["eliminate"]),
		)
		maxChildren = min(
			populationSize - largestReproductionTournament + 1,
			populationSize - eliteCount - largestEliminationTournament + 1,
		)
		if numChildren > maxChildren:
			raise ValueError(
				"Crossover and mutation replace too much of the evaluated population for the configured tournament sizes."
			)

	def getAverageFitness(self):
		count = 0
		fitnessSum = 0
		for i in self.individuals:
			if not math.isnan(i[self.FITNESS]):
				count += 1
				fitnessSum += i[self.FITNESS]		
		return fitnessSum/count if count > 0 else 0

	# Returns a dictionary with { "fitness": value, "data": creatureObjectStructure }
	def getCreaturesWithFitnessJson(self):
		output = []
		for i in self.individuals:
			fitness = i[self.FITNESS]
			output.append({ "fitness": None if math.isnan(fitness) else fitness, "data": i[self.CREATURE].getJson() })
		return output
	
	def getIndexBestCreature(self):
		bestIndex = 0
		bestFitness = self.individuals[bestIndex][self.FITNESS]

		for j in range(1, len(self.individuals)):
			i = self.individuals[j]
			if math.isnan(bestFitness) or (not math.isnan(i[self.FITNESS]) and i[self.FITNESS] > bestFitness):
				bestFitness = i[self.FITNESS]
				bestIndex = j

		return bestIndex

	def getCreature(self, creatureId):
		if not creatureId in self.creatureIndexLookup:
			return None

		creatureIndex = self.creatureIndexLookup[creatureId]
		return self.individuals[creatureIndex][self.CREATURE]

	def getBestFitness(self):
		return self.individuals[self.getIndexBestCreature()][self.FITNESS]

	def getBestCreature(self):
		#print("picked fitness = " + str(self.individuals[self.getIndexBestCreature()][self.FITNESS]))
		#print("picked in flight = " + str(self.individuals[self.getIndexBestCreature()][self.IN_FLIGHT]))
		return self.individuals[self.getIndexBestCreature()][self.CREATURE]

	def getPopulationSize(self):
		return len(self.individuals)

	def getNumWithFitness(self):
		return len(self.individuals) - len(self.indicesMissingFitness)

	def maintainPopulation(self):
		# Re-live individuals lost in flight
		indicesPutBackFromFlight = []
		evaluationTimeoutSeconds = float(self.populationConfig.get("evaluationTimeoutSeconds", 300))

		#print("maintain: numMissing=" + str(numMissingFitness))

		for i in self.indicesInFlight:
			timeInFlight = time.monotonic() - self.individuals[i][self.IN_FLIGHT]
		#	print("maintain: timeInFlight=" + str(timeInFlight))
			if timeInFlight > evaluationTimeoutSeconds:
				indicesPutBackFromFlight.append(i)

		for i in indicesPutBackFromFlight:
			self.individuals[i][self.IN_FLIGHT] = float("nan")	# Give up, assume will never come back
			if self.indicesInFlight.count(i) > 0:
				self.indicesInFlight.remove(i)
	
		if len(self.indicesMissingFitness) == 0:
			self.proceedToNextGeneration()

		if time.monotonic() - self.saveStateTimestamp > float(self.populationConfig.get("checkpointIntervalSeconds", 60 * 60)):
			self.saveStateTimestamp = time.monotonic()
			self.callbacks["saveState"]()

	# Returns a list of indices into individuals
	def getEliteIndices(self):
		eliteCount = int(self.populationConfig.get("eliteCount", 0))
		if eliteCount == 0:
			return set()
		eligible = [
			index for index, individual in enumerate(self.individuals)
			if not math.isnan(individual[self.FITNESS])
		]
		return set(sorted(
			eligible,
			key=lambda index: self.individuals[index][self.FITNESS],
			reverse=True,
		)[:eliteCount])

	def pickIndividuals(self, numToPick, excludedIndices=None):
		excludedIndices = excludedIndices or set()
		eligible = [
			index for index, individual in enumerate(self.individuals)
			if not math.isnan(individual[self.FITNESS]) and index not in excludedIndices
		]
		if numToPick > len(eligible):
			raise RuntimeError("Not enough evaluated individuals for tournament selection.")
		return random.sample(eligible, numToPick)

	def _findReproduceIndex(self, competitionSize):
		reproduce = self.pickIndividuals(competitionSize)
		return max(reproduce, key=lambda index: self.individuals[index][self.FITNESS])

	def _findMutationParentIndex(self, competitionSize):
		parentSelection = self.mutationConfig.get("parentSelection", "tournament-v1")
		if parentSelection == "tournament-v1":
			return self._findReproduceIndex(competitionSize)
		if parentSelection == "elite-v1":
			eligible = [
				index for index, individual in enumerate(self.individuals)
				if not math.isnan(individual[self.FITNESS])
			]
			return max(eligible, key=lambda index: self.individuals[index][self.FITNESS])
		raise ValueError("Unknown mutation parent selection: {}".format(parentSelection))

	def _findEliminateIndex(self, competitionSize):
		eliminate = self.pickIndividuals(competitionSize, self.getEliteIndices())
		return min(eliminate, key=lambda index: self.individuals[index][self.FITNESS])

	def proceedToNextGeneration(self):

		def replaceIndividual(atIndex, newCreature):
			del self.creatureIndexLookup[self.individuals[atIndex][self.CREATURE].id]
			self.individuals[atIndex]= [float("nan"), newCreature, float("nan")]
			self.creatureIndexLookup[newCreature.id] = atIndex
			self.indicesMissingFitness.append(atIndex)


		# Create children with crossover
		numCrossoverChildren = 0
		crossoverRatio = float(self.crossoverConfig["rate"])
		reproduceCrossoverSize = int(self.crossoverConfig["competitionSize"]["reproduce"])
		eliminateCrossoverSize = int(self.crossoverConfig["competitionSize"]["eliminate"])
		
		while crossoverRatio > 0.00001 and numCrossoverChildren < int(crossoverRatio*len(self.individuals)):
			numCrossoverChildren = numCrossoverChildren + 1

			i1 = self._findReproduceIndex(reproduceCrossoverSize)
			i2 = self._findReproduceIndex(reproduceCrossoverSize)
			reproduceCreature1 = self.individuals[i1][self.CREATURE]
			reproduceCreature2 = self.individuals[i2][self.CREATURE]
			child = copy.deepcopy(reproduceCreature1)
			child.crossover(reproduceCreature2, self.crossoverConfig)

			#child.nextFitnessLog = "Crossover between " + str(self.individuals[i1][self.FITNESS]) + " and " + str(self.individuals[i2][self.FITNESS]) + "."
			
			replaceIndividual(self._findEliminateIndex(eliminateCrossoverSize), child)


		# Create children with mutation
		numMutateChildren = 0
		self.mutationConfig
		mutationRatio = float(self.mutationConfig["rate"])
		reproduceMutationSize = int(self.mutationConfig["competitionSize"]["reproduce"])
		eliminateMutationSize = int(self.mutationConfig["competitionSize"]["eliminate"])

		while mutationRatio > 0.00001 and numMutateChildren < int(mutationRatio*len(self.individuals)):
			numMutateChildren = numMutateChildren + 1

			i1 = self._findMutationParentIndex(reproduceMutationSize)
			reproduceCreature = self.individuals[i1][self.CREATURE]
			child = copy.deepcopy(reproduceCreature)
			child.mutate(self.mutationConfig["config"])
			
			replaceIndividual(self._findEliminateIndex(eliminateMutationSize), child)

		self.populationConfig["generation"] += 1
		
		print("Proceeded to generation " + str(self.populationConfig["generation"]) + ". " + str(numCrossoverChildren+numMutateChildren) + " children created")

	def getStatusNumeric(self):
		return { "numInFlight": len(self.indicesInFlight), "numWithFitness": self.getNumWithFitness(), "populationSize": len(self.individuals)}
	
	def getStatus(self):
		status = self.getStatusNumeric()

		return "GA(" + str(status["populationSize"]) + "): in flight = " + str(status["numInFlight"]) + " w/fitness=" + str(status["numWithFitness"])

	def getForFitness(self):
		picked = None
		for i in self.indicesMissingFitness:
			if math.isnan(self.individuals[i][self.IN_FLIGHT]):
				self.individuals[i][self.IN_FLIGHT] = time.monotonic()
				self.indicesInFlight.append(i)
				picked = self.individuals[i][self.CREATURE]
				break

		return picked

	def startEvaluation(self, creatureId):
		evaluationId = str(uuid.uuid4())
		self.activeEvaluationIds[creatureId] = evaluationId
		return evaluationId

	def isCurrentEvaluation(self, creatureId, evaluationId):
		return self.activeEvaluationIds.get(creatureId) == evaluationId

	def continueEvaluation(self, creatureId):
		self.activeEvaluationIds.pop(creatureId, None)
			

	def setCreatureFitness(self, creatureId, fitness):
		if not creatureId in self.creatureIndexLookup:
			return		# No longer an active creature. Fitness calculation which is a late arrival and was considered lost.

		i = self.creatureIndexLookup[creatureId]

		#if not math.isnan(self.individuals[i][self.FITNESS]):
		#	return   # Already has fitness. This is probably because the fitness calculation was given up, but now arrived late. Already have fitness result so ignore
		#if self.indicesInFlight.count(i) != 1:
		#	print("malformed: count " + str(i) + " = " + str(self.indicesInFlight.count(i)))
		
		if self.indicesInFlight.count(i) != 0:
			self.indicesInFlight.remove(i)

		creature = self.individuals[i][self.CREATURE]
		if(creature.nextFitnessLog):
			print("Fitness=" + str(fitness) + ". " + creature.nextFitnessLog)
		self.individuals[i][self.FITNESS] = fitness
		
		if self.indicesMissingFitness.count(i) != 0:
			self.indicesMissingFitness.remove(i)

		self.individuals[i][self.IN_FLIGHT] = float("nan")
		self.activeEvaluationIds.pop(creatureId, None)
		
		
class Trainer():	
	def __init__(self, config):
		def startAlgorithm():
			def resetFitness(creatures):
				for creature in creatures:
					creature["fitness"] = None

			algorithmType = config["json"]["algorithm"]["type"]
			if algorithmType == "GeneticAlgorithm":
				arguments = config["json"]["algorithm"]["arguments"]
				structure = config["json"]["structure"]
				
				if config["resetFitness"] and structure["creatures"]:
					resetFitness(structure["creatures"])

				self.algorithm = GeneticAlgorithm(
					arguments["population"],
					arguments["crossover"],
					arguments["mutation"],
					structure,
					{ "saveState": self.saveState })
			elif algorithmType == "MapElites":
				arguments = config["json"]["algorithm"]["arguments"]
				structure = config["json"]["structure"]
				if config["resetFitness"]:
					structure["creatures"] = []
				self.algorithm = MapElitesAlgorithm(
					arguments["population"],
					arguments["mutation"],
					structure,
					arguments["archive"],
					{ "saveState": self.saveState })
			else:
				sys.exit("Algorithm type must be 'GeneticAlgorithm' or 'MapElites'. Got '" + algorithmType + "'");

		self.config = config
		# ThreadingTCPServer dispatches requests concurrently.  All callbacks
		# below share the genetic algorithm state, so serialize that boundary.
		# RLock is intentional because batch callbacks call registerResult and
		# population maintenance can call saveState.
		self.stateLock = threading.RLock()
		self.startTime = time.monotonic()
		self.experimentId = str(uuid.uuid4())
		self.stopReason = None
		self.stopFinalized = False
		trainerState = self.config["json"].get("experiment", {}).get("trainerState", {})
		self.domainProgress = copy.deepcopy(trainerState.get("domainProgress", {}))
		self.domainQueue = list(self.domainProgress.keys())
		self.evaluationContexts = {}
		self.evaluationHistory = list(trainerState.get("evaluationHistory", []))
		self.evaluationSimulations = int(trainerState.get("evaluationSimulations", 0))
		self.statistics = { "accumulatedSimulatedTime": 0, "accumulatedFitness": {}, "accumulatedSimulatedCreatures": {}, "timeStamp": time.monotonic() }
		self.lastStatus = "...waiting..."

		startAlgorithm()
		if hasattr(self.algorithm, "reserveEvaluation"):
			for creatureId in self.domainProgress:
				self.algorithm.reserveEvaluation(creatureId)

		self.bestFitness = self.algorithm.getBestFitness()
		currentEvaluations = int(self.algorithm.populationConfig["evaluations"])
		trainerState = self.config["json"].get("experiment", {}).get("trainerState", {})
		self.bestFitnessEvaluation = int(trainerState.get("bestFitnessEvaluation", currentEvaluations))
		if self.bestFitnessEvaluation < 0 or self.bestFitnessEvaluation > currentEvaluations:
			self.bestFitnessEvaluation = currentEvaluations

		try:
			self.communicator = Communicator(self.getWork, self.getWorkBatch, self.doStepBatch, self.registerResult, self.getServerStatus, self.getBestCreature)
			self.communicator.start()
		except KeyboardInterrupt:
			self.requestStop("signal", "Exiting after an interrupt signal.")
			self.finalizeStop()
		except Exception as e:
			print(e)
			raise

	def saveState(self):
		with self.stateLock:
			creatures = self.algorithm.getCreaturesWithFitnessJson()
			if(creatures != None and len(creatures)>0):
				self.config["json"]["structure"]["creatures"] = creatures

			trainerState = self.config["json"].setdefault("experiment", {}).setdefault("trainerState", {})
			trainerState["schemaVersion"] = 1
			trainerState["pythonRandomState"] = random.getstate()
			trainerState["bestFitnessEvaluation"] = self.bestFitnessEvaluation
			trainerState["domainProgress"] = getattr(self, "domainProgress", {})
			trainerState["evaluationHistory"] = getattr(self, "evaluationHistory", [])[-10000:]
			trainerState["evaluationSimulations"] = getattr(self, "evaluationSimulations", 0)

			serialized = json.dumps(self.config["json"], indent=1, separators=(',', ': '), allow_nan=False)
			#serialized = json.dumps(config["json"])

			temporaryFilename = self.config["filename"] + ".tmp"
			with open(temporaryFilename, "w") as file:
				bytesWritten = file.write(serialized)
				file.flush()
				os.fsync(file.fileno())
			os.replace(temporaryFilename, self.config["filename"])
			print(str(bytesWritten) + " bytes written to " + self.config["filename"] + ". ")

	def terminateSession(self):
		print("terminate!!")

	def requestStop(self, reason, message):
		with self.stateLock:
			self._requestStop(reason, message)

	def _requestStop(self, reason, message):
		if self.stopReason is None:
			self.stopReason = reason
			print(message)

	def updateStopReason(self):
		with self.stateLock:
			self._updateStopReason()

	def _updateStopReason(self):
		if self.config["terminateEvaluations"] and self.algorithm.populationConfig["evaluations"] >= self.config["terminateEvaluations"]:
			self.requestStop(
				"evaluation-limit",
				"Exiting since max number of fitness evaluations has been performed. terminate-evaluations={}.".format(self.config["terminateEvaluations"]))
		elif wallClockLimitReached(self.startTime, self.config["terminateSeconds"]):
			self.requestStop(
				"wall-clock-limit",
				"Exiting since the wall-clock training limit has been reached. terminate-seconds={}.".format(self.config["terminateSeconds"]))
		elif self.config["terminateStallEvaluations"] and self.algorithm.populationConfig["evaluations"] - self.bestFitnessEvaluation >= self.config["terminateStallEvaluations"]:
			self.requestStop(
				"fitness-stall",
				"Exiting since no new best creature has been found for terminate-stall-evaluations={}.".format(self.config["terminateStallEvaluations"]))

	def finalizeStop(self):
		with self.stateLock:
			if self.stopReason is None or self.stopFinalized:
				return
			self.stopFinalized = True
			self.saveState()
			self.communicator.stop()

	def registerResult(self, data, finalizeStop=True):
		with self.stateLock:
			return self._registerResult(data, finalizeStop)

	def _registerResult(self, data, finalizeStop=True):
		experimentId = data["experimentId"]
		if experimentId != self.experimentId:
			print("Ignoring this result since experimentId of returned result does not match current experimentId.")
			return "FAIL"

		creatureId = data["id"]
		creature = self.algorithm.getCreature(creatureId)
		if not creature:
			return "FAIL"
		if not self.algorithm.isCurrentEvaluation(creatureId, data.get("evaluationId")):
			if hasattr(self.algorithm, "recordEmitterFailure"):
				self.algorithm.recordEmitterFailure(creature.emitterId, invalidOutcome=True)
			print("Ignoring stale or duplicate evaluation result for creature {}.".format(creatureId))
			return "FAIL"

		try:
			rawDistance = float(data["maxDistance"])
			fitness = float(data.get("fitness", rawDistance))
			simulatedTime = float(data["simulatedTime"])
		except (KeyError, TypeError, ValueError, OverflowError):
			if hasattr(self.algorithm, "recordEmitterFailure"):
				self.algorithm.recordEmitterFailure(creature.emitterId, invalidOutcome=True)
			print("Ignoring evaluation result for creature {} because its distance, fitness, or simulated time is not numeric.".format(creatureId))
			return "FAIL"
		if not math.isfinite(rawDistance) or not math.isfinite(fitness) or not math.isfinite(simulatedTime):
			if hasattr(self.algorithm, "recordEmitterFailure"):
				self.algorithm.recordEmitterFailure(creature.emitterId, invalidOutcome=True)
			print("Ignoring evaluation result for creature {} because its distance, fitness, or simulated time is not finite.".format(creatureId))
			return "FAIL"
		try:
			motion = data.get("motion", {})
			if not isinstance(motion, dict):
				raise TypeError()
			nearGroundTimeFraction = float(motion.get("nearGroundTimeFraction", 1.0))
			rollingExplainedFraction = float(motion.get("rollingExplainedFraction", 0.0))
		except (TypeError, ValueError, OverflowError):
			if hasattr(self.algorithm, "recordEmitterFailure"):
				self.algorithm.recordEmitterFailure(creature.emitterId, invalidOutcome=True)
			print("Ignoring evaluation result for creature {} because its motion descriptor is not numeric.".format(creatureId))
			return "FAIL"
		if not math.isfinite(nearGroundTimeFraction) or not math.isfinite(rollingExplainedFraction):
			if hasattr(self.algorithm, "recordEmitterFailure"):
				self.algorithm.recordEmitterFailure(creature.emitterId, invalidOutcome=True)
			print("Ignoring evaluation result for creature {} because its motion descriptor is not finite.".format(creatureId))
			return "FAIL"

		#print("fitness={}".format(fitness))

		# print(data["type"] + ": " + creatureId + ", fitness=" + str(fitness) + ", best=" + str(self.bestFitness))

		if not creature.generatorType in self.statistics["accumulatedFitness"]:
			self.statistics["accumulatedFitness"][creature.generatorType] = 0
			self.statistics["accumulatedSimulatedCreatures"][creature.generatorType] = 0

		self.statistics["accumulatedFitness"][creature.generatorType] += fitness
		self.statistics["accumulatedSimulatedCreatures"][creature.generatorType] += 1
		
		self.statistics["accumulatedSimulatedTime"] += simulatedTime
		self.evaluationSimulations = getattr(self, "evaluationSimulations", 0) + 1

		if not hasattr(self, "evaluationContexts"):
			self.evaluationContexts = {}
		if not hasattr(self, "domainProgress"):
			self.domainProgress = {}
		if not hasattr(self, "domainQueue"):
			self.domainQueue = []
		if not hasattr(self, "evaluationHistory"):
			self.evaluationHistory = []
		context = self.evaluationContexts.pop(data.get("evaluationId"), {})
		domains = self.config.get("json", {}).get("experiment", {}).get("evaluationDomains", [])
		if not domains:
			domains = [{"id": "nominal"}]
		progress = self.domainProgress.setdefault(creatureId, {"results": []})
		progress["results"].append({
			"domainId": context.get("domainId", domains[len(progress["results"])]["id"]),
			"distance": rawDistance,
			"fitness": fitness,
			"motion": motion,
		})
		if len(progress["results"]) < len(domains):
			self.algorithm.continueEvaluation(creatureId)
			if creatureId not in self.domainQueue:
				self.domainQueue.append(creatureId)
			return "OK"

		results = progress["results"]
		domainScores = [float(result["fitness"]) for result in results]
		if any(score < 0 for score in domainScores):
			robustFitness = min(domainScores)
		else:
			geometricMean = math.prod(domainScores) ** (1.0 / len(domainScores))
			robustFitness = 0.5 * (min(domainScores) + geometricMean)
		nominalMotion = results[0].get("motion", {})
		behavior = {
			"airborneFraction": max(0.0, min(1.0, 1.0 - float(nominalMotion.get("nearGroundTimeFraction", 1.0)))),
			"rotationParticipation": max(0.0, min(1.0, float(nominalMotion.get("rollingExplainedFraction", 0.0)))),
		}
		self.domainProgress.pop(creatureId, None)
		self.algorithm.populationConfig["evaluations"] += 1
		insertionResult = None
		if hasattr(self.algorithm, "setCreatureEvaluation"):
			self.algorithm.setCreatureEvaluation(creatureId, robustFitness, behavior, domainScores)
			if hasattr(self.algorithm, "getLastInsertionResult"):
				insertionResult = self.algorithm.getLastInsertionResult()
		else:
			self.algorithm.setCreatureFitness(creatureId, robustFitness)
		historyEntry = {
			"evaluation": self.algorithm.populationConfig["evaluations"],
			"creatureId": creatureId,
			"morphologyId": creature.morphologyId,
			"robustFitness": robustFitness,
			"domainScores": domainScores,
			"behavior": behavior,
		}
		if insertionResult is not None:
			historyEntry.update({
				"emitterId": creature.emitterId,
				"insertionOutcome": insertionResult["outcome"],
				"qdDelta": insertionResult["qdDelta"],
				"qdScore": insertionResult["qdScore"],
			})
			print(
				"MAP-Elites insertion: outcome={} qd-delta={:.6f} qd-score={:.6f} emitter={}".format(
					insertionResult["outcome"], insertionResult["qdDelta"],
					insertionResult["qdScore"], creature.emitterId or "initial-population"))
		self.evaluationHistory.append(historyEntry)
		
		if robustFitness > self.bestFitness or math.isnan(self.bestFitness):
			self.bestFitness = robustFitness
			self.bestFitnessEvaluation = self.algorithm.populationConfig["evaluations"]
			print("--> new robust best creature found through {}! Fitness={} domains={}".format(creature.generatorType, robustFitness, domainScores))

		self.updateStopReason()
		if finalizeStop:
			self.finalizeStop()

		return "OK"		# Notify client request handled successfully

	def getServerStatus(self):
		with self.stateLock:
			return json.dumps(self.getServerStatusUnserialized())
	
	def getServerStatusUnserialized(self):
		# This code only works where there is a single client (can have multiple worker threads)
		currentTime = time.monotonic()
		deltaTime = currentTime - self.statistics["timeStamp"]
		if deltaTime > 2:
			accumulatedFitness = 0
			accumulatedSimulatedCreatures = 0
			generatorTypeStatus = ""
			for key in self.statistics["accumulatedFitness"]:
				accumulatedFitness += self.statistics["accumulatedFitness"][key]
				accumulatedSimulatedCreatures += self.statistics["accumulatedSimulatedCreatures"][key]
				if not generatorTypeStatus == "":
					generatorTypeStatus += ", "
				generatorTypeStatus += key + "={:.1f}".format(self.statistics["accumulatedFitness"][key]/self.statistics["accumulatedSimulatedCreatures"][key])

			#averageFitness = accumulatedFitness/accumulatedSimulatedCreatures if accumulatedSimulatedCreatures>0 else 0
			#self.lastStatus = time.strftime("%H:%M:%S: ") + "{0:.0f}x RT, {1:.1f} creatures/sec  avg fitness={2:.1f}  best fitness={3:.1f}".format(self.statistics["accumulatedSimulatedTime"]/deltaTime, accumulatedSimulatedCreatures/deltaTime, averageFitness, self.bestFitness)
			self.lastStatus = time.strftime("%H:%M:%S: ") + "{:.0f}x RT, {:.1f} creatures/sec. Fitness: best={:.1f}, avg={:.1f}, new=({:s})".format(self.statistics["accumulatedSimulatedTime"]/deltaTime, accumulatedSimulatedCreatures/deltaTime, self.bestFitness, self.algorithm.getAverageFitness(), generatorTypeStatus)
			self.lastStatus = self.lastStatus + ". " + self.algorithm.getStatus()

			for key in self.statistics["accumulatedFitness"].copy():
				self.statistics["accumulatedFitness"].pop(key, None)
				self.statistics["accumulatedSimulatedCreatures"].pop(key, None)

			self.statistics["accumulatedSimulatedTime"] = 0
			self.statistics["timeStamp"] = currentTime

			print(self.lastStatus)

		return { "status": self.lastStatus }

	def getBestCreature(self):
		with self.stateLock:
			return self.getWork(True)

	def doStepBatch(self, data):
		with self.stateLock:
			return self._doStepBatch(data)

	def _doStepBatch(self, data):
		for result in data["results"]:
			self.registerResult(result, finalizeStop=False)

		self.updateStopReason()
		self.finalizeStop()

		if self.communicator.isStopped:
			response = { "workUnits": [] }
		else:
			response = self.getWorkBatchUnserialized(data)
		response["status"] = self.getServerStatusUnserialized()["status"]
		response["stopped"] = self.communicator.isStopped

		return json.dumps(response)

	def getWorkBatch(self, data):
		with self.stateLock:
			return json.dumps(self.getWorkBatchUnserialized(data))

	def getWorkBatchUnserialized(self, data):
		self.updateStopReason()
		if self.stopReason is not None:
			self.finalizeStop()
			return { "workUnits": [] }

		remaining = data["maxWorkUnits"]
		workUnits = []
		noWork = False
		
		while not noWork and remaining > 0:
			work = self.getWorkUnserialized(False)
			if work["status"] == "NO_WORK":
				noWork = True
			else:
				workUnits.append(work)
				remaining -= 1

		return { "workUnits": workUnits }

	def getWorkUnserialized(self, getBestForPlayback):
		if getBestForPlayback:
			creature = self.algorithm.getBestCreature()
		else:
			self.updateStopReason()
			if self.stopReason is not None:
				self.finalizeStop()
				return { "status": "NO_WORK" }
			self.algorithm.maintainPopulation()
			creature = None
			while self.domainQueue and creature is None:
				creatureId = self.domainQueue.pop(0)
				creature = self.algorithm.getCreature(creatureId)
			if creature is None:
				creature = self.algorithm.getForFitness()

		if creature :
			experiment = self.config["json"].get("experiment", {})
			objective = copy.deepcopy(experiment.get("objective", {}))
			physics = copy.deepcopy(experiment.get("physics", {}))
			domains = experiment.get("evaluationDomains", [])
			progress = self.domainProgress.get(creature.id, {"results": []})
			domainIndex = 0 if getBestForPlayback or not domains else len(progress["results"])
			domain = domains[domainIndex] if domains else {"id": "nominal"}
			physics.update(domain.get("physics", {}))
			objective.update(domain.get("objective", {}))
			physics["backend"] = experiment.get("backend", "machine-evolved-bullet-v1")
			controlRateHz = int(physics.get("controlRateHz", objective.get("fixedStepHz", 60)))
			evaluationId = self.algorithm.startEvaluation(creature.id)
			if not getBestForPlayback and hasattr(self.algorithm, "recordEmitterAttempt"):
				self.algorithm.recordEmitterAttempt(creature.emitterId)
			self.evaluationContexts[evaluationId] = {"creatureId": creature.id, "domainId": domain.get("id", "nominal")}
			taskJson = {
				"name": "MOVE_FAR",
				"id": creature.id,
				"experimentId": self.experimentId,
				"evaluationId": evaluationId,
				"domainId": domain.get("id", "nominal"),
				"horizonTicks": int(objective.get("horizonTicks", 60 * 60)),
				"controlRateHz": controlRateHz,
				"objective": objective,
			}
			work = { "status": "OK", "task": taskJson, "creature": creature.getJson(), "physics": physics }
		else:
			work = { "status": "NO_WORK" }
		
		return work


	def getWork(self, getBestForPlayback = False):
		with self.stateLock:
			return json.dumps(self.getWorkUnserialized(getBestForPlayback))

def getJson():
	def parseCommandLineArguments():
		parser = argparse.ArgumentParser(description='Starts the Machine Evolved trainer.')
		parser.add_argument('config', metavar='config', type=argparse.FileType('r'), 
						help='Filename of json file configuring the simulation.')
		parser.add_argument('--reset-fitness', dest="resetFitness", const="resetFitness", action='store_const', help='specify to reset fitness of all creatures of loaded population (default: re-use fitness values)')
		parser.add_argument("--terminate-evaluations", type=int, help="terminate after this many fitness evaluations have been performed. if not specified, never terminate.")
		parser.add_argument("--terminate-seconds", type=float, help="terminate after this many wall-clock seconds and save the latest population. if not specified, never terminate.")
		parser.add_argument("--terminate-stall-evaluations", type=int, help="terminate after this many fitness evaluations that didn't cause the best fitness to improve. if not specified, never terminate.")
		parser.add_argument("--result-filename", help="If specified, append the result of the simulation to csv file specified here. Default: Do not write results to file.")
		parser.add_argument("--seed", type=int, help="seed Python's random generator and persist it in the experiment configuration")
		
		return parser.parse_args()

	args = parseCommandLineArguments()
	if args.terminate_seconds is not None and args.terminate_seconds <= 0:
		raise ValueError("--terminate-seconds must be greater than zero")

	filename = args.config.name
	resetFitness = True if args.resetFitness else False

	with open(filename) as file:
		loadedJson = json.load(file)

	experiment = loadedJson.setdefault("experiment", {})
	seed = args.seed if args.seed is not None else experiment.get("seed")
	if seed is not None:
		experiment["seed"] = seed

	return {"resultFilename": args.result_filename, "seed": seed, "terminateEvaluations": args.terminate_evaluations, "terminateSeconds": args.terminate_seconds, "terminateStallEvaluations": args.terminate_stall_evaluations, "filename": filename, "json": loadedJson, "resetFitness": resetFitness}

def writeResult(trainer, filename):
	generator = config["json"]["structure"]["generator"]
	inputs = generator["inputs"]
	bestCreature = trainer.algorithm.getBestCreature()
	population = config["json"]["algorithm"]["arguments"]["population"]
	headerRow = ""
	valueRow = ""

	headerRow += "best fitness"
	valueRow += str(trainer.algorithm.getBestFitness())

	headerRow += ",average fitness"
	valueRow += "," + str(trainer.algorithm.getAverageFitness())
	
	headerRow += ",generations"
	valueRow += "," + str(population["generation"])

	headerRow += ",fitness evaluations"
	valueRow += "," + str(population["evaluations"])

	headerRow += ",population size"
	valueRow += "," + str(population["size"])
	
	headerRow += ",oscillators count"
	valueRow += "," + str(generator["oscillators"]["count"])
	
	headerRow += ",oscillators multiplier"
	valueRow += "," + str(generator["oscillators"]["multiplier"])
	
	headerRow += ",oscillators start"
	valueRow += "," + str(generator["oscillators"]["start"])
	
	headerRow += ",feedbacks"
	valueRow += "," + str(generator["feedbacks"])

	headerRow += ",layers"
	valueRow += "," + str(len(generator["motorController"]["layers"]))

	headerRow += ",data file"
	valueRow += "," + config["filename"][config["filename"].rfind("\\")+1:]

	for key in sorted(inputs):
		headerRow += ","
		headerRow += key
		
		valueRow += ","
		valueRow += str(inputs[key])

	headerRow += ",total inputs"
	valueRow += "," + str(bestCreature.structure.getNumInputs())

	if os.path.isfile(filename):
		with open(filename, "a") as file:
			file.write(valueRow + "\n")
		print("Appended results to " + filename)
	else:
		with open(filename, "w+") as file:
			file.write(headerRow + "\n")
			file.write(valueRow + "\n")
		print("Created new results file " + filename + " and wrote results.")

if __name__ == "__main__":
	def interruptHandler(signum, frame):
		raise KeyboardInterrupt()

	signal.signal(signal.SIGINT, interruptHandler)
	signal.signal(signal.SIGTERM, interruptHandler)
	config = getJson()
	restoreRandomState(config)
	trainer = Trainer(config)

	if(config["resultFilename"]):
		writeResult(trainer, config["resultFilename"])
