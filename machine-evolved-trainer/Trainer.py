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

class GeneticAlgorithm():
	individuals = []
	FITNESS = 0		# Key into individuals item tuple
	CREATURE = 1	# Key into individuals item tuple
	IN_FLIGHT = 2	# Key into individuals item tuple

	indicesMissingFitness = []
	indicesInFlight = []
	creatureIndexLookup = {}	# A dictionary that maps creature.id to index into individuals.

	def __init__(self, populationConfig, crossoverConfig, mutationConfig, structureConfig, callbacks):
		self.populationConfig = populationConfig
		self.crossoverConfig = crossoverConfig
		self.mutationConfig = mutationConfig
		self.structureConfig = structureConfig
		self.saveStateTimestamp = time.time()
		self.callbacks = callbacks

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
				fitness = float(creatures[i]["fitness"])
				creature = Creature(creatureJson, structureConfig["generator"])
				self.individuals.append([fitness, creature, float("nan")])
				self.creatureIndexLookup[creature.id] = i
				
				if math.isnan(fitness):
					self.indicesMissingFitness.append(i)

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
			output.append({ "fitness": i[self.FITNESS], "data": i[self.CREATURE].getJson() })
		return output
	
	def getIndexBestCreature(self):
		bestFitness = self.individuals[0][self.FITNESS]
		bestIndex = -1

		for j in range(0, len(self.individuals)):
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
		numMissingFitness = len(self.indicesMissingFitness)
		indicesPutBackFromFlight = []

		#print("maintain: numMissing=" + str(numMissingFitness))

		for i in self.indicesInFlight:
			timeInFlight = time.time() -  self.individuals[i][self.IN_FLIGHT]
		#	print("maintain: timeInFlight=" + str(timeInFlight))
			if((numMissingFitness < 10 and timeInFlight > 1) or timeInFlight > 10):
				indicesPutBackFromFlight.append(i)

		for i in indicesPutBackFromFlight:
			self.individuals[i][self.IN_FLIGHT] = float("nan")	# Give up, assume will never come back
			if self.indicesInFlight.count(i) > 0:
				self.indicesInFlight.remove(i)
	
		if len(self.indicesMissingFitness) == 0:
			self.proceedToNextGeneration()

		if time.time() - self.saveStateTimestamp > 60*60:	# 1hr. TODO: Make command-line configurable
			self.saveStateTimestamp = time.time()
			self.callbacks["saveState"]()

	# Returns a list of indices into individuals
	def pickIndividuals(self, numToPick):
		picked = []
		while len(picked) < numToPick:
			i = int(random.random() * len(self.individuals))
			if not math.isnan(self.individuals[i][self.FITNESS]) and not i in picked:
				picked.append(i)

		return picked

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
				self.individuals[i][self.IN_FLIGHT] = time.time()
				self.indicesInFlight.append(i)
				picked = self.individuals[i][self.CREATURE]
				break

		return picked
			

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
		
		
class Trainer():	
	def __init__(self, config):
		def startAlgorithm():
			def resetFitness(creatures):
				for creature in creatures:
					creature["fitness"] = float("NaN")

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
		self.experimentId = str(uuid.uuid4())
		self.statistics = { "accumulatedSimulatedTime": 0, "accumulatedFitness": {}, "accumulatedSimulatedCreatures": {}, "timeStamp": time.time() }
		self.statistics["timeStamp"] = time.time()
		self.lastStatus = "...waiting..."

		startAlgorithm()

		self.bestFitness = self.algorithm.getBestFitness()
		self.bestFitnessEvaluation = self.algorithm.populationConfig["evaluations"]

		try:
			self.communicator = Communicator(self.getWork, self.getWorkBatch, self.doStepBatch, self.registerResult, self.getServerStatus, self.getBestCreature)
			self.communicator.start()
		except KeyboardInterrupt:
			self.saveState()
		except Exception as e:
			print(e)
			pass

	def saveState(self):
		creatures = self.algorithm.getCreaturesWithFitnessJson()
		if(creatures != None and len(creatures)>0):
			self.config["json"]["structure"]["creatures"] = creatures

		serialized = json.dumps(self.config["json"], indent=1, separators=(',', ': '))
		#serialized = json.dumps(config["json"])
			
		with open(self.config["filename"], "w") as file:
			bytesWritten = file.write(serialized)
			print(str(bytesWritten) + " bytes written to " + self.config["filename"] + ". ")

	def terminateSession(self):
		print("terminate!!")

	def registerResult(self, data):
		experimentId = data["experimentId"]
		if experimentId != self.experimentId:
			print("Ignoring this result since experimentId of returned result does not match current experimentId.")
			return "FAIL"

		creatureId = data["id"]
		creature = self.algorithm.getCreature(creatureId)
		if not creature:
			return "FAIL"

		fitness = data["maxDistance"]

		#print("fitness={}".format(fitness))

		simulatedTime = data["simulatedTime"]
		currentTime = time.time()

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

		if self.config["terminateEvaluations"] and self.algorithm.populationConfig["evaluations"] >= self.config["terminateEvaluations"]:
			print("Exiting since max number of fitness evaluations has been performed. terminate-evaluations={}.".format(self.config["terminateEvaluations"]))
			self.saveState()
			self.communicator.stop()
		
		if self.config["terminateStallEvaluations"] and self.algorithm.populationConfig["evaluations"] - self.bestFitnessEvaluation >= self.config["terminateStallEvaluations"]:
			print("Exiting since no new best creature has been found for terminate-stall-evaluations={}.".format(self.config["terminateStallEvaluations"]))
			self.saveState()
			self.communicator.stop()

		return "OK"		# Notify client request handled successfully

	def getServerStatus(self):
		return json.dumps(self.getServerStatusUnserialized())
	
	def getServerStatusUnserialized(self):
		# This code only works where there is a single client (can have multiple worker threads)
		currentTime = time.time()
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
		return self.getWork(True)

	def doStepBatch(self, data):
		maxNewWorkUnits = data["maxWorkUnits"]
		index = 0
		while index < len(data["results"]) and not self.communicator.isStopped:
			result = data["results"][index]
			self.registerResult(result)	
			index += 1

		response = self.getWorkBatchUnserialized(data)
		response["status"] = self.getServerStatusUnserialized()["status"]

		return json.dumps(response)

	def getWorkBatch(self, data):
		return json.dumps(getWorkBatchUnserialized(data))

	def getWorkBatchUnserialized(self, data):
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
			self.algorithm.maintainPopulation()
			creature = self.algorithm.getForFitness()

		if creature :
			taskJson = { "name": "MOVE_FAR", "id": creature.id, "experimentId": self.experimentId }
			work = { "status": "OK", "task": taskJson, "creature": creature.getJson() }
		else:
			work = { "status": "NO_WORK" }
		
		return work


	def getWork(self, getBestForPlayback = False):
		return json.dumps(self.getWorkUnserialized(getBestForPlayback))

