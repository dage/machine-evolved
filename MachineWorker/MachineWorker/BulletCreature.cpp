#include "BulletCreature.h"
#include <map>

BulletCreature::BulletCreature(BulletInterface* bullet, CreatureStructure* creatureStructure, btVector3 position)
{
	std::map<CreatureStructure::CAPSULE*, btRigidBody*> constraintsMap;

	structure = creatureStructure;

	feedbacks.assign(structure->numFeedbacks, 0);		// Initialize feedbacks with zeroes

	// Create bullet rigid bodies
	for (CreatureStructure::CAPSULE* capsule : creatureStructure->getCapsules()) {
		btRigidBody* bulletCapsule = bullet->addCapsule(capsule->innerHeight, capsule->radius, btVector3(capsule->positionX + position.x(), capsule->positionY + position.y(), capsule->positionZ + position.z()), btQuaternion(capsule->quaternionX, capsule->quaternionY, capsule->quaternionZ, capsule->quaternionW));
		capsules.push_back(bulletCapsule);

		constraintsMap[capsule] = bulletCapsule;
	}

	// Create constraints
	for (CreatureStructure::CAPSULE* capsule : creatureStructure->getCapsules()) {
		if (!capsule->constraint.empty()) {
			//printf("INSIDE! parentId=%s\n", capsule->constraint.get<std::string>("parentId"));
			CreatureStructure::CAPSULE* parentCapsule = creatureStructure->getCapsule(capsule->constraint.get<std::string>("parentId"));
			btGeneric6DofConstraint* constraint = bullet->addConstraint(
				.5*parentCapsule->innerHeight + parentCapsule->radius,
				-.5*capsule->innerHeight - capsule->radius,
				constraintsMap[parentCapsule],
				constraintsMap[capsule],
				capsule->constraint);
			constraints.push_back(constraint);

			createMotors(constraint, capsule->constraint.count("x-rotation") == 1, capsule->constraint.count("y-rotation") == 1, capsule->constraint.count("z-rotation") == 1);
		}
		else
			root = constraintsMap[capsule];
	}
	bulletInterface = bullet;
}

BulletCreature::~BulletCreature()
{
}

void BulletCreature::createMotors(btGeneric6DofConstraint* constraint, bool xRotationEnabled, bool yRotationEnabled, bool zRotationEnabled) {
	// http://bulletphysics.org/Bullet/phpBB3/viewtopic.php?t=8408
	
	btRotationalLimitMotor* motor;
	std::vector<int> indices;
	if (xRotationEnabled) indices.push_back(0);
	if (yRotationEnabled) indices.push_back(1);
	if (zRotationEnabled) indices.push_back(2);

	for (int i : indices) {
		motor = constraint->getRotationalLimitMotor(i);

		motor->m_bounce = 0.f;
		motor->m_normalCFM = 0.f;
		motor->m_stopCFM = 0.f;

		motor->m_maxMotorForce = 2000.f;		// 2017-10-12 v1: 5000.f
		motor->m_maxLimitForce = 100000.f;
		motor->m_enableMotor = true;
		motors.push_back(MotorWithDimension{ i==0?'x':i==1?'y':'z', motor });
	}
}

std::vector<btRotationalLimitMotor*> BulletCreature::getMotors() {
	std::vector<btRotationalLimitMotor*> onlyMotors;

	for (auto motorWithDimension : motors)
		onlyMotors.push_back(motorWithDimension.motor);

	return onlyMotors;
}

std::vector<btRigidBody*> BulletCreature::getCapsules() {
	return capsules;	// TODO: Use shallow clone instead maybe
}

void BulletCreature::setFeedbacks(std::vector<float> newFeedbackValues) {
	feedbacks = newFeedbackValues;
}

btVector3 BulletCreature::getCenterOfMassPosition() {
	float massAccumulated = 0;
	btVector3 positionAccumulated = btVector3(0, 0, 0);

	for (auto capsule : capsules) {
		float mass = 1. / capsule->getInvMass();
		massAccumulated += mass;
		positionAccumulated += mass*capsule->getCenterOfMassPosition();
	}
	positionAccumulated /= massAccumulated;	
	
	return positionAccumulated;
}

