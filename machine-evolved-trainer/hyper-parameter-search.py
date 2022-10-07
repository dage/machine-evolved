import argparse
import json
import os
import itertools
import random
import statistics
from CreatureStructure import CreatureStructure
from Creature import Creature
from pprint import pprint

def execute():
	def createDataPermutation(baseConfig, numInputs):
		generator = baseConfig["structure"]["generator"]
		inputs = generator["inputs"]
		
		outputLayer = { "activation": "linear" }
		trials = 0
		currentNumInputs = 0
		currentNumOutputs = 0
		defaultHiddenNeurons = 0

		oscillatorStartValues = [0.1, 0.25, 0.5, 1.0, 2.0]
		oscillatorCountValues = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
		oscillatorMultiplierValues = [2, 4, 1.5, 1.1]

		while trials < 1000000 and numInputs != currentNumInputs:
			generator["oscillators"]["start"] = random.choice(oscillatorStartValues)
			generator["oscillators"]["multiplier"] = random.choice(oscillatorMultiplierValues)
			generator["oscillators"]["count"] = random.choice(oscillatorCountValues)
			for key in inputs:
				if key == "feedbacks":
					inputs[key] = 0		# disable feedbacks for now
				else:
					inputs[key] = 0 if random.random() < 0.5 else 1

			creature = Creature(None, generator)

			currentNumInputs = creature.structure.getNumInputs()
			currentNumOutputs = creature.structure.getNumOutputs()
			defaultHiddenNeurons = round(statistics.median(range(min(currentNumInputs, currentNumOutputs), max(currentNumInputs, currentNumOutputs)))) if currentNumOutputs != currentNumInputs else currentNumInputs

			if(random.random() < 0.5):
				generator["motorController"] = { "layers": [{ "activation": "tanh", "neurons": defaultHiddenNeurons }, outputLayer ]}
			else:
				generator["motorController"] = { "layers": [ outputLayer ]}

			trials += 1

		print(str(trials) + " trials used to find " + str(currentNumInputs) + " number of inputs and " + str(currentNumOutputs) + " number of outputs (default hidden neurons=" + str(defaultHiddenNeurons) + ")")

		return creature.structure.getJson()

	parser = argparse.ArgumentParser(description='Machine Evolved hyper parameter search.')
	parser.add_argument('baseConfig', metavar='baseConfig', type=argparse.FileType('r'), 
					help='Filename of master json file for configuring the simulation.')
	parser.add_argument('numInputs', metavar='numInputs', type=int,
					help='The number of inputs that will be used for the model.')
	parser.add_argument('maxEvaluations', metavar='maxEvaluations', type=int,
					help='The maximum number of fitness evaluations performed by each of the experiments.')
	parser.add_argument('numExperiments', metavar='numExperiments', type=int,
					help='The number of experiments that will be added to batch file.')

	args = parser.parse_args()
	configFilename = args.baseConfig.name
	numInputs = args.numInputs
	maxEvaluations = args.maxEvaluations
	numExperiments = args.numExperiments
	directoryName =  configFilename[:configFilename.rfind(".json")] + "-" + str(numInputs) + "-" + str(maxEvaluations)

	with open(configFilename) as file:
		data = json.load(file)
	
	if os.path.exists(directoryName):
		print("directory {} already exists.".format(directoryName))
	else:
		os.makedirs(directoryName)
		print("directory {} created!".format(directoryName))

	currentDir = os.path.dirname(os.path.realpath("Trainer.py"))
	inputs = data["structure"]["generator"]["inputs"]
	oscillators = data["structure"]["generator"]["oscillators"]

	with open(directoryName + "\\run.bat", "w") as script:
		index = 0
		while index < numExperiments:
			permutation = createDataPermutation(data, numInputs)

			filename = str(index) + ".json"

			if os.path.isfile(directoryName + "\\" + filename):
				print("File {} already exists. Skipping...".format(directoryName + "\\" + filename))
			else:
				fileContent = json.dumps(data)
				with open(directoryName + "\\" + filename, "w") as outputFile:
					outputFile.write(fileContent)

				script.write("py " + currentDir + "\\Trainer.py --terminate-evaluations " + str(maxEvaluations) + " --terminate-stall-evaluations " + str(int(maxEvaluations/5)) + " " + filename + " --result-filename results.csv --reset-fitness\n")
				print("{}/{} ==> {}".format(index+1, numExperiments, filename))

			index += 1

if __name__ == "__main__":
	execute()