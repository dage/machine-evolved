#pragma once

#include "CoreMinimal.h"
#include "Engine/LevelScriptActor.h"
#include "Engine/World.h"

#include <vector>

#include "CreatureBase.h"
#include "UnrealCreature.h"
#include "BulletCreature.h"
#include "CreatureStructure.h"
#include "IMotorController.h"
#include "LinearMotorController.h"

#include <boost/property_tree/ptree.hpp>
#include <boost/property_tree/json_parser.hpp>

namespace pt = boost::property_tree;

/**
 * The creature class that has support for rendering in UE4.
 */
class MACHINEWORKER_API Creature : public CreatureBase
{
public:
	Creature(BulletInterface* bullet, UWorld* unrealWorld, UMaterial* capsuleMaterial, btVector3 position, pt::ptree jsonObject);  // Physics and rendering
	~Creature();

	void terminate();
	void tick();

private:
	struct CAPSULE_UNREAL_BULLET {	// links rendering and physics
		UnrealCapsule* unreal;
		btRigidBody* bullet;
	};

	AUnrealCreature* unrealCreature = NULL;
	std::vector<CAPSULE_UNREAL_BULLET> capsuleLinks;

	void synchronizeRendering();
};
