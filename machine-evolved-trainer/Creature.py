from CreatureStructure import CreatureStructure, CAPSULE
from LinearMotorController import LinearMotorController

from math import sqrt
import random
import json
import uuid
import copy

class Creature():
	# structureJson: Object hierarchy of actuall structure (capsules etc) if it exists from before
	# generatorJson: Configuration for generator
	def __init__(self, structureJson = None, generatorJson = None, structureTemplate = None, morphologyId = None):
		self.generatorJson = generatorJson
		self.morphologyId = morphologyId
		self.emitterId = None
		self.emitterFailureCount = 0
		motorsJson = None
		if structureJson:
			self.structure = CreatureStructure(structureJson["structure"])
			motorsJson = structureJson["motorController"]
			metadata = structureJson.get("metadata", {})
			self.morphologyId = metadata.get("morphologyId", morphologyId)
			self.emitterId = metadata.get("emitterId")
			self.emitterFailureCount = int(metadata.get("emitterFailureCount", 0))
			self.generatorType = "loaded"
		elif structureTemplate:
			self.structure = CreatureStructure(copy.deepcopy(structureTemplate))
			self.generatorType = "template-{}".format(morphologyId or "unnamed")
		else:
			self.structure = self.createStructure()
			self.generatorType = "randomized"
		
		self.motorController = LinearMotorController(self.structure.getNumInputs(), self.structure.getNumOutputs(), motorsJson, generatorJson["motorController"])

		self.id = structureJson.get("metadata", {}).get("creatureId", str(uuid.uuid4())) if structureJson else str(uuid.uuid4())
		self.nextFitnessLog = ""

	# Picks a random number in a rangeStr (which is on format "FROM-TO")
	@staticmethod
	def pickRandomNumberFromRange(rangeStr, seperator = "-"):
		rangeNumeric = rangeStr.split(seperator)
		return random.uniform(float(rangeNumeric[0]), float(rangeNumeric[1]))

	def getJson(self):
		result = { "structure": self.structure.getJson(), "motorController": self.motorController.getJson() }
		metadata = {}
		if self.morphologyId is not None:
			metadata["morphologyId"] = self.morphologyId
		if self.emitterId is not None:
			metadata["emitterId"] = self.emitterId
			if self.emitterFailureCount:
				metadata["emitterFailureCount"] = self.emitterFailureCount
		if metadata:
			result["metadata"] = metadata
		return result

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
		structure.setOscillatorMode(self.generatorJson["oscillators"].get("mode", "sin-v1"))

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
