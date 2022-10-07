#include "BulletWorkerBase.h"

/**
* Runs the physics simulation. Independent of UE4.
*/

BulletWorkerBase::BulletWorkerBase(AsyncCommunicator* communicator)
{
	id = ++indexCounter;

	if (communicator)
		this->communicator = (Communicator*)communicator;
	else
		this->communicator = new Communicator();
}

BulletWorkerBase::~BulletWorkerBase()
{
}

double BulletWorkerBase::getCurrentTime() {
	auto now = std::chrono::system_clock::now().time_since_epoch();
	return std::chrono::duration_cast<std::chrono::microseconds>(now).count() / 1000000.;
}

int BulletWorkerBase::runBlocking(int numCreatures) {
	//communicator = AsyncCommunicator::start();
	bullet = BulletInterface();
	bullet.init();

	int numCompleted = 0;
	const int NUM_IN_FLIGHT = 1;		// WARNING: Introduces problems for >1. Keep at =1 for now.
	int numToCreate;
	int checkPointCreatures = 0;
	double checkPointLastTime = getCurrentTime();
	bool noWork = false;

	std::list<CreatureBase*> creatures;
	do {
		noWork = false;
		numToCreate = NUM_IN_FLIGHT - creatures.size();

		if (creatures.size() == 0) {	// no currently simulated creatues?
			auto jsonObject = communicator->getWork();

			if (jsonObject.empty() || jsonObject.get<std::string>("status") == "NO_WORK") {
				std::this_thread::sleep_for(std::chrono::microseconds(200));	// No work ==> sleep a little bit to give server some time
			}
			else {
				btVector3 position = btVector3(0.*(numCompleted%NUM_IN_FLIGHT), 0, 0);	// prevent crashing
				CreatureBase* creature = new CreatureBase(&bullet, position, jsonObject.get_child("creature"));
				workEvaluator.add(jsonObject.get_child("task"), creature);
				creatures.push_back(creature);
			}
		}

		/* Old discarded code for having multiple creatues in flight simultanously. Re-examine when implementing gpu support.
		while (numToCreate > 0 && !noWork) {
		auto jsonObject = communicator->getWork();
		if (!jsonObject.empty() && jsonObject.get<std::string>("status") == "OK") {
		btVector3 position = btVector3(0.*(numCompleted%NUM_IN_FLIGHT), 0, 0);	// prevent crashing
		CreatureBase* creature = new CreatureBase(&bullet, position, jsonObject.get_child("creature"));
		workEvaluator.add(jsonObject.get_child("task"), creature);
		numToCreate--;
		creatures.push_back(creature);
		}
		else if (creatures.size() == 0) {
		std::this_thread::sleep_for(std::chrono::microseconds(200));	// No work ==> sleep a little bit to give server some time

		//noWork = true;
		//UE_LOG(LogTemp, Warning, TEXT("No work available for worker %d. Sleeping a bit.."), id);
		//FPlatformProcess::Sleep(.5f);	// Nothing to do, sleep a bit
		}
		}
		*/

		bullet.tick(1 / 60.f);
		for (auto creature : creatures)
			creature->tick();

		std::vector<WorkEvaluator::TASK*> removedTasks = workEvaluator.tick();
		for (auto task : removedTasks) {
			numCompleted++;
			checkPointCreatures++;
			numToCreate++;
			communicator->sendResult(task);
			creatures.remove(task->creature);
			task->creature->terminate();
			delete task->creature;
			delete task;
		}

#ifdef SHELL
		double time = getCurrentTime();
		if (time >= checkPointLastTime + 10) {
			double creaturesPerSecond = checkPointCreatures / (time - checkPointLastTime);
			printf("Speed: %f creatures/sec. Server status: %s\n", creaturesPerSecond, communicator->getServerStatus().c_str());
			checkPointLastTime = time;
			checkPointCreatures = 0;
		}
#endif // SHELL

	} while (!isTerminated && numCompleted < numCreatures);

	bullet.destroy();

	return numCompleted;
}

// Calling this from any threads signal the blocking main loop to gracefully finish.
void BulletWorkerBase::terminate() {
	isTerminated = true;
}

int BulletWorkerBase::indexCounter = 0;