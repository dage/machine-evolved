#pragma once

#include <string>

#include <boost/property_tree/ptree.hpp>

#include "WorkEvaluator.h"

namespace pt = boost::property_tree;

class ICommunicator
{
public:
	virtual ~ICommunicator() = default;

	virtual pt::ptree getWork() = 0;
	virtual void sendResult(WorkEvaluator::TASK* task) = 0;
	virtual std::string getServerStatus() = 0;
	virtual bool shouldStopWorkers() const = 0;
};