void BulletCreature::terminate() {
	//for (auto motor : motors)
	//	delete motor;

	for (auto constraint : constraints) {
		bulletInterface->removeConstraint(constraint);
	}

	for (auto capsule : capsules) {
		bulletInterface->removeCapsule(capsule);
	}

	//float length = 0;
	//for (int i = 0; i < stateCalibrationWeightSum.size(); i++) {
	//	float normalized = stateCalibrationWeightSum[i] / stateCalibrationNumAdded;
	//	printf("%i: %f, ", i, normalized);
	//	length += normalized*normalized;
	//}
	//length = sqrt(length);
	//printf("length = %f, samples=%i \n", length, stateCalibrationNumAdded);
}

std::vector<float> BulletCreature::getState(int tick) {
	// Have been manually edited (so approximately match sin/cos) so that the different state elements are pretty close together, based on a simple in-efficient creature. TODO: Revisit this later
	const float CALIBRATION_Z_POSITION = 5; // 50.;
	const float CALIBRATION_VELOCITY = 7; //  50.;
	const float CALIBRATION_CAPSULE_POSITION = 2; // 10.;
	const float CALIBRATION_CAPSULE_TRANSLATION_VELOCITY = 7; // 200.;
	const float CALIBRATION_CAPSULE_ANGULAR_VELOCITY = 1; //  5.;
	const float CALIBRATION_CONSTRAINT_ANGLE = 3; // 10.;

	std::vector<float> state(structure->getNumInputs());
	int stateIndex = 0;

	float totalCapsuleLength = 0;
	auto capsulesDefinition = structure->getCapsules();
	for (int i = 0; i < capsulesDefinition.size(); i++)
		totalCapsuleLength += capsulesDefinition[i]->innerHeight + capsulesDefinition[i]->radius;

	float massAccumulated = 0;
	btVector3 centerOfCreaturePosition = btVector3(0, 0, 0);
	btVector3 centerOfCreatureVelocity = btVector3(0, 0, 0);
	btVector3 velocityAccumulated = btVector3(0, 0, 0);

	// For whole creature:
	btQuaternion orientation = root->getOrientation();
	if(structure->inputs.rootOrientationX) state[stateIndex++] = orientation.getX();
	if(structure->inputs.rootOrientationY) state[stateIndex++] = orientation.getY();
	if(structure->inputs.rootOrientationZ) state[stateIndex++] = orientation.getZ();
	if(structure->inputs.rootOrientationW) state[stateIndex++] = orientation.getW();

	for (auto capsule : capsules) {
		float mass = 1. / capsule->getInvMass();
		massAccumulated += mass;
		velocityAccumulated += mass*capsule->getLinearVelocity();	// TODO: Check if getInterpolationLinearVelocity() is an alternative
	}
	centerOfCreaturePosition = getCenterOfMassPosition();
	float zPosition = centerOfCreaturePosition.z() / totalCapsuleLength;	// normalize

	velocityAccumulated /= massAccumulated;
	centerOfCreatureVelocity = velocityAccumulated;
	velocityAccumulated /= totalCapsuleLength;

	if (structure->inputs.zPosition) state[stateIndex++] = zPosition * CALIBRATION_Z_POSITION;
	if (structure->inputs.velocityX) state[stateIndex++] = velocityAccumulated.x()*CALIBRATION_VELOCITY;
	if (structure->inputs.velocityY) state[stateIndex++] = velocityAccumulated.y()*CALIBRATION_VELOCITY;
	if (structure->inputs.velocityZ) state[stateIndex++] = velocityAccumulated.z()*CALIBRATION_VELOCITY;

	if (structure->inputs.oscillators) {
		float time = 1. / 60. * tick;
		float current = structure->oscillatorStart;
		for (int oscillatorIndex = 0; oscillatorIndex < structure->oscillatorCount; oscillatorIndex++) {
			float oscillator = sin(current * time);
			state[stateIndex++] = oscillator;

			current *= structure->oscillatorMultiplier;
		}
	}

	// For per-capsule:
	for (auto capsule : capsules) {
		btVector3 relativePosition = capsule->getCenterOfMassPosition() - centerOfCreaturePosition;
		btVector3 relativePositionVelocity = capsule->getLinearVelocity() - centerOfCreatureVelocity;
		btVector3 relativeAngularVelocity = capsule->getAngularVelocity();

		relativePosition /= totalCapsuleLength;
		relativeAngularVelocity /= PI;
		relativePositionVelocity /= totalCapsuleLength;

		if (structure->inputs.capsulePositionX) state[stateIndex++] = relativePosition.x()*CALIBRATION_CAPSULE_POSITION;
		if (structure->inputs.capsulePositionY) state[stateIndex++] = relativePosition.y()*CALIBRATION_CAPSULE_POSITION;
		if (structure->inputs.capsulePositionZ) state[stateIndex++] = relativePosition.z()*CALIBRATION_CAPSULE_POSITION;
		if (structure->inputs.capsuleVelocityX) state[stateIndex++] = relativePositionVelocity.x()*CALIBRATION_CAPSULE_TRANSLATION_VELOCITY;
		if (structure->inputs.capsuleVelocityY) state[stateIndex++] = relativePositionVelocity.y()*CALIBRATION_CAPSULE_TRANSLATION_VELOCITY;
		if (structure->inputs.capsuleVelocityZ) state[stateIndex++] = relativePositionVelocity.z()*CALIBRATION_CAPSULE_TRANSLATION_VELOCITY;
		if (structure->inputs.capsuleAngularVelocityX) state[stateIndex++] = relativeAngularVelocity.x()*CALIBRATION_CAPSULE_ANGULAR_VELOCITY;
		if (structure->inputs.capsuleAngularVelocityY) state[stateIndex++] = relativeAngularVelocity.y()*CALIBRATION_CAPSULE_ANGULAR_VELOCITY;
		if (structure->inputs.capsuleAngularVelocityZ) state[stateIndex++] = relativeAngularVelocity.z()*CALIBRATION_CAPSULE_ANGULAR_VELOCITY;

		//UE_LOG(LogTemp, Warning, TEXT("   CAPSULE: x=%f, y=%f, z=%f, dx=%f, dy=%f, dz=%f, angle dx=%f, angle dy=%f, angle dz=%f"), relativePosition.x(), relativePosition.y(), relativePosition.z(), relativePositionVelocity.x(), relativePositionVelocity.y(), relativePositionVelocity.z(), relativeAngularVelocity.x(), relativeAngularVelocity.y(), relativeAngularVelocity.z());
	}
	
	// For per-motor:
	for (auto motorWithDimension : motors) {
		if ((motorWithDimension.dimension == 'x' && structure->inputs.motorAngleX) ||
			(motorWithDimension.dimension == 'y' && structure->inputs.motorAngleY) ||
			(motorWithDimension.dimension == 'z' && structure->inputs.motorAngleZ)) {
			float angularPosition = motorWithDimension.motor->m_currentPosition / PI;
			state[stateIndex++] = angularPosition*CALIBRATION_CONSTRAINT_ANGLE;
		}
	}

	// Add feedbacks:
	if (structure->inputs.feedbacks) {
		for (auto feedbackValue : feedbacks) {
			state[stateIndex++] = feedbackValue;
		}
	}

	// Temporary code for callibrating the state
	//if (stateCalibrationWeightSum.size() == 0) {
	//	stateCalibrationWeightSum = std::vector<float>(state.size(), 0);
	//}
	//for (int i = 0; i < state.size(); i++) {
	//	stateCalibrationWeightSum[i] += state[i] * state[i];
	//}
	//stateCalibrationNumAdded++;

	return state;
}
