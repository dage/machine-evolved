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
	std::string evaluationId = jsonObject.get<std::string>("evaluationId", "");

	TASK* taskInfo = new TASK(name, id, experimentId, evaluationId, creatureToTrack);
	if (name == "MOVE_FAR") {
		int numberOfTicks = jsonObject.get<int>("horizonTicks", 60 * 60);
		pt::ptree objective;
		if (auto configuredObjective = jsonObject.get_child_optional("objective"))
			objective = *configuredObjective;
		btVector3 startingPosition = creatureToTrack->getCenterOfMassPosition();
		startingPosition.setZ(0);
		MOVE_FAR_TASK* moveFarTask = new MOVE_FAR_TASK(taskInfo, startingPosition, 0., numberOfTicks, objective);
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

			moveFarTask->motion.tick(moveFarTask->creature);
			moveFarTask->maxDistance = moveFarTask->motion.maxDistance;

			if (--moveFarTask->remainingTicks<=0) {
				moveFarTask->motion.finalize(static_cast<double>(moveFarTask->numberOfTicks) / 60.0);
				moveFarTask->fitness = moveFarTask->motion.fitness;
				removedTasks.push_back(task);
			}
			else
				keptTasks.push_back(task);
		}
	}

	tasks = keptTasks;
	return removedTasks;
}
