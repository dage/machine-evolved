#include "LinearMotorController.h"

LinearMotorController::LinearMotorController(int numInputs, int numOutputs, pt::ptree serialized)
{
	this->numInputs = numInputs;
	this->numOutputs = numOutputs;

	int layersIndex = 0;
	auto layersPtree = serialized.get_child("layers");
	layers = std::vector<LAYER>(layersPtree.size());
	for (pt::ptree::value_type &layer : layersPtree) {
		auto weightsPtree = layer.second.get_child("weights");
		std::vector<float> weights(weightsPtree.size());
		int weightIndex = 0;
		for (pt::ptree::value_type &weight : weightsPtree) {
			weights[weightIndex++] = weight.second.get_value<float>();
		}

		auto biasesPtree = layer.second.get_child("biases");
		std::vector<float> biases(biasesPtree.size());
		int biasIndex = 0;
		for (pt::ptree::value_type &bias: biasesPtree) {
			biases[biasIndex++] = bias.second.get_value<float>();
		}

		LAYER layerStruct = {
			layer.second.get<std::string>("activation"),
			weights,
			biases
		};
		layers[layersIndex++] = layerStruct;
	}
}

LinearMotorController::~LinearMotorController() {
}

// Multiplies inputVector with matrix and returns an outputvector (size found from size of matrix)
std::vector<float> LinearMotorController::multiplyMatrix(const std::vector<float> inputVector, const std::vector<float> matrix, const std::vector<float> biases, std::string activation) {
#ifdef _DEBUG
	if (matrix.size() % inputVector.size() != 0)
		throw "Malformed vector matrix multiplication. Matrix is of wrong size.";
#endif // _DEBUG

	int outputSize = matrix.size() / inputVector.size();
	int inputSize = inputVector.size();
	std::vector<float> outputVector = std::vector<float>(outputSize);


	// Manually perform vector matrix multiplication
	for (int i = 0; i < outputSize; i++) {
		outputVector[i] = 0.;
		for (int j = 0; j < inputSize; j++) {
			outputVector[i] += inputVector[j] * matrix[i*inputSize + j] + biases[i*inputSize + j];
		}
	}

	// Apply activation function
	if (activation == "tanh")
		for (int i = 0; i < outputSize; i++)
			outputVector[i] = tanh(outputVector[i]);

	return outputVector;
}

double LinearMotorController::getNanoSeconds() {
	auto now = std::chrono::system_clock::now().time_since_epoch();
	return std::chrono::duration_cast<std::chrono::nanoseconds>(now).count();
}

//int LinearMotorController::profilingNumAdded = 0;
//double LinearMotorController::profilingDeltaTimeAccumulated = 0;

std::vector<float> LinearMotorController::getMotorForces(const std::vector<float> creatureState) {
	//double startTime = getNanoSeconds();

	auto currentValue = creatureState;
	for (auto layer : layers) {
		currentValue = multiplyMatrix(currentValue, layer.weights, layer.biases, layer.activation);
	}

	//double endTime = getNanoSeconds();
	//profilingDeltaTimeAccumulated += endTime - startTime;
	//profilingNumAdded++;
	//if (profilingNumAdded % 100000 == 0) {
	//	printf("%f nanoseconds spent.\n", profilingDeltaTimeAccumulated/profilingNumAdded);
	//}

#ifdef _DEBUG
	if (currentValue.size() != numOutputs)
		throw "Malformed neural net transformation. Output size does not match!";
#endif // _DEBUG

	return currentValue;
}
