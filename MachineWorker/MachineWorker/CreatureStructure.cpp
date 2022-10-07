#include "CreatureStructure.h"

// Constructor that initializes from a serialization
CreatureStructure::CreatureStructure(pt::ptree serialized) {
	numFeedbacks = serialized.get<int>("feedbacks");
	
	oscillatorStart = serialized.get<float>("oscillators.start");
	oscillatorMultiplier = serialized.get<float>("oscillators.multiplier");
	oscillatorCount = serialized.get<int>("oscillators.count");
	
	inputs.capsuleAngularVelocityX = serialized.get<int>("inputs.capsule-angular-velocity-x") == 1;
	inputs.capsuleAngularVelocityY = serialized.get<int>("inputs.capsule-angular-velocity-y") == 1;
	inputs.capsuleAngularVelocityZ = serialized.get<int>("inputs.capsule-angular-velocity-z") == 1;
	inputs.capsulePositionX = serialized.get<int>("inputs.capsule-position-x") == 1;
	inputs.capsulePositionY = serialized.get<int>("inputs.capsule-position-y") == 1;
	inputs.capsulePositionZ = serialized.get<int>("inputs.capsule-position-z") == 1;
	inputs.capsuleVelocityX = serialized.get<int>("inputs.capsule-velocity-x") == 1;
	inputs.capsuleVelocityY = serialized.get<int>("inputs.capsule-velocity-y") == 1;
	inputs.capsuleVelocityZ = serialized.get<int>("inputs.capsule-velocity-z") == 1;
	inputs.feedbacks = serialized.get<int>("inputs.feedbacks") == 1;
	inputs.motorAngleX = serialized.get<int>("inputs.motor-angle-x") == 1;
	inputs.motorAngleY = serialized.get<int>("inputs.motor-angle-y") == 1;
	inputs.motorAngleZ = serialized.get<int>("inputs.motor-angle-z") == 1;
	inputs.oscillators = serialized.get<int>("inputs.oscillators") == 1;
	inputs.rootOrientationX = serialized.get<int>("inputs.root-orientation-x") == 1;
	inputs.rootOrientationY = serialized.get<int>("inputs.root-orientation-y") == 1;
	inputs.rootOrientationZ = serialized.get<int>("inputs.root-orientation-z") == 1;
	inputs.rootOrientationW = serialized.get<int>("inputs.root-orientation-w") == 1;
	inputs.velocityX = serialized.get<int>("inputs.velocity-x") == 1;
	inputs.velocityY = serialized.get<int>("inputs.velocity-y") == 1;
	inputs.velocityZ = serialized.get<int>("inputs.velocity-z") == 1;
	inputs.zPosition = serialized.get<int>("inputs.z-position") == 1;

	for (pt::ptree::value_type &capsule : serialized.get_child("capsules")) {
		auto item = capsule.second;
		auto capsule = new CAPSULE();

		capsule->id = item.get<std::string>("id");
		capsule->innerHeight = item.get<double>("innerHeight");
		capsule->radius = item.get<double>("radius");
		capsule->positionX = item.get<double>("positionX");
		capsule->positionY = item.get<double>("positionY");
		capsule->positionZ = item.get<double>("positionZ");
		capsule->quaternionX = item.get<double>("quaternionX");
		capsule->quaternionY = item.get<double>("quaternionY");
		capsule->quaternionZ = item.get<double>("quaternionZ");
		capsule->quaternionW = item.get<double>("quaternionW");
		capsule->constraint = item.get_child("constraint");

		addCapsule(capsule);
	}
}

CreatureStructure::~CreatureStructure()
{
	for (CAPSULE* capsule : capsules)
		delete capsule;
}

int CreatureStructure::getNumInputs() {
	// Per creature:
	int numPerCreature = 0;
	numPerCreature += inputs.rootOrientationX ? 1 : 0;
	numPerCreature += inputs.rootOrientationY ? 1 : 0;
	numPerCreature += inputs.rootOrientationZ ? 1 : 0;
	numPerCreature += inputs.rootOrientationW ? 1 : 0;
	numPerCreature += inputs.zPosition ? 1 : 0;
	numPerCreature += inputs.velocityX ? 1 : 0;
	numPerCreature += inputs.velocityY ? 1 : 0;
	numPerCreature += inputs.velocityZ ? 1 : 0;
	numPerCreature += inputs.oscillators ? oscillatorCount : 0;

	// Per capsule:
	int numPerCapsule = 0;
	numPerCapsule += inputs.capsulePositionX ? 1 : 0;
	numPerCapsule += inputs.capsulePositionY ? 1 : 0;
	numPerCapsule += inputs.capsulePositionZ ? 1 : 0;
	numPerCapsule += inputs.capsuleVelocityX ? 1 : 0;
	numPerCapsule += inputs.capsuleVelocityY ? 1 : 0;
	numPerCapsule += inputs.capsuleVelocityZ ? 1 : 0;
	numPerCapsule += inputs.capsuleAngularVelocityX ? 1 : 0;
	numPerCapsule += inputs.capsuleAngularVelocityY ? 1 : 0;
	numPerCapsule += inputs.capsuleAngularVelocityZ ? 1 : 0;

	// For motors:
	int numForMotors = 0;
	for (auto capsule : capsules) {
		if (!capsule->constraint.empty()) {
			if (capsule->constraint.count("x-rotation") == 1 && inputs.motorAngleX)
				numForMotors++;
			if (capsule->constraint.count("y-rotation") == 1 && inputs.motorAngleY)
				numForMotors++;
			if (capsule->constraint.count("z-rotation") == 1 && inputs.motorAngleZ)
				numForMotors++;
		}
	}

	// For feedbacks:
	int numForFeedbacks = inputs.feedbacks ? numFeedbacks : 0;

	return numPerCreature + capsules.size() * numPerCapsule + numForMotors + numForFeedbacks;
}

int CreatureStructure::getNumOutputs() {
	int num = 0;

	for (auto capsule : capsules) {
		if (!capsule->constraint.empty()) {
			if (capsule->constraint.count("x-rotation") == 1)
				num++;
			if (capsule->constraint.count("y-rotation") == 1)
				num++;
			if (capsule->constraint.count("z-rotation") == 1)
				num++;
		}
	}

	num += numFeedbacks;

	return num;
}

std::vector<CreatureStructure::CAPSULE*> CreatureStructure::getCapsules() {
	return capsules;
}

CreatureStructure::CAPSULE* CreatureStructure::getCapsule(std::string id) {
	for (CAPSULE* capsule : capsules) {		// TODO: For optimalization, change std::vector into std::map or similar.
		if (capsule->id == id)
			return capsule;
	}
	return NULL;	// not found
}

void CreatureStructure::addCapsule(CAPSULE* capsule) {
	capsules.push_back(capsule);
}

