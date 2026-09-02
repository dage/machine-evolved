#pragma once

#include "Communicator.h"
#include "ICommunicator.h"

#include <atomic>
#include <condition_variable>
#include <deque>
#include <stack>
#include <mutex>

namespace pt = boost::property_tree;

/**
 * An async version of Communicator. Requests are sent and received in an own thread and is handled internally as queues for maximum overall application performance.
 * Based on https://wiki.unrealengine.com/Multi-Threading:_How_to_Create_Threads_in_UE4
 */
class AsyncCommunicator : public ICommunicator
{
public:
	AsyncCommunicator();
	~AsyncCommunicator() override;

	pt::ptree getWork() override;
	void sendResult(WorkEvaluator::TASK* task) override;
	std::string getServerStatus() override;
	bool shouldStopWorkers() const override;

	pt::ptree getBestCreature();

	void run();
	void stop();
	bool isStopped() const;

private:
	int targetWorkQueueSize = 16;	// Attempt to fill work queue up to this size

	Communicator communicator = Communicator();
	std::mutex workMutex;
	std::mutex resultMutex;
	std::mutex statusMutex;
	std::mutex wakeMutex;
	std::condition_variable wakeCondition;

	std::deque<pt::ptree> workQueue;
	std::deque<std::string> resultsQueue;
	std::string serverStatus = "";
	std::atomic<bool> stopRequested{ false };
	std::atomic<bool> stopped{ false };
	std::atomic<bool> trainerStopped{ false };
};
