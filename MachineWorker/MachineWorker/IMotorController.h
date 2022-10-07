#pragma once

#include <vector>

/**
 * This is the base class of motor controls. It maps the creature state to outputs for the motors.
 *
 * TODO: Missing the whole architecture picture. Need to think more how to organize while keeping final tensorflow inference in mind.
 */
class IMotorController
{
public:
	IMotorController();
	virtual ~IMotorController();

	virtual std::vector<float> getMotorForces(std::vector<float> creatureState) {
		throw "Not implemented";
	}
};
