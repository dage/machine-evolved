#pragma once

#include <ctime>
#include <ratio>
#include <thread>
#include <chrono>
#include <atomic>
#include <limits>
#include <stack>

#include "BulletInterface.h"
#include "CreatureBase.h"
#include "WorkEvaluator.h"
#include "Communicator.h"
#include "ICommunicator.h"

/**
 * Base class for worker. Independent of UE4.
 */
class BulletWorkerBase
{
public:
	BulletWorkerBase(ICommunicator* communicator = nullptr);
	~BulletWorkerBase();

	int id;
	static std::atomic<int> indexCounter;
	
	int runBlocking(int numCreatures = std::numeric_limits<int>::max());

	void terminate();
	

protected:
	std::atomic<bool> isTerminated{ false };

	ICommunicator* communicator;
	bool ownsCommunicator = false;
	BulletInterface bullet;
	WorkEvaluator workEvaluator = WorkEvaluator();

private:
	double getCurrentTime();
};
