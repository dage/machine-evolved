#pragma once

#include "Communicator.h"
#include "WorkEvaluator.h"

#include <stack>
#include <mutex>

namespace pt = boost::property_tree;

/**
 * An async version of Communicator. Requests are sent and received in an own thread and is handled internally as queues for maximum overall application performance.
 * Based on https://wiki.unrealengine.com/Multi-Threading:_How_to_Create_Threads_in_UE4
 */
class AsyncCommunicator
{
public:
	AsyncCommunicator();
	~AsyncCommunicator();

	virtual pt::ptree getWork();
	virtual void sendResult(WorkEvaluator::TASK* task);
	virtual std::string getServerStatus();

	pt::ptree getBestCreature();

	void run();
	void stop();

private:
	int targetWorkQueueSize = 16;	// Attempt to fill work queue up to this size

	Communicator communicator = Communicator();
	std::mutex workMutex;
	std::mutex resultMutex;

	std::deque<pt::ptree> workQueue;
	std::stack<std::string> resultsQueue;
	std::string serverStatus = "";
	bool stopped = false;
};
