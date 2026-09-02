#include "AsyncCommunicator.h"

#include <algorithm>
#include <cstdio>
#include <vector>

AsyncCommunicator::AsyncCommunicator()
{
}

AsyncCommunicator::~AsyncCommunicator()
{
}

void AsyncCommunicator::run() {
	int failedFlushAttempts = 0;
	while (true) {
		std::vector<std::string> pendingResults;
		{
			std::lock_guard<std::mutex> resultsLock(resultMutex);
			pendingResults.assign(resultsQueue.begin(), resultsQueue.end());
		}

		if (stopRequested && pendingResults.empty())
			break;

		std::size_t queuedWork = 0;
		{
			std::lock_guard<std::mutex> workLock(workMutex);
			queuedWork = workQueue.size();
		}

		// Submit completed evaluations and refill the work queue in one request.
		std::string request = "{\"results\": [";
		for (std::size_t index = 0; index < pendingResults.size(); ++index) {
			request += pendingResults[index];
			if (index + 1 < pendingResults.size())
				request += ",";
		}
		request += "]";

		if (static_cast<int>(pendingResults.size()) == targetWorkQueueSize && queuedWork == 0) {
			printf("Increasing queue sizes from %i to %i.\n", targetWorkQueueSize, targetWorkQueueSize * 2);
			targetWorkQueueSize *= 2;
		}

		const int maxWorkUnits = std::max(0, targetWorkQueueSize - static_cast<int>(queuedWork));
		request += ",\"maxWorkUnits\":" + std::to_string(stopRequested ? 0 : maxWorkUnits) + "}";

		auto response = communicator.doStepBatch(request);

		if (!response.empty()) {
			failedFlushAttempts = 0;
			if (!pendingResults.empty()) {
				std::lock_guard<std::mutex> resultsLock(resultMutex);
				for (std::size_t index = 0; index < pendingResults.size() && !resultsQueue.empty(); ++index)
					resultsQueue.pop_front();
			}

			if (!stopRequested) {
				std::lock_guard<std::mutex> workLock(workMutex);
				for (pt::ptree::value_type &workUnit : response.get_child("workUnits"))
					workQueue.push_back(workUnit.second);
			}

			{
				std::lock_guard<std::mutex> statusLock(statusMutex);
				serverStatus = response.get<std::string>("status", "");
			}
		}
		else if (stopRequested && !pendingResults.empty()) {
			failedFlushAttempts++;
			if (failedFlushAttempts >= 20) {
				std::fprintf(stderr, "Unable to flush %zu queued result(s); the trainer is unavailable.\n", pendingResults.size());
				break;
			}
		}

		std::unique_lock<std::mutex> wakeLock(wakeMutex);
		wakeCondition.wait_for(wakeLock, std::chrono::milliseconds(100), [this]() {
			return stopRequested.load();
		});
	}
	stopped = true;
}

std::string AsyncCommunicator::getServerStatus() {
	std::lock_guard<std::mutex> statusLock(statusMutex);
	return serverStatus;
}

void AsyncCommunicator::stop() {
	stopRequested = true;
	wakeCondition.notify_all();
}

bool AsyncCommunicator::isStopped() const {
	return stopped;
}

pt::ptree AsyncCommunicator::getBestCreature() {
	return communicator.getBestCreature();		// do it sequentially and blocking since this is called extremely rarely
}

pt::ptree AsyncCommunicator::getWork() {
	//return communicator.getWork();	// uncomment to instead use synchronous blocking version

	pt::ptree jsonObject;

	std::lock_guard<std::mutex> lock(workMutex);
	if (workQueue.empty()) {
		return jsonObject;
	}

	jsonObject = workQueue.front();
	workQueue.pop_front();
	return jsonObject;
}

void AsyncCommunicator::sendResult(WorkEvaluator::TASK* task) {
	//communicator.sendResult(task);		// uncomment to instead use synchronous blocking version
	//return;								// uncomment to instead use synchronous blocking version

	{
		std::lock_guard<std::mutex> lock(resultMutex);
		resultsQueue.push_back(communicator.getSendResultSerialized(task));
	}
	wakeCondition.notify_all();
}
