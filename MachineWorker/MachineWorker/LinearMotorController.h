#pragma once

#include <ctime>
#include <ratio>
#include <chrono>

#include "IMotorController.h"

#include <boost/property_tree/ptree.hpp>
#include <boost/property_tree/json_parser.hpp>

namespace pt = boost::property_tree;

/**
 * 
 */
class LinearMotorController : public IMotorController
{
public:
	LinearMotorController(int numInputs, int numOutputs, pt::ptree serialized);
	~LinearMotorController();

	struct LAYER {
		std::string activation;
		std::vector<float> weights;
		std::vector<float> biases;
	};

	std::vector<float> getMotorForces(const std::vector<float> creatureState);

private:
	int numInputs;
	int numOutputs;

	std::vector<float> multiplyMatrix(const std::vector<float> inputVector, const std::vector<float> matrix, const std::vector<float> biases, const std::string activation);

	double getNanoSeconds();
	//static int profilingNumAdded;
	//static double profilingDeltaTimeAccumulated;

	std::vector<LAYER> layers;
};
