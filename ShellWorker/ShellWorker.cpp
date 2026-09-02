#include <atomic>
#include <cstdlib>
#include <exception>
#include <iostream>
#include <limits>
#include <string>
#include <thread>
#include <vector>

#include "AsyncCommunicator.h"
#include "BulletWorkerBase.h"

namespace
{
struct Options
{
	int threads = 8;
	int maxCreaturesPerWorker = std::numeric_limits<int>::max();
};

int parsePositiveInt(const std::string& value, const std::string& option)
{
	std::size_t parsedCharacters = 0;
	int parsedValue = 0;
	try {
		parsedValue = std::stoi(value, &parsedCharacters);
	}
	catch (const std::exception&) {
		throw std::runtime_error(option + " expects a positive integer, got '" + value + "'.");
	}

	if (parsedCharacters != value.size() || parsedValue < 1)
		throw std::runtime_error(option + " expects a positive integer, got '" + value + "'.");

	return parsedValue;
}

void printUsage(const char* executable)
{
	std::cout
		<< "Usage: " << executable << " [thread-count] [options]\n"
		<< "\n"
		<< "Options:\n"
		<< "  --threads N                    Number of parallel physics workers (default: 8).\n"
		<< "  --max-creatures-per-worker N   Exit after each worker completes N evaluations.\n"
		<< "  --help                         Show this help.\n";
}

Options parseOptions(int argc, char* argv[])
{
	Options options;
	bool positionalThreadsUsed = false;

	for (int index = 1; index < argc; ++index) {
		const std::string argument = argv[index];
		if (argument == "--help") {
			printUsage(argv[0]);
			std::exit(0);
		}
		if (argument == "--threads" || argument == "--max-creatures-per-worker") {
			if (++index >= argc)
				throw std::runtime_error(argument + " requires a value.");
			const int value = parsePositiveInt(argv[index], argument);
			if (argument == "--threads")
				options.threads = value;
			else
				options.maxCreaturesPerWorker = value;
			continue;
		}
		if (!argument.empty() && argument[0] != '-' && !positionalThreadsUsed) {
			options.threads = parsePositiveInt(argument, "thread-count");
			positionalThreadsUsed = true;
			continue;
		}
		throw std::runtime_error("Unknown argument '" + argument + "'.");
	}

	return options;
}
}

int main(int argc, char* argv[])
{
	try {
		const Options options = parseOptions(argc, argv);
		std::cout << "Using " << options.threads << " worker thread"
			<< (options.threads == 1 ? "" : "s") << ".\n";

		AsyncCommunicator communicator;
		std::thread communicatorThread([&communicator]() { communicator.run(); });

		std::atomic<int> completedEvaluations{ 0 };
		std::atomic<bool> workerFailed{ false };
		std::vector<std::thread> workers;
		workers.reserve(options.threads);
		for (int index = 0; index < options.threads; ++index) {
			workers.emplace_back([&]() {
				try {
					BulletWorkerBase worker(&communicator);
					completedEvaluations += worker.runBlocking(options.maxCreaturesPerWorker);
				}
				catch (const std::exception& exception) {
					workerFailed = true;
					std::cerr << "Worker failed: " << exception.what() << "\n";
				}
				catch (...) {
					workerFailed = true;
					std::cerr << "Worker failed with an unknown exception.\n";
				}
			});
		}

		for (std::thread& worker : workers)
			worker.join();

		// The communicator keeps queued results until the server acknowledges the
		// batch. Requesting stop after workers finish therefore performs a bounded
		// final flush instead of dropping the last evaluation.
		communicator.stop();
		communicatorThread.join();

		std::cout << "Completed " << completedEvaluations.load() << " evaluation"
			<< (completedEvaluations == 1 ? "" : "s") << ".\n";
		return workerFailed ? 1 : 0;
	}
	catch (const std::exception& exception) {
		std::cerr << "shellworker: " << exception.what() << "\n";
		printUsage(argv[0]);
		return 2;
	}
}
