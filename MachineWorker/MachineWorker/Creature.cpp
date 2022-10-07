#include "Creature.h"

Creature::Creature(BulletInterface* bullet, UWorld* unrealWorld, UMaterial* capsuleMaterial, btVector3 position, pt::ptree jsonObject)
	: CreatureBase::CreatureBase(bullet, position, jsonObject)
{	
	// Rendering:
	unrealCreature = unrealWorld->SpawnActor<AUnrealCreature>(AUnrealCreature::StaticClass(), FVector(0,0,0), FRotator(0.f, 0.f, 0.f), FActorSpawnParameters());

	unrealCreature->setStructure(structure);

	// Create capules map (rendering<-->physics)
	std::vector<btRigidBody*> bulletCapsules = bulletCreature->getCapsules();
	std::vector<UnrealCapsule*> unrealCapsules = unrealCreature->getCapsules();
	for (int i = 0; i < bulletCapsules.size(); i++) {
		CAPSULE_UNREAL_BULLET capsuleLink = { unrealCapsules[i], bulletCapsules[i] };
		capsuleLinks.push_back(capsuleLink);
	}

	// Apply materials
	for (UnrealCapsule* unrealCapsule : unrealCapsules) {
		unrealCapsule->setMaterial(capsuleMaterial);
	}

	synchronizeRendering();
}

Creature::~Creature()
{
	if (unrealCreature)
		delete unrealCreature;
}

void Creature::terminate() {
	if(unrealCreature)
		unrealCreature->Destroy();

	CreatureBase::terminate();
}

void Creature::tick() {
	CreatureBase::tick();

	if (unrealCreature)
		synchronizeRendering();
}

void Creature::synchronizeRendering() {
	for (CAPSULE_UNREAL_BULLET capsuleLink : capsuleLinks) {
		btTransform bulletTransform = capsuleLink.bullet->getWorldTransform();
		btVector3 position = bulletTransform.getOrigin();
		btQuaternion rotation = bulletTransform.getRotation();

		capsuleLink.unreal->setPosition(FVector(position.x(), position.y(), position.z()));
		capsuleLink.unreal->setRotation(FQuat(rotation.x(), rotation.y(), rotation.z(), rotation.w()));
	}
}
