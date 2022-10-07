// Fill out your copyright notice in the Description page of Project Settings.

#include "BulletInterface.h"

BulletInterface::BulletInterface()
{
}

// Initializes the Bullet Game Physics engine. Adds a static ground at y=0.
void BulletInterface::init() {
	broadphase = new btDbvtBroadphase();

	collisionConfiguration = new btDefaultCollisionConfiguration();
	dispatcher = new btCollisionDispatcher(collisionConfiguration);

	solver = new btSequentialImpulseConstraintSolver;

	dynamicsWorld = new btDiscreteDynamicsWorld(dispatcher, broadphase, solver, collisionConfiguration);

	dynamicsWorld->setGravity(btVector3(0, 0, -200));

	groundShape = new btStaticPlaneShape(btVector3(0, 0, 1), 0);
	groundMotionState = new btDefaultMotionState(btTransform(btQuaternion(0, 0, 0, 1), btVector3(0, -1, 0)));
	btRigidBody::btRigidBodyConstructionInfo groundRigidBodyCI(0, groundMotionState, groundShape, btVector3(0, 0, 0));
	groundRigidBodyCI.m_friction = 4.f;
	groundRigidBody = new btRigidBody(groundRigidBodyCI);
	dynamicsWorld->addRigidBody(groundRigidBody);

	isInitialized = true;
}

void BulletInterface::removeConstraint(btTypedConstraint* constraint) {
	dynamicsWorld->removeConstraint(constraint);
	delete constraint;
}

void BulletInterface::removeCapsule(btRigidBody* capsule) {
	dynamicsWorld->removeRigidBody(capsule);
	delete capsule->getCollisionShape();
	delete capsule->getMotionState();
	delete capsule;
}

btRigidBody* BulletInterface::addCapsule(float innerHeight, float radius, btVector3 position, btQuaternion rotation) {
	btTransform transform = btTransform();
	transform.setIdentity();
	transform.setOrigin(position);
	transform.setRotation(rotation);

	btCollisionShape* fallShape = new btCapsuleShapeZ(radius, innerHeight);
	btDefaultMotionState* fallMotionState = new btDefaultMotionState(transform);
	btScalar mass = PI * radius * radius * innerHeight +	// formula for volume of a cylinder
		4 * 3 / PI * radius*radius*radius;					// formula for volume of a sphere (two half spheres at end of capsule)

	mass *= 0.0001;	// For debugging constraint problems.

	//UE_LOG(LogTemp, Warning, TEXT("Capsule with mass %f added."), mass);

	btVector3 fallInertia(0, 0, 0);
	fallShape->calculateLocalInertia(mass, fallInertia);
	btRigidBody::btRigidBodyConstructionInfo fallRigidBodyCI(mass, fallMotionState, fallShape, fallInertia);
	btRigidBody* fallRigidBody = new btRigidBody(fallRigidBodyCI);
	dynamicsWorld->addRigidBody(fallRigidBody);
	
	return fallRigidBody;
}


// Helper function to split range in format "-0.5;2" into a two element float vector with {-0.5, 2}
std::vector<float> BulletInterface::getRange(std::string range, std::string seperator) {
	std::vector<float> output = { 0, 0 };
	auto position = range.find(";");
	if (position != -1) {
		auto firstPart = range.substr(0, position);
		auto secondPart = range.substr(position+1, range.size() - position - 1);
		output[0] = stof(firstPart);
		output[1] = stof(secondPart);
	}
	return output;
}

// offsetA: Local offset in Z direction for connect point on bodyA
// offsetB: Local offset in Z direction for connect point on bodyB
btGeneric6DofConstraint* BulletInterface::addConstraint(float offsetA, float offsetB, btRigidBody* bodyA, btRigidBody* bodyB, pt::ptree config) {
	const std::vector<std::string> keys = { "x-rotation", "y-rotation", "z-rotation" };
	double lowerLimits[] = { 0, 0, 0 };
	double upperLimits[] = { 0, 0, 0 };
	int index = 0;

	for (auto key : keys) {
		std::string value = config.get<std::string>(key + ".range", "");
		auto valueSplitted = getRange(value);
		lowerLimits[index] = valueSplitted[0];
		upperLimits[index] = valueSplitted[1];
		index++;
	}

	btTransform localA;
	btTransform localB;
	localA.setIdentity(); 
	localB.setIdentity();
	localA.setOrigin(btVector3(0, 0, offsetA));
	localB.setOrigin(btVector3(0, 0, offsetB));

	btGeneric6DofConstraint* constraint = new btGeneric6DofConstraint(*bodyA, *bodyB, localA, localB, true);
	constraint->setLinearLowerLimit(btVector3(0, 0, 0));
	constraint->setLinearUpperLimit(btVector3(0, 0, 0));
	constraint->setAngularLowerLimit(btVector3(lowerLimits[0]*PI, lowerLimits[1]*PI, lowerLimits[2]*PI));
	constraint->setAngularUpperLimit(btVector3(upperLimits[0]*PI, upperLimits[1]*PI, upperLimits[2]*PI));
	dynamicsWorld->addConstraint(constraint, true);

	return constraint;
}

void BulletInterface::tick(float deltaTime) {
	if (!isInitialized)
		return;

	double frameTime = 1. / 60.;
	int timeSteps = 1;
	dynamicsWorld->stepSimulation(frameTime, timeSteps, frameTime / timeSteps);
}

void BulletInterface::destroy() {
	if (!isInitialized)
		return;

	dynamicsWorld->removeRigidBody(groundRigidBody);
	delete groundRigidBody->getMotionState();
	delete groundRigidBody;

	delete groundShape;

	delete dynamicsWorld;
	delete solver;

	delete collisionConfiguration;
	delete dispatcher;
	delete broadphase;

	isInitialized = false;
}


BulletInterface::~BulletInterface()
{
	destroy();
}
