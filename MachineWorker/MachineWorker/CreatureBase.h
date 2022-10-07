#pragma once

#include "BulletInterface.h"
#include "IMotorController.h"
#include "LinearMotorController.h"
#include "BulletCreature.h"
#include "CreatureStructure.h"

#include <boost/property_tree/ptree.hpp>
#include <boost/property_tree/json_parser.hpp>

namespace pt = boost::property_tree;

/**
 * A UE4-independent base class for the Creature
 */
class CreatureBase
{
public:
	CreatureBase(BulletInterface* bullet, btVector3 position, pt::ptree jsonObject);
	~CreatureBase();

	btVector3 getCenterOfMassPosition();
	void tick();
	void terminate();

protected:
	IMotorController* motorController;
	BulletCreature* bulletCreature;
	CreatureStructure* structure;

	int numTicks = 0;

private:
	void applyMotorForces();
};
