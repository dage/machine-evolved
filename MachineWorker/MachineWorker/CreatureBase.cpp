#include "CreatureBase.h"

#include <algorithm>

CreatureBase::CreatureBase(BulletInterface* bullet, btVector3 position, pt::ptree jsonObject, float motorMaxForce, float motorTargetVelocityLimit)
{
	this->motorTargetVelocityLimit = motorTargetVelocityLimit;
	// Structure:
	structure = new CreatureStructure(jsonObject.get_child("structure"));

	// Physics:
	bulletCreature = new BulletCreature(bullet, structure, position, motorMaxForce);

	//printf("inputs=%i, outputs=%i\n", structure->getNumInputs(), structure->getNumOutputs());

	motorController = new LinearMotorController(structure->getNumInputs(), structure->getNumOutputs(), jsonObject.get_child("motorController"));
}

CreatureBase::~CreatureBase()
{
	delete structure;
	delete motorController;
	delete bulletCreature;
}

void CreatureBase::terminate() {
	bulletCreature->terminate();
}

btVector3 CreatureBase::getCenterOfMassPosition() {
	return bulletCreature->getCenterOfMassPosition();
}

std::vector<CreatureBase::CapsulePose> CreatureBase::getCapsulePoses() {
	auto definitions = structure->getCapsules();
	auto bodies = bulletCreature->getCapsules();
	if (definitions.size() != bodies.size())
		throw std::runtime_error("Creature capsule definitions and Bullet bodies do not match.");

	std::vector<CapsulePose> poses;
	poses.reserve(definitions.size());
	for (std::size_t index = 0; index < definitions.size(); ++index) {
		const btTransform& transform = bodies[index]->getWorldTransform();
		poses.push_back(CapsulePose{
			definitions[index]->id,
			definitions[index]->innerHeight,
			definitions[index]->radius,
			transform.getOrigin(),
			transform.getRotation(),
		});
	}
	return poses;
}

void CreatureBase::tick() {
	numTicks++;
	applyMotorForces();
}

void CreatureBase::applyMotorForces() {
	auto state = bulletCreature->getState(numTicks);
	std::vector<float> outputs = motorController->getMotorForces(state);
	auto motors = bulletCreature->getMotors();

#ifdef _DEBUG
	if (motors.size() + structure->numFeedbacks != motorForces.size())
		throw "Malformed motor control. The number of neural net outputs doesn't match the number of motors.";
#endif // _DEBUG

	for (int i = 0; i < motors.size(); i++) {
		btRotationalLimitMotor* motor = motors[i];
		float targetVelocity = outputs[i];
		if (motorTargetVelocityLimit > 0.f)
			targetVelocity = std::max(-motorTargetVelocityLimit, std::min(motorTargetVelocityLimit, targetVelocity));
		motor->m_targetVelocity = targetVelocity;
	}

	std::vector<float> updatedFeedbacks;
	for (int i = 0; i < structure->numFeedbacks; i++) {
		float value = outputs[outputs.size() - structure->numFeedbacks + i];
		updatedFeedbacks.push_back(value);
	}
	bulletCreature->setFeedbacks(updatedFeedbacks);
}
