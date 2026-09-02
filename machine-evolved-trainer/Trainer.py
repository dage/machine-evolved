from Communicator import Communicator
from Creature import Creature
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
				creature = Creature(None, structureConfig["generator"])
				self.individuals.append([float("nan"), creature, float("nan")])
				self.creatureIndexLookup[creature.id] = i
		else:
			# Deserialize existing creatures
			creatures = structureConfig["creatures"]
			for i in range(0, len(creatures)):
				creatureJson = creatures[i]["data"]
				rawFitness = creatures[i].get("fitness")
				fitness = float("nan") if rawFitness is None else float(rawFitness)
				creature = Creature(creatureJson, structureConfig["generator"])
				self.individuals.append([fitness, creature, float("nan")])
				self.creatureIndexLookup[creature.id] = i

				if math.isnan(fitness):
					self.indicesMissingFitness.append(i)

	def validateConfiguration(self):
		populationSize = int(self.populationConfig["size"])
		competitionSizes = [
			int(self.crossoverConfig["competitionSize"]["reproduce"]),
			int(self.crossoverConfig["competitionSize"]["eliminate"]),
			int(self.mutationConfig["competitionSize"]["reproduce"]),
			int(self.mutationConfig["competitionSize"]["eliminate"]),
		]
		if populationSize < 1 or min(competitionSizes) < 1 or max(competitionSizes) > populationSize:
			raise ValueError("Population and tournament sizes must be positive, and tournaments cannot exceed the population.")
		numChildren = int(float(self.crossoverConfig["rate"]) * populationSize)
		numChildren += int(float(self.mutationConfig["rate"]) * populationSize)
		if numChildren > populationSize - max(competitionSizes) + 1:
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
	def pickIndividuals(self, numToPick):
		eligible = [
			index for index, individual in enumerate(self.individuals)
			if not math.isnan(individual[self.FITNESS])
		]
		if numToPick > len(eligible):
			raise RuntimeError("Not enough evaluated individuals for tournament selection.")
		return random.sample(eligible, numToPick)

	def proceedToNextGeneration(self):
		def findReproduceIndex(competitionSize):
			reproduce = self.pickIndividuals(competitionSize)
			bestIndex = 0
			bestFitness = 0
			for i in reproduce:
				fitness = self.individuals[i][self.FITNESS]
				if(fitness > bestFitness):
					bestFitness = fitness
					bestIndex = i

			return bestIndex

		def findEliminateIndex(competitionSize):			
			eliminate = self.pickIndividuals(competitionSize)
			worstIndex = 0
			worstFitness = 10000000000
			for i in eliminate:
				fitness = self.individuals[i][self.FITNESS]
				if(fitness < worstFitness):
					worstFitness = fitness
					worstIndex = i

			return worstIndex

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

			i1 = findReproduceIndex(reproduceCrossoverSize)
			i2 = findReproduceIndex(reproduceCrossoverSize)
			reproduceCreature1 = self.individuals[i1][self.CREATURE]
			reproduceCreature2 = self.individuals[i2][self.CREATURE]
			child = copy.deepcopy(reproduceCreature1)
			child.crossover(reproduceCreature2, self.crossoverConfig)

			#child.nextFitnessLog = "Crossover between " + str(self.individuals[i1][self.FITNESS]) + " and " + str(self.individuals[i2][self.FITNESS]) + "."
			
			replaceIndividual(findEliminateIndex(eliminateCrossoverSize), child)


		# Create children with mutation
		numMutateChildren = 0
		self.mutationConfig
		mutationRatio = float(self.mutationConfig["rate"])
		reproduceMutationSize = int(self.mutationConfig["competitionSize"]["reproduce"])
		eliminateMutationSize = int(self.mutationConfig["competitionSize"]["eliminate"])

		while mutationRatio > 0.00001 and numMutateChildren < int(mutationRatio*len(self.individuals)):
			numMutateChildren = numMutateChildren + 1

			i1 = findReproduceIndex(reproduceMutationSize)
			reproduceCreature = self.individuals[i1][self.CREATURE]
			child = copy.deepcopy(reproduceCreature)
			child.mutate(self.mutationConfig["config"])
			
			replaceIndividual(findEliminateIndex(eliminateMutationSize), child)

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
			else:
				sys.exit("Only algorithm type 'GeneticAlgorithm' currently implemented. Got '" + algorithmType + "'");

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
		self.statistics = { "accumulatedSimulatedTime": 0, "accumulatedFitness": {}, "accumulatedSimulatedCreatures": {}, "timeStamp": time.monotonic() }
		self.lastStatus = "...waiting..."

		startAlgorithm()

		self.bestFitness = self.algorithm.getBestFitness()
		self.bestFitnessEvaluation = self.algorithm.populationConfig["evaluations"]

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
			print("Ignoring stale or duplicate evaluation result for creature {}.".format(creatureId))
			return "FAIL"

		try:
			rawDistance = float(data["maxDistance"])
			fitness = float(data.get("fitness", rawDistance))
			simulatedTime = float(data["simulatedTime"])
		except (KeyError, TypeError, ValueError, OverflowError):
			print("Ignoring evaluation result for creature {} because its distance, fitness, or simulated time is not numeric.".format(creatureId))
			return "FAIL"
		if not math.isfinite(rawDistance) or not math.isfinite(fitness) or not math.isfinite(simulatedTime):
			print("Ignoring evaluation result for creature {} because its distance, fitness, or simulated time is not finite.".format(creatureId))
			return "FAIL"

		#print("fitness={}".format(fitness))

		# print(data["type"] + ": " + creatureId + ", fitness=" + str(fitness) + ", best=" + str(self.bestFitness))

		if not creature.generatorType in self.statistics["accumulatedFitness"]:
			self.statistics["accumulatedFitness"][creature.generatorType] = 0
			self.statistics["accumulatedSimulatedCreatures"][creature.generatorType] = 0

		self.statistics["accumulatedFitness"][creature.generatorType] += fitness
		self.statistics["accumulatedSimulatedCreatures"][creature.generatorType] += 1
		
		self.statistics["accumulatedSimulatedTime"] += simulatedTime

		self.algorithm.populationConfig["evaluations"] += 1
		self.algorithm.setCreatureFitness(creatureId, fitness)
		
		if fitness > self.bestFitness or math.isnan(self.bestFitness):
			self.bestFitness = fitness
			self.bestFitnessEvaluation = self.algorithm.populationConfig["evaluations"]
			print("--> new best creature found through {}! Fitness={}".format(creature.generatorType, fitness))

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
			creature = self.algorithm.getForFitness()

		if creature :
			experiment = self.config["json"].get("experiment", {})
			objective = experiment.get("objective", {})
			physics = experiment.get("physics", {})
			taskJson = {
				"name": "MOVE_FAR",
				"id": creature.id,
				"experimentId": self.experimentId,
				"evaluationId": self.algorithm.startEvaluation(creature.id),
				"horizonTicks": int(objective.get("horizonTicks", 60 * 60)),
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
	if config["seed"] is not None:
		random.seed(config["seed"])
	trainer = Trainer(config)

	if(config["resultFilename"]):
		writeResult(trainer, config["resultFilename"])
