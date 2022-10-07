from CreatureStructure import CreatureStructure, CAPSULE
from LinearMotorController import LinearMotorController

from math import sqrt
import random
import json
import uuid

class Creature():
	# structureJson: Object hierarchy of actuall structure (capsules etc) if it exists from before
	# generatorJson: Configuration for generator
	def __init__(self, structureJson = None, generatorJson = None):
		self.generatorJson = generatorJson
		motorsJson = None
		if structureJson:
			self.structure = CreatureStructure(structureJson["structure"])
			motorsJson = structureJson["motorController"]
			self.generatorType = "loaded"
		else:
			self.structure = self.createStructure()
			self.generatorType = "randomized"
		
		self.motorController = LinearMotorController(self.structure.getNumInputs(), self.structure.getNumOutputs(), motorsJson, generatorJson["motorController"])

		self.id = str(uuid.uuid4())
		self.nextFitnessLog = ""

	# Picks a random number in a rangeStr (which is on format "FROM-TO")
	@staticmethod
	def pickRandomNumberFromRange(rangeStr, seperator = "-"):
		rangeNumeric = rangeStr.split(seperator)
		return random.uniform(float(rangeNumeric[0]), float(rangeNumeric[1]))

	def getJson(self):
		return { "structure": self.structure.getJson(), "motorController": self.motorController.getJson() }

	def serialize(self):
		return json.dumps(self.getJson())

	def createStructure(self):
		def normalize(v, tolerance=0.00001):
			mag2 = sum(n * n for n in v)
			if abs(mag2 - 1.0) > tolerance:
				mag = sqrt(mag2)
				v = tuple(n / mag for n in v)
			return v
		
		quaternion = (1, 0, 0, 1)	# http://www.onlineconversion.com/quaternions.htm
		quaternion = normalize(quaternion)

		structure = CreatureStructure()

		structure.setInputs(self.generatorJson["inputs"])
		structure.setNumFeedbacks(self.generatorJson["feedbacks"])
		structure.setOscillatorStart(self.generatorJson["oscillators"]["start"])
		structure.setOscillatorMultiplier(self.generatorJson["oscillators"]["multiplier"])
		structure.setOscillatorCount(self.generatorJson["oscillators"]["count"])

		capsule = CAPSULE(
			str(uuid.uuid4()),
			Creature.pickRandomNumberFromRange(self.generatorJson["capsuleInnerHeightRange"]),
			Creature.pickRandomNumberFromRange(self.generatorJson["capsuleRadiusRange"]),
			0, 
			0, 
			float(self.generatorJson["capsuleRadiusRange"].split("-")[1])+1,	 # place just above ground 
			quaternion[0], 
			quaternion[1], 
			quaternion[2], 
			quaternion[3], 
			"")
		structure.addCapsule(capsule)

		for i in range(0, int(self.generatorJson["numCapsules"])-1):
			capsule = structure.addCapsuleWithConstraint(
				Creature.pickRandomNumberFromRange(self.generatorJson["capsuleInnerHeightRange"]),
				Creature.pickRandomNumberFromRange(self.generatorJson["capsuleRadiusRange"]),
				capsule,
				self.generatorJson["motors"])
		
		return structure

	def mutate(self, configJson):
		self.id = str(uuid.uuid4())
		self.motorController.mutate(configJson)
		self.generatorType = "mutate"

	def crossover(self, creature, configJson):
		self.id = str(uuid.uuid4())
		self.motorController.crossover(creature, configJson)
		self.generatorType = "crossover"