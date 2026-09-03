#pragma once

#include <string>
#include <functional>

#include "CreatureBase.h"
#include "MotionMetrics.h"

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
			TASK(std::string name, std::string id, std::string experimentId, std::string evaluationId, CreatureBase* creature) {
				this->name = name;
				this->id = id;
				this->experimentId = experimentId;
				this->evaluationId = evaluationId;
				this->creature = creature;
			}
			std::string name;
			std::string id;
			std::string experimentId;
			std::string evaluationId;
			CreatureBase* creature;
			double startTime;
	};

	class MOVE_FAR_TASK : public TASK {
		public:
			MOVE_FAR_TASK(TASK* task, btVector3 startingPosition, double maxDistance, int numberOfTicks, int controlRateHz, const pt::ptree& objective) : TASK(task->name, task->id, task->experimentId, task->evaluationId, task->creature) {
				this->startingPosition = startingPosition;
				this->maxDistance = maxDistance;
				this->numberOfTicks = numberOfTicks;
				this->controlRateHz = controlRateHz;
				this->remainingTicks = numberOfTicks;
				motion.initialize(task->creature, objective);
			}
			btVector3 startingPosition;
			double maxDistance;
			double fitness = 0.;
			MotionMetrics motion;
			int numberOfTicks;
			int controlRateHz;
			int remainingTicks;
	};

	void add(pt::ptree jsonObject, CreatureBase* creatureToTrack);
	void remove(CreatureBase* creatureForRemove);
	std::vector<TASK*> tick();

	std::vector<TASK*> tasks;
};
