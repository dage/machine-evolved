#include "WorkEvaluator.h"

WorkEvaluator::WorkEvaluator()
{
}

WorkEvaluator::~WorkEvaluator()
{
}

void WorkEvaluator::remove(CreatureBase* creatureForRemove) {
	auto keptTasks = std::vector<TASK*>();

	for (auto task : tasks) {
		if (task->creature != creatureForRemove)
			keptTasks.push_back(task);
	}

	tasks = keptTasks;
}

void WorkEvaluator::add(pt::ptree jsonObject, CreatureBase* creatureToTrack) {
	std::string name = jsonObject.get<std::string>("name");
	std::string id = jsonObject.get<std::string>("id");
	std::string experimentId = jsonObject.get<std::string>("experimentId");

	TASK* taskInfo = new TASK(name, id, experimentId, creatureToTrack);
	if (name == "MOVE_FAR") {
		btVector3 startingPosition = creatureToTrack->getCenterOfMassPosition();
		startingPosition.setZ(0);
		MOVE_FAR_TASK* moveFarTask = new MOVE_FAR_TASK(taskInfo, startingPosition, 0.);
		delete taskInfo;
		tasks.push_back(moveFarTask);
	}
	else
		throw "Unknown task name: " + name;
}

// Call every tick in the simulation
// Returns a set of TASKS that are finished. Caller must perform clean-up on these.
std::vector<WorkEvaluator::TASK*> WorkEvaluator::tick() {
	auto keptTasks = std::vector<TASK*>();
	auto removedTasks = std::vector<TASK*>();

	for (auto task : tasks) {
		if (task->name == "MOVE_FAR") {
			MOVE_FAR_TASK* moveFarTask = (MOVE_FAR_TASK*)task;

			btVector3 position = moveFarTask->creature->getCenterOfMassPosition();
			position.setZ(0);

			double distance = (position - moveFarTask->startingPosition).length();
			if (distance > moveFarTask->maxDistance)
				moveFarTask->maxDistance = distance;

			if (--moveFarTask->remainingTicks<=0) 
				removedTasks.push_back(task);
			else
				keptTasks.push_back(task);
		}
	}

	tasks = keptTasks;
	return removedTasks;
}

