import random
import json
import sys
import math

class LinearMotorController():
	# generatorJson: 
	def __init__(self, numInputs, numOutputs, stateJson = None, generatorJson = None):
		def createRandomizedWeights(num):
			weights = []
			for i in range(0, num):
				weights.append(random.gauss(0, 1))
			return weights

		self.layers = []
		if stateJson == None:
			# Create new randomized
			currentNumInputs = numInputs
			for layerConfig in generatorJson["layers"]:
				outputSize = layerConfig["neurons"] if "neurons" in layerConfig else numOutputs	# hidden layer neurons or output layer output
				layerState = { "activation": layerConfig["activation"], "weights": createRandomizedWeights(currentNumInputs*outputSize), "biases": createRandomizedWeights(currentNumInputs*outputSize) }

				self.layers.append(layerState)
				currentNumInputs = outputSize
		else:
			for i in range(0, len(stateJson["layers"])):
				self.layers.append(stateJson["layers"][i])

	def getJson(self):
		return { "name": "LinearMotorController", "layers": self.layers }

	def serialize(self):
		return json.dumps(getJson())

	# Returns list of (layerIndex, weightIndex, key)
	def getWeightIndices(self, numParametersRatio):
		numParametersToChange = int(numParametersRatio * 2*self.getNumWeights())

		indices = list(range(0, 2*self.getNumWeights()))
		random.shuffle(indices)
		layerWeightIndices = []
		for i in indices[:numParametersToChange]:
			layerWeightIndices.append(self.transformWeightIndex(i))
		return layerWeightIndices

	# Takes weightIndex into all weights independent of layer and return a tupple (layerIndex, weightIndexIntoLayerWeights)
	def transformWeightIndex(self, weightIndex):
		weightStart = 0
		for key in ("weights", "biases"):
			for i in range(0, len(self.layers)):
				l = self.layers[i]
				if weightIndex >= weightStart and weightIndex < weightStart + len(l["weights"]):
					return (i, weightIndex - weightStart, key)
				weightStart += len(l["weights"])

	def getNumWeights(self):
		num = 0
		for l in self.layers:
			num += len(l["weights"])
		return num

	def crossover(self, partnerCreature, configJson):
		numWeightsToChangeRatio = self.pickRandomNumberFromRange(configJson["numParameterChangedRatioRange"], "-")
		changeRatio = self.pickRandomNumberFromRange(configJson["changeRatioRange"], "-")

		for lw in self.getWeightIndices(numWeightsToChangeRatio):
			layerIndex = lw[0]
			weightIndex = lw[1]
			key = lw[2]
			delta = partnerCreature.motorController.layers[layerIndex][key][weightIndex] - self.layers[layerIndex][key][weightIndex]
			self.layers[layerIndex][key][weightIndex] += changeRatio * delta

	def pickRandomNumberFromRange(self, rangeStr, seperator):
		rangeNumeric = rangeStr.split(seperator)
		return random.uniform(float(rangeNumeric[0]), float(rangeNumeric[1]))

	def mutate(self, configJson):
		numWeightsToChangeRatio = self.pickRandomNumberFromRange(configJson["numParameterChangedRatioRange"], "-")

		offset = self.pickRandomNumberFromRange(configJson["offsetRange"], ";")
		offset = math.pow(offset, int(configJson["offsetExponent"]))
		if "randomizeSign" in configJson and configJson["randomizeSign"] == "yes" and random.random() < .5:
			offset = offset * (-1);

		for lw in self.getWeightIndices(numWeightsToChangeRatio):
			layerIndex = lw[0]
			weightIndex = lw[1]
			key = lw[2]

			self.layers[layerIndex][key][weightIndex] += offset