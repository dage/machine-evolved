#pragma once

#include <string>
#include <map>
#include <iostream>
#include <sstream>
#include <algorithm> 
#include <cctype>
#include <locale>
#include <mutex>

#include "WorkEvaluator.h"


#define ASIO_STANDALONE 
#include <asio.hpp>

#include <boost/property_tree/ptree.hpp>
#include <boost/property_tree/json_parser.hpp>

using asio::ip::tcp;
namespace pt = boost::property_tree;

/**
 * Handles all socket communication with the server.
 */
class Communicator
{
public:
	enum TYPE { PING, GET_WORK, GET_WORK_BATCH, RESULT, GET_SERVER_STATUS, GET_BEST_CREATURE, STEP_BATCH };

	Communicator();
	~Communicator();

	static std::string getTypeAsString(TYPE type);

	virtual pt::ptree getWork();
	virtual void sendResult(WorkEvaluator::TASK* task);
	virtual std::string getServerStatus();
	
	void sendResult(std::string resultSerialized);
	pt::ptree getWorkBatch(int maxWorkUnits);
	pt::ptree getBestCreature();
	std::string getSendResultSerialized(WorkEvaluator::TASK* task);
	pt::ptree doStepBatch(std::string request);

private:
	pt::ptree sendRequestReturnJson(TYPE type, std::string data = "");
	std::string sendRequest(TYPE type, std::string data = "");
};
