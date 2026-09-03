#pragma once

#include <boost/property_tree/ptree.hpp>

#include <vector>

#include "btBulletDynamicsCommon.h"

#ifndef PI
const double PI = 3.141592653589793;
#endif // !PI

namespace pt = boost::property_tree;
/**
* Interface to and Bullet Game Physics engine.
*/
class BulletInterface
{
public:
	BulletInterface();
	~BulletInterface();

	void init();
	void configure(pt::ptree config);
	void destroy();
	void tick(float);
	bool usesV2Physics() const;
	int getControlRateHz() const;
	int getPhysicsRateHz() const;

	btRigidBody* addCapsule(float innerHeight, float radius, btVector3 position, btQuaternion rotation);
	btGeneric6DofConstraint* addConstraint(float offsetA, float offsetB, btRigidBody* bodyA, btRigidBody* bodyB, pt::ptree config);
	void removeCapsule(btRigidBody* capsule);
	void removeConstraint(btTypedConstraint* constraint);

protected:
	bool isInitialized = false;

private:
	btBroadphaseInterface* broadphase;
	btDefaultCollisionConfiguration* collisionConfiguration;
	btCollisionDispatcher* dispatcher;
	btSequentialImpulseConstraintSolver* solver;
	btDiscreteDynamicsWorld* dynamicsWorld;
	btCollisionShape* groundShape;
	btDefaultMotionState* groundMotionState;
	btRigidBody* groundRigidBody;
	float capsuleFriction = 0.5f;
	float capsuleRollingFriction = 0.f;
	float capsuleSpinningFriction = 0.f;
	float capsuleRestitution = 0.f;
	float capsuleLinearDamping = 0.f;
	float capsuleAngularDamping = 0.f;
	float capsuleMassScale = 0.0001f;
	bool v2Physics = false;
	bool capsuleCcdEnabled = false;
	float ccdMotionThresholdRadiusRatio = 0.25f;
	float ccdSweptSphereRadiusRatio = 0.2f;
	int controlRateHz = 60;
	int physicsRateHz = 60;
	int physicsSubsteps = 1;

	std::vector<float> getRange(std::string range, std::string seperator = ";");
};
