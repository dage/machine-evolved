#include "CreatureBase.h"

#include <algorithm>
#include <cmath>

namespace {
float wrapAngle(float value) {
	if (!std::isfinite(value))
		return 0.f;
	return std::remainder(value, 2.f * static_cast<float>(PI));
}
}

CreatureBase::CreatureBase(
	BulletInterface* bullet,
	btVector3 position,
	pt::ptree jsonObject,
	float motorMaxForce,
	float motorTargetVelocityLimit,
	bool v2Physics,
	int controlRateHz)
{
	this->motorTargetVelocityLimit = motorTargetVelocityLimit;
	this->v2Physics = v2Physics;
	this->controlRateHz = controlRateHz;
	// Structure:
	structure = new CreatureStructure(jsonObject.get_child("structure"));

	// Physics:
	bulletCreature = new BulletCreature(bullet, structure, position, motorMaxForce);

	//printf("inputs=%i, outputs=%i\n", structure->getNumInputs(), structure->getNumOutputs());

	const pt::ptree& controller = jsonObject.get_child("motorController");
	commandMode = controller.get<std::string>("commandMode", "target-velocity-v1");
	if (commandMode != "target-velocity-v1" && commandMode != "target-angle-servo-v1")
		throw std::runtime_error("Unknown motor command mode: " + commandMode);
	if (commandMode == "target-angle-servo-v1" && !v2Physics)
		throw std::runtime_error("target-angle-servo-v1 requires machine-evolved-bullet-v2");
	servoAngleRange = controller.get<float>("servo.targetAngleRangeRadians", 0.9f * static_cast<float>(PI));
	servoKp = controller.get<float>("servo.kp", 10.f);
	servoKd = controller.get<float>("servo.kd", 0.75f);
	settlingTicks = static_cast<int>(controller.get<float>("servo.settlingSeconds", 1.f) * controlRateHz + 0.5f);
	rampTicks = static_cast<int>(controller.get<float>("servo.rampSeconds", 1.f) * controlRateHz + 0.5f);
	motorController = new LinearMotorController(structure->getNumInputs(), structure->getNumOutputs(), controller);
	for (const auto motor : bulletCreature->getMotors())
		previousMotorPositions.push_back(motor->m_currentPosition);
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
	auto state = bulletCreature->getState(numTicks, controlRateHz);
	std::vector<float> outputs = motorController->getMotorForces(state);
	auto motors = bulletCreature->getMotors();

#ifdef _DEBUG
	if (motors.size() + structure->numFeedbacks != outputs.size())
		throw "Malformed motor control. The number of neural net outputs doesn't match the number of motors.";
#endif // _DEBUG

	for (int i = 0; i < motors.size(); i++) {
		btRotationalLimitMotor* motor = motors[i];
		float targetVelocity = outputs[i];
		if (commandMode == "target-angle-servo-v1") {
			const float currentPosition = motor->m_currentPosition;
			const float delta = wrapAngle(currentPosition - previousMotorPositions[i]);
			const float relativeVelocity = delta * controlRateHz;
			previousMotorPositions[i] = std::isfinite(currentPosition) ? currentPosition : 0.f;

			const float normalizedOutput = std::isfinite(outputs[i])
				? std::max(-1.f, std::min(1.f, outputs[i]))
				: 0.f;
			const float targetAngle = normalizedOutput * servoAngleRange;
			const float error = wrapAngle(targetAngle - currentPosition);
			targetVelocity = servoKp * error - servoKd * relativeVelocity;

			const int activeTick = numTicks - settlingTicks;
			if (activeTick <= 0)
				targetVelocity = 0.f;
			else if (rampTicks > 0 && activeTick < rampTicks) {
				const float progress = static_cast<float>(activeTick) / rampTicks;
				const float smoothstep = progress * progress * (3.f - 2.f * progress);
				targetVelocity *= smoothstep;
			}
		}
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
