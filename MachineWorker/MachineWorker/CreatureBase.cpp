#include "CreatureBase.h"

CreatureBase::CreatureBase(BulletInterface* bullet, btVector3 position, pt::ptree jsonObject)
{
	// Structure:
	structure = new CreatureStructure(jsonObject.get_child("structure"));

	// Physics:
	bulletCreature = new BulletCreature(bullet, structure, position);

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
		motor->m_targetVelocity = outputs[i];
	}

	std::vector<float> updatedFeedbacks;
	for (int i = 0; i < structure->numFeedbacks; i++) {
		float value = outputs[outputs.size() - structure->numFeedbacks + i];
		updatedFeedbacks.push_back(value);
	}
	bulletCreature->setFeedbacks(updatedFeedbacks);
}
