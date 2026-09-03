#pragma once

#include "BulletInterface.h"
#include "IMotorController.h"
#include "LinearMotorController.h"
#include "BulletCreature.h"
#include "CreatureStructure.h"

#include <boost/property_tree/ptree.hpp>
#include <boost/property_tree/json_parser.hpp>

#include <string>
#include <vector>

namespace pt = boost::property_tree;

/**
 * A UE4-independent base class for the Creature
 */
class CreatureBase
{
public:
	struct CapsulePose {
		std::string id;
		float innerHeight;
		float radius;
		btVector3 position;
		btQuaternion rotation;
	};

	CreatureBase(
		BulletInterface* bullet,
		btVector3 position,
		pt::ptree jsonObject,
		float motorMaxForce = 2000.f,
		float motorTargetVelocityLimit = 0.f,
		bool v2Physics = false,
		int controlRateHz = 60);
	~CreatureBase();

	btVector3 getCenterOfMassPosition();
	std::vector<CapsulePose> getCapsulePoses();
	void tick();
	void terminate();

protected:
	IMotorController* motorController;
	BulletCreature* bulletCreature;
	CreatureStructure* structure;

	int numTicks = 0;

private:
	void applyMotorForces();
	float motorTargetVelocityLimit = 0.f;
	bool v2Physics = false;
	int controlRateHz = 60;
	std::string commandMode = "target-velocity-v1";
	float servoAngleRange = 0.9f * static_cast<float>(PI);
	float servoKp = 10.f;
	float servoKd = 0.75f;
	int settlingTicks = 0;
	int rampTicks = 0;
	std::vector<float> previousMotorPositions;
};
