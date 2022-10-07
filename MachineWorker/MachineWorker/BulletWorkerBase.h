#pragma once

#include <ctime>
#include <ratio>
#include <thread>
#include <chrono>
#include <stack>

#include "BulletInterface.h"
#include "CreatureBase.h"
#include "WorkEvaluator.h"
#include "Communicator.h"
#include "AsyncCommunicator.h"

/**
 * Base class for worker. Independent of UE4.
 */
class BulletWorkerBase
{
public:
	BulletWorkerBase(AsyncCommunicator* communicator = nullptr);
	~BulletWorkerBase();

	int id;
	static int indexCounter;
	
	int runBlocking(int numCreatures = 2147483647);

	void terminate();
	

protected:
	bool isTerminated = false;

	Communicator* communicator;
	BulletInterface bullet;
	WorkEvaluator workEvaluator = WorkEvaluator();

private:
	double getCurrentTime();
};
