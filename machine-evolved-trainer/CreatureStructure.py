# This class must exactly match the CreatureStructure c++ class in MachineWorker.

from collections import namedtuple
import json
import uuid
from pprint import pprint

CAPSULE = namedtuple("CAPSULE", "id innerHeight radius positionX positionY positionZ quaternionX quaternionY quaternionZ quaternionW constraint")

class CreatureStructure:
	def __init__(self, jsonData = None):
		self.capsules = []
		self.numFeedbacks = 0
		self.inputs = {}
		
		if jsonData != None:
			self.buildFromJson(jsonData)

	def setInputs(self, inputs):
		self.inputs = inputs

	def setNumFeedbacks(self, num):
		self.numFeedbacks = num

	def setOscillatorStart(self, startRatio):
		self.oscillatorStart = startRatio

	def setOscillatorMultiplier(self, multiplier):
		self.oscillatorMultiplier = multiplier

	def setOscillatorCount(self, count):
		self.oscillatorCount = count
		
	def buildFromJson(self, jsonData):
		self.numFeedbacks = jsonData["feedbacks"]
		self.oscillatorStart = jsonData["oscillators"]["start"]
		self.oscillatorMultiplier = jsonData["oscillators"]["multiplier"]
		self.oscillatorCount = jsonData["oscillators"]["count"]
		self.inputs = jsonData["inputs"]

		for item in jsonData["capsules"]:
			capsule = CAPSULE(item["id"], item["innerHeight"], item["radius"], item["positionX"], item["positionY"], item["positionZ"], item["quaternionX"], item["quaternionY"], item["quaternionZ"], item["quaternionW"], item["constraint"])
			self.addCapsule(capsule)

	def addCapsule(self, capsule):
		self.capsules.append(capsule)

	# configJson: A dictonary with configuration details for the constraint. As of 17/9 in structure/generator/motors.
	def addCapsuleWithConstraint(self, innerHeight, radius, parentCapsule, configJson):
		# inner functions are quaternion linear algebra helper functions to avoid importing external libraries
		def quaternion_conjugate(q):
			w, x, y, z = q
			return (w, -x, -y, -z)

		def quaternion_mult(q1, q2):
			w1, x1, y1, z1 = q1
			w2, x2, y2, z2 = q2
			w = w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2
			x = w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2
			y = w1 * y2 + y1 * w2 + z1 * x2 - x1 * z2
			z = w1 * z2 + z1 * w2 + x1 * y2 - y1 * x2
			return w, x, y, z

		def quaternion_vector_mult(q1, v1):
			q2 = (0.0,) + v1
			return quaternion_mult(quaternion_mult(q1, q2), quaternion_conjugate(q1))[1:]

		middlePosition = (0, 0, .5*parentCapsule.innerHeight + parentCapsule.radius + .5*innerHeight + radius)
		parentQuaternion = (parentCapsule.quaternionW, parentCapsule.quaternionX, parentCapsule.quaternionY, parentCapsule.quaternionZ)		# Using w,x,y,z notation - not x,y,z,w like I do in c++
		rotatedPosition = quaternion_vector_mult(parentQuaternion, middlePosition)
		newPosition = (rotatedPosition[0] + parentCapsule.positionX, rotatedPosition[1] + parentCapsule.positionY, rotatedPosition[2] + parentCapsule.positionZ)

		configWithParent = configJson.copy()
		configWithParent["parentId"] = parentCapsule.id
		capsule = CAPSULE(str(uuid.uuid4()), innerHeight, radius, newPosition[0], newPosition[1], newPosition[2], parentCapsule.quaternionX, parentCapsule.quaternionY, parentCapsule.quaternionZ, parentCapsule.quaternionW, configWithParent)
		self.addCapsule(capsule)
		return capsule

	def getCapsules(self):
		return self.capsules

	def getJson(self):
		capsules = []
		for capsule in self.capsules:
			capsuleDictionary = capsule._asdict()

			capsules.append(capsuleDictionary)

		oscillators = { "start": self.oscillatorStart, "multiplier": self.oscillatorMultiplier, "count": self.oscillatorCount }

		return { "capsules": capsules, "feedbacks": self.numFeedbacks, "oscillators": oscillators, "inputs": self.inputs }

	def serialize(self):
		return json.dumps(getJson())

	def getNumInputs(self):
		# Per creature:
		numPerCreature = 0
		creatureKeys = ["root-orientation-x", "root-orientation-y", "root-orientation-z", "root-orientation-w", "z-position", "velocity-x", "velocity-y", "velocity-z"]
		for key in creatureKeys:
			if self.inputs[key] == 1:
				numPerCreature += 1
		if self.inputs["oscillators"] == 1:
			numPerCreature += self.oscillatorCount

		# Per capsule:
		numPerCapsule = 0
		capsuleKeys = ["capsule-position-x", "capsule-position-y", "capsule-position-z", "capsule-velocity-x", "capsule-velocity-y", "capsule-velocity-z", "capsule-angular-velocity-x", "capsule-angular-velocity-y", "capsule-angular-velocity-z"]
		for key in capsuleKeys:
			if self.inputs[key] == 1:
				numPerCapsule += 1

		# For motors:
		numForMotors = 0
		for capsule in self.capsules:
			if capsule.constraint:
				if "x-rotation" in capsule.constraint and self.inputs["motor-angle-x"] == 1:
					numForMotors += 1
				if "y-rotation" in capsule.constraint and self.inputs["motor-angle-y"] == 1:
					numForMotors += 1
				if "z-rotation" in capsule.constraint and self.inputs["motor-angle-z"] == 1:
					numForMotors += 1

		# For feedbacks:
		numForFeedbacks = 0
		if self.inputs["feedbacks"] == 1:
			numForFeedbacks = self.numFeedbacks

		return numPerCreature + len(self.capsules) * numPerCapsule + numForMotors + numForFeedbacks

	def getNumOutputs(self):
		num = 0

		for capsule in self.capsules:
			if capsule.constraint:
				if "x-rotation" in capsule.constraint:
					num += 1
				if "y-rotation" in capsule.constraint:
					num += 1
				if "z-rotation" in capsule.constraint:
					num += 1

		num += self.numFeedbacks

		return num

	def getNumConstraints(self):
		num = 0

		for capsule in self.capsules:
			if capsule.constraint:
				num = num + 1

		return num