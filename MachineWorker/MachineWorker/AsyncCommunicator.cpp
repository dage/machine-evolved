#include "AsyncCommunicator.h"

AsyncCommunicator::AsyncCommunicator()
{
}

AsyncCommunicator::~AsyncCommunicator()
{
}

void AsyncCommunicator::run() {
	while (!stopped) {
		// Transfer results into concatenated json array results string
		std::string request = "{\"results\": [";
		std::unique_lock<std::mutex> resultsLock(resultMutex, std::defer_lock);
		resultsLock.lock();
		int numResults = resultsQueue.size();
		while (!resultsQueue.empty()) {
			auto result = resultsQueue.top();
			resultsQueue.pop();
			request += result;
			if (!resultsQueue.empty()) // more to go?
				request += ",";
		}
		request += "]";
		resultsLock.unlock();

		if (numResults == targetWorkQueueSize && workQueue.size() == 0) {
			printf("Increasing queue sizes from %i to %i.\n", targetWorkQueueSize, targetWorkQueueSize * 2);
			targetWorkQueueSize *= 2;
		}

		request += ",\"maxWorkUnits\":" + std::to_string(targetWorkQueueSize - workQueue.size()) + "}";

		auto response = communicator.doStepBatch(request);


		if (!response.empty()) {
			std::unique_lock<std::mutex> workLock(workMutex, std::defer_lock);
			workLock.lock();
			for (pt::ptree::value_type &workUnit : response.get_child("workUnits")) {
				workQueue.push_back(workUnit.second);
			}
			workLock.unlock();

			serverStatus = response.get<std::string>("status");
		}

		// TODO: Get work units - ensure inserted so that existing elements are removed first ("time to live" validation on server)
		// TODO: Get server status
		// TODO: Remove old code


		// Get new work:
/*		int numWorkUnitsRequested = 0;	// avoid situation where results are never sent because workers are quicker than server
		bool isServerExhausted = false;
		while (workQueue.size() != WORK_QUEUE_SIZE && numWorkUnitsRequested++ < 1000 && !isServerExhausted) {
			auto work = communicator.getWork();

			if (!work.empty() && work.get<std::string>("status") != "NO_WORK") {
				std::unique_lock<std::mutex> lock(workMutex, std::defer_lock);
				lock.lock();
				workQueue.push_back(work);
				lock.unlock();
			}
			else
				// TODO: Check returned json status and chill if status="NO_WORK"
				isServerExhausted = true;
		}

		// Get server status:
		serverStatus = communicator.getServerStatus();
*/
		// Chill:
		std::this_thread::sleep_for(std::chrono::seconds(1));	// No work ==> sleep a little bit to give server some time
	}
}

std::string AsyncCommunicator::getServerStatus() {
	//return communicator.getServerStatus();
	return serverStatus;
}

void AsyncCommunicator::stop() {
	stopped = true;
}

pt::ptree AsyncCommunicator::getBestCreature() {
	return communicator.getBestCreature();		// do it sequentially and blocking since this is called extremely rarely
}

pt::ptree AsyncCommunicator::getWork() {
	//return communicator.getWork();	// uncomment to instead use synchronous blocking version

	pt::ptree jsonObject;

	std::unique_lock<std::mutex> lock(workMutex, std::defer_lock);
	lock.lock();
	if (workQueue.empty()) {
		lock.unlock();
		return jsonObject;
	}

	jsonObject = workQueue.front();
	workQueue.pop_front();
	lock.unlock();
	return jsonObject;
}

void AsyncCommunicator::sendResult(WorkEvaluator::TASK* task) {
	//communicator.sendResult(task);		// uncomment to instead use synchronous blocking version
	//return;								// uncomment to instead use synchronous blocking version

	std::unique_lock<std::mutex> lock(resultMutex, std::defer_lock);
	lock.lock();
	resultsQueue.push(communicator.getSendResultSerialized(task));
	lock.unlock();
}