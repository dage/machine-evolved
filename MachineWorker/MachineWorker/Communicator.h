#pragma once

#include <string>
#include <map>
#include <iostream>
#include <sstream>
#include <algorithm> 
#include <cctype>
#include <locale>
#include <mutex>

#include "ICommunicator.h"

#include <boost/asio.hpp>
#include <boost/property_tree/ptree.hpp>
#include <boost/property_tree/json_parser.hpp>

namespace asio = boost::asio;
using boost::asio::ip::tcp;
namespace pt = boost::property_tree;

/**
 * Handles all socket communication with the server.
 */
class Communicator : public ICommunicator
{
public:
	enum TYPE { PING, GET_WORK, GET_WORK_BATCH, RESULT, GET_SERVER_STATUS, GET_BEST_CREATURE, STEP_BATCH };

	Communicator();
	~Communicator() override;

	static std::string getTypeAsString(TYPE type);

	pt::ptree getWork() override;
	void sendResult(WorkEvaluator::TASK* task) override;
	std::string getServerStatus() override;
	
	void sendResult(std::string resultSerialized);
	pt::ptree getWorkBatch(int maxWorkUnits);
	pt::ptree getBestCreature();
	std::string getSendResultSerialized(WorkEvaluator::TASK* task);
	pt::ptree doStepBatch(std::string request);

private:
	pt::ptree sendRequestReturnJson(TYPE type, std::string data = "");
	std::string sendRequest(TYPE type, std::string data = "");
};
