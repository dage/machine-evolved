#pragma once

#include <boost/property_tree/ptree.hpp>
#include <boost/property_tree/json_parser.hpp>

#include "BulletInterface.h"	// only included to ease internal linear algebra, never exposed
#include <vector>
#include <string>
#include <sstream>

namespace pt = boost::property_tree;

/**
 * This is a data object defining the structure of the creature. 
   It is light weight and is independent of both Unreal Engine and Bullet physics engine.
   The implementation in C++ must exactly match the python implementation.
 */
class CreatureStructure
{
public:
	struct CAPSULE {
		std::string id;
		float innerHeight;
		float radius;
		float positionX;
		float positionY;
		float positionZ;
		float quaternionX;
		float quaternionY;
		float quaternionZ;
		float quaternionW;
		pt::ptree constraint;
	};

	struct INPUTS {
		bool rootOrientationX;
		bool rootOrientationY;
		bool rootOrientationZ;
		bool rootOrientationW;
		bool zPosition;
		bool velocityX;
		bool velocityY;
		bool velocityZ;
		bool oscillators;
		bool capsulePositionX;
		bool capsulePositionY;
		bool capsulePositionZ;
		bool capsuleVelocityX;
		bool capsuleVelocityY;
		bool capsuleVelocityZ;
		bool capsuleAngularVelocityX;
		bool capsuleAngularVelocityY;
		bool capsuleAngularVelocityZ;
		bool motorAngleX;
		bool motorAngleY;
		bool motorAngleZ;
		bool feedbacks;
	};

	CreatureStructure(pt::ptree serialized);
	~CreatureStructure();

	void addCapsule(CAPSULE* capsule);
	std::vector<CAPSULE*> getCapsules();
	CAPSULE* getCapsule(std::string id);

	int getNumInputs();		// Returns the number of floating point numbers expected for the creature state
	int getNumOutputs();		// Returns the number of motors expected for the creature
	
	int numFeedbacks = 0;
	float oscillatorStart;
	float oscillatorMultiplier;
	int oscillatorCount;
	INPUTS inputs;

private:
	std::vector<CAPSULE*> capsules;
};
