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
	void destroy();
	void tick(float);

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

	std::vector<float> getRange(std::string range, std::string seperator = ";");
};
