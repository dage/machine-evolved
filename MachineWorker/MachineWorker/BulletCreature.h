#pragma once

#include <math.h>

#include "BulletInterface.h"
#include "CreatureStructure.h"
#include <vector>

/**
 * Defines a create in Bullet physics engine.
 */
class BulletCreature
{
public:
	struct MotorWithDimension {
		char dimension;
		btRotationalLimitMotor* motor;
	};

	BulletCreature(BulletInterface* bullet, CreatureStructure* structure, btVector3 position);
	~BulletCreature();

	CreatureStructure* structure;

	std::vector<btRigidBody*> getCapsules();		// For rendering
	std::vector<btRotationalLimitMotor*> getMotors();
	std::vector<float> getState(int tick);
	btVector3 getCenterOfMassPosition();

	void setFeedbacks(std::vector<float> newFeedbackValues);

	void terminate();

private:
	void createMotors(btGeneric6DofConstraint* constraint, bool xRotationEnabled, bool yRotationEnabled, bool zRotationEnabled);

	btRigidBody* root;
	std::vector<float> feedbacks;
	std::vector<MotorWithDimension> motors;
	std::vector<btRigidBody*> capsules;
	std::vector<btGeneric6DofConstraint*> constraints;
	BulletInterface* bulletInterface;

	//std::vector<float> stateCalibrationWeightSum;
	//int stateCalibrationNumAdded = 0;
};
