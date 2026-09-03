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

void BulletInterface::configure(pt::ptree config) {
	if (!isInitialized)
		return;

	const std::string backend = config.get<std::string>("backend", "machine-evolved-bullet-v1");
	v2Physics = backend == "machine-evolved-bullet-v2";
	if (backend != "machine-evolved-bullet-v1" && !v2Physics)
		throw std::runtime_error("Unknown Bullet backend: " + backend);
	controlRateHz = v2Physics ? config.get<int>("controlRateHz", 60) : 60;
	physicsRateHz = v2Physics ? config.get<int>("physicsRateHz", 120) : 60;
	if (controlRateHz <= 0 || physicsRateHz < controlRateHz || physicsRateHz % controlRateHz != 0)
		throw std::runtime_error("physicsRateHz must be an integer multiple of controlRateHz");
	physicsSubsteps = physicsRateHz / controlRateHz;
	dynamicsWorld->getSolverInfo().m_numIterations = v2Physics
		? config.get<int>("solverIterations", 20)
		: dynamicsWorld->getSolverInfo().m_numIterations;
	if (v2Physics)
		dynamicsWorld->getSolverInfo().m_splitImpulse = config.get<bool>("splitImpulse", true);

	dynamicsWorld->setGravity(btVector3(
		config.get<float>("gravityX", 0.f),
		config.get<float>("gravityY", 0.f),
		config.get<float>("gravityZ", -200.f)));
	groundRigidBody->setFriction(config.get<float>("groundFriction", 4.f));
	capsuleFriction = config.get<float>("capsuleFriction", 0.5f);
	capsuleRollingFriction = config.get<float>("capsuleRollingFriction", 0.f);
	capsuleSpinningFriction = config.get<float>("capsuleSpinningFriction", 0.f);
	capsuleRestitution = config.get<float>("capsuleRestitution", 0.f);
	capsuleLinearDamping = config.get<float>("capsuleLinearDamping", 0.f);
	capsuleAngularDamping = config.get<float>("capsuleAngularDamping", 0.f);
	capsuleMassScale = config.get<float>("capsuleMassScale", 0.0001f);
	capsuleCcdEnabled = v2Physics && config.get<bool>("capsuleCcdEnabled", true);
	ccdMotionThresholdRadiusRatio = config.get<float>("ccdMotionThresholdRadiusRatio", 0.25f);
	ccdSweptSphereRadiusRatio = config.get<float>("ccdSweptSphereRadiusRatio", 0.2f);
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
	btScalar mass;
	if (v2Physics)
		mass = PI * radius * radius * innerHeight +
			4. * PI * radius * radius * radius / 3.;
	else
		mass = PI * radius * radius * innerHeight +	// Preserve Bullet-v1's exact floating-point evaluation order.
			4 * 3 / PI * radius*radius*radius;

	mass *= capsuleMassScale;

	//UE_LOG(LogTemp, Warning, TEXT("Capsule with mass %f added."), mass);

	btVector3 fallInertia(0, 0, 0);
	fallShape->calculateLocalInertia(mass, fallInertia);
	btRigidBody::btRigidBodyConstructionInfo fallRigidBodyCI(mass, fallMotionState, fallShape, fallInertia);
	fallRigidBodyCI.m_friction = capsuleFriction;
	fallRigidBodyCI.m_restitution = capsuleRestitution;
	btRigidBody* fallRigidBody = new btRigidBody(fallRigidBodyCI);
	fallRigidBody->setRollingFriction(capsuleRollingFriction);
	fallRigidBody->setSpinningFriction(capsuleSpinningFriction);
	fallRigidBody->setDamping(capsuleLinearDamping, capsuleAngularDamping);
	if (capsuleCcdEnabled) {
		fallRigidBody->setCcdMotionThreshold(ccdMotionThresholdRadiusRatio * radius);
		fallRigidBody->setCcdSweptSphereRadius(ccdSweptSphereRadiusRatio * radius);
	}
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

	if (!v2Physics) {
		double frameTime = 1. / 60.;
		int timeSteps = 1;
		dynamicsWorld->stepSimulation(frameTime, timeSteps, frameTime / timeSteps);
		return;
	}
	const btScalar controlStep = 1. / static_cast<btScalar>(controlRateHz);
	const btScalar physicsStep = 1. / static_cast<btScalar>(physicsRateHz);
	dynamicsWorld->stepSimulation(controlStep, physicsSubsteps, physicsStep);
}

bool BulletInterface::usesV2Physics() const {
	return v2Physics;
}

int BulletInterface::getControlRateHz() const {
	return controlRateHz;
}

int BulletInterface::getPhysicsRateHz() const {
	return physicsRateHz;
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
