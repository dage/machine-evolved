#pragma once

#include <string>
#include <functional>

#include "CreatureBase.h"

#include <boost/property_tree/ptree.hpp>
#include <boost/property_tree/json_parser.hpp>

namespace pt = boost::property_tree;

/**
 * Evaluates creature performance for executing the different tasks.
 */
class WorkEvaluator
{
public:
	WorkEvaluator();
	~WorkEvaluator();

	class TASK {	// base 
		public:
			TASK(std::string name, std::string id, std::string experimentId, CreatureBase* creature) {
				this->name = name;
				this->id = id;
				this->experimentId = experimentId;
				this->creature = creature;
			}
			std::string name;
			std::string id;
			std::string experimentId;
			CreatureBase* creature;
			double startTime;
	};

	class MOVE_FAR_TASK : public TASK {
		public:
			MOVE_FAR_TASK(TASK* task, btVector3 startingPosition, double maxDistance) : TASK(task->name, task->id, task->experimentId, task->creature) {
				this->startingPosition = startingPosition;
				this->maxDistance = maxDistance;
			}
			static const int NUMBER_OF_TICKS = 60*60*1;
			btVector3 startingPosition;
			double maxDistance;
			int remainingTicks = NUMBER_OF_TICKS;	// 3600 = 60*60 = 60 FPS/s * 60 secs = 1 minutte
	};

	void add(pt::ptree jsonObject, CreatureBase* creatureToTrack);
	void remove(CreatureBase* creatureForRemove);
	std::vector<TASK*> tick();

	std::vector<TASK*> tasks;
};