def getJson():
	def parseCommandLineArguments():
		parser = argparse.ArgumentParser(description='Starts the Machine Evolved trainer.')
		parser.add_argument('config', metavar='config', type=argparse.FileType('r'), 
						help='Filename of json file configuring the simulation.')
		parser.add_argument('--reset-fitness', dest="resetFitness", const="resetFitness", action='store_const', help='specify to reset fitness of all creatures of loaded population (default: re-use fitness values)')
		parser.add_argument("--terminate-evaluations", type=int, help="terminate after this many fitness evaluations have been performed. if not specified, never terminate.")
		parser.add_argument("--terminate-stall-evaluations", type=int, help="terminate after this many fitness evaluations that didn't cause the best fitness to improve. if not specified, never terminate.")
		parser.add_argument("--result-filename", help="If specified, append the result of the simulation to csv file specified here. Default: Do not write results to file.")
		
		return parser.parse_args()

	args = parseCommandLineArguments()

	filename = args.config.name
	resetFitness = True if args.resetFitness else False

	with open(filename) as file:
		return {"resultFilename": args.result_filename, "terminateEvaluations": args.terminate_evaluations, "terminateStallEvaluations": args.terminate_stall_evaluations, "filename": filename, "json": json.load(file), "resetFitness": resetFitness}

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
	config = getJson()
	trainer = Trainer(config)

	if(config["resultFilename"]):
		writeResult(trainer, config["resultFilename"])
