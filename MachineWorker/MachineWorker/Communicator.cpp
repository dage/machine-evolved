#include "Communicator.h"

std::map<Communicator::TYPE, std::string> enumToString;

Communicator::Communicator()
{
//	sendRequest(TYPE::PING);
}

Communicator::~Communicator()
{
}

std::string Communicator::getSendResultSerialized(WorkEvaluator::TASK* task) {
	std::string resultSerialized;

	if (task->name == "MOVE_FAR") {
		WorkEvaluator::MOVE_FAR_TASK* moveFarTask = (WorkEvaluator::MOVE_FAR_TASK*)task;
		
		//printf("fitness=%f\n", moveFarTask->maxDistance);

		resultSerialized = "{\"id\":\"" + task->id + "\",\"experimentId\":\"" + task->experimentId + "\",\"maxDistance\":" + std::to_string(moveFarTask->maxDistance) + ", \"simulatedTime\": " + std::to_string(WorkEvaluator::MOVE_FAR_TASK::NUMBER_OF_TICKS / 60) + "}";
	}
	return resultSerialized;
}

void Communicator::sendResult(std::string resultSerialized) {
	sendRequest(TYPE::RESULT, resultSerialized);
}

void Communicator::sendResult(WorkEvaluator::TASK* task) {
	sendResult(getSendResultSerialized(task));
}

std::string Communicator::getServerStatus() {
	pt::ptree response = sendRequestReturnJson(TYPE::GET_SERVER_STATUS);
	
	if (response.empty())
		return "SERVER DOWN";

	return response.get<std::string>("status");
}

pt::ptree Communicator::sendRequestReturnJson(Communicator::TYPE type, std::string data) {
	pt::ptree pt;

	auto response = sendRequest(type, data);

	if (response.empty()) {
		return pt;
	}

	// Deserialize data:
	std::istringstream is(response);
	pt::read_json(is, pt);

	return pt;
}

// sends results, receives a new work batch and server status
pt::ptree Communicator::doStepBatch(std::string request) {
	return sendRequestReturnJson(TYPE::STEP_BATCH, request);
}

pt::ptree Communicator::getWorkBatch(int maxWorkUnits) {
	return sendRequestReturnJson(TYPE::GET_WORK_BATCH, "{\"maxWorkUnits\":" + std::to_string(maxWorkUnits) + "}");
}

pt::ptree Communicator::getWork() {
	return sendRequestReturnJson(TYPE::GET_WORK);
}

pt::ptree Communicator::getBestCreature() {
	return sendRequestReturnJson(TYPE::GET_BEST_CREATURE);
}

std::string Communicator::getTypeAsString(TYPE type) {
	std::map<TYPE, std::string> enumToString;		// TODO: Optimize: Only initialize this once

	enumToString[TYPE::GET_BEST_CREATURE] = "GET_BEST_CREATURE";
	enumToString[TYPE::PING] = "PING";
	enumToString[TYPE::GET_WORK] = "GET_WORK";
	enumToString[TYPE::GET_WORK_BATCH] = "GET_WORK_BATCH";
	enumToString[TYPE::GET_SERVER_STATUS] = "GET_SERVER_STATUS";
	enumToString[TYPE::RESULT] = "RESULT";
	enumToString[TYPE::STEP_BATCH] = "STEP_BATCH";

	return enumToString[type];
}

// Sends TCP/IP request to server, blocks and returns response.
// Returns an empty string if an error occured.
std::string Communicator::sendRequest(TYPE type, std::string jsonData) {
	const std::string HOST = "127.0.0.1";
	const std::string PORT = "9999";

	// FAILED, not working. From: https://stackoverflow.com/questions/28827830/static-mutex-for-class-member-function-c-11
	//static std::mutex mutex;		// prevent multiple simultanous connection from the same client
	// This fails: std::lock_guard<std::mutex> lock(mutex);
	// AND this fails: std::unique_lock<std::mutex> lock(mutex);

	try
	{
		// Set up
		asio::io_service io_service;
		tcp::resolver resolver(io_service);
		tcp::resolver::query query(HOST, PORT);
		tcp::resolver::iterator endpoint_iterator = resolver.resolve(query);

		// Connect
		tcp::socket socket(io_service);
		asio::connect(socket, endpoint_iterator);

		// Send
		std::string typeString = getTypeAsString(type);
		std::string requestString = "{\"type\":\"" + typeString + "\"";
		if (type == TYPE::RESULT || type == TYPE::GET_WORK_BATCH || type == TYPE::STEP_BATCH)
			requestString += ",\"data\":" + jsonData + "}";
		else
			requestString += "}";
		asio::error_code ignored_error;

		asio::write(socket, asio::buffer(requestString), ignored_error);
		
		if (type == TYPE::RESULT)	// No response for this request ==> bail out!
			return "";	

		// Receive
		const int BLOCK_SIZE = 4096;
		std::string allBlocks = "";
		bool isFirstBlock = true;
		int bracketCount = 0;
		
		while(true) {
			std::vector<char> buf(128);
			asio::error_code error;

			size_t len = socket.read_some(asio::buffer(buf), error);
			
			if (len > 0) {	
				std::string block(buf.begin(), buf.begin() + len);

				int charIndex = 0;
				do {
					char c = buf.data()[charIndex];
					if (c == '{')
						bracketCount++;
					else if (c == '}')
						bracketCount--;
				} while (bracketCount > 0 && ++charIndex < len);
				allBlocks += block;
			}
			
			if (error == asio::error::eof || bracketCount == 0)
				break; // Connection closed cleanly by peer.
			else if (error)
				throw asio::system_error(error); // Some other error.
		}

		//printf("\n\n\n\n\nRequest: %s\n\n", requestString.c_str());
		//printf("Response: %s\n", allBlocks.c_str());

		return allBlocks;
	}
	catch (std::exception& e)
	{
		printf("Exception occured during communications: %s\n", e.what());  // Send to UE4 also to avoid compiler warning (--> error in UE4) for unused exception e.
		//std::this_thread::sleep_for(std::chrono::seconds(5));	// No work ==> sleep a little bit to give server some time
		return "";	// Let caller know to ignore this
	}
}