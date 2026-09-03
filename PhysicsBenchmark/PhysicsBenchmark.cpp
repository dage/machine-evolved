#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <exception>
#include <iomanip>
#include <iostream>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include <boost/property_tree/json_parser.hpp>
#include <boost/property_tree/ptree.hpp>

#include "BulletCreature.h"
#include "BulletInterface.h"
#include "CreatureStructure.h"

namespace pt = boost::property_tree;

namespace {
struct Options {
	std::string specPath;
	int rollouts = 1;
	int workers = 1;
	int warmupRollouts = 1;
	int ticks = 0;
};

struct RolloutResult {
	double seconds = 0.;
	double x = 0.;
	double y = 0.;
	double z = 0.;
	std::uint64_t digest = 1469598103934665603ULL;
	bool finite = true;
};

Options parseOptions(int argc, char** argv) {
	Options options;
	for (int index = 1; index < argc; ++index) {
		const std::string argument = argv[index];
		auto value = [&]() -> std::string {
			if (++index >= argc)
				throw std::runtime_error("Missing value for " + argument);
			return argv[index];
		};
		if (argument == "--spec") options.specPath = value();
		else if (argument == "--rollouts") options.rollouts = std::stoi(value());
		else if (argument == "--workers") options.workers = std::stoi(value());
		else if (argument == "--warmup-rollouts") options.warmupRollouts = std::stoi(value());
		else if (argument == "--ticks") options.ticks = std::stoi(value());
		else throw std::runtime_error("Unknown argument: " + argument);
	}
	if (options.specPath.empty()) throw std::runtime_error("--spec is required");
	if (options.rollouts <= 0 || options.workers <= 0 || options.warmupRollouts < 0 || options.ticks < 0)
		throw std::runtime_error("Rollout, worker, warmup and tick counts are invalid");
	return options;
}

std::vector<std::vector<float>> readActionTape(const pt::ptree& spec) {
	std::vector<std::vector<float>> tape;
	for (const auto& frameNode : spec.get_child("actionTape.frames")) {
		std::vector<float> frame;
		for (const auto& valueNode : frameNode.second)
			frame.push_back(valueNode.second.get_value<float>());
		if (frame.size() != 6) throw std::runtime_error("Every action frame must contain six velocities");
		tape.push_back(frame);
	}
	if (tape.empty()) throw std::runtime_error("Action tape must not be empty");
	return tape;
}

void hashFloat(std::uint64_t& hash, float value) {
	std::uint32_t bits = 0;
	static_assert(sizeof(bits) == sizeof(value), "float size mismatch");
	std::memcpy(&bits, &value, sizeof(value));
	for (int shift = 0; shift < 32; shift += 8) {
		hash ^= static_cast<std::uint8_t>((bits >> shift) & 0xff);
		hash *= 1099511628211ULL;
	}
}

RolloutResult runOne(
	const pt::ptree& spec,
	const std::vector<std::vector<float>>& tape,
	int ticks)
{
	const auto started = std::chrono::steady_clock::now();
	BulletInterface bullet;
	bullet.init();
	bullet.configure(spec.get_child("bulletPhysics"));
	CreatureStructure structure(spec.get_child("structure"));
	BulletCreature creature(
		&bullet,
		&structure,
		btVector3(0, 0, 0),
		spec.get<float>("bulletPhysics.motorMaxForce"));

	const bool sleepingEnabled = spec.get<bool>("benchmark.sleepingEnabled", true);
	if (!sleepingEnabled) {
		for (auto* body : creature.getCapsules()) body->setActivationState(DISABLE_DEACTIVATION);
	}
	const auto motors = creature.getMotors();
	if (motors.size() != 6) throw std::runtime_error("Benchmark structure must expose six motors");
	const int controlRateHz = bullet.getControlRateHz();
	for (int tick = 0; tick < ticks; ++tick) {
		const auto& frame = tape[static_cast<std::size_t>(tick) % tape.size()];
		for (std::size_t motor = 0; motor < motors.size(); ++motor)
			motors[motor]->m_targetVelocity = frame[motor];
		bullet.tick(1.f / static_cast<float>(controlRateHz));
	}

	RolloutResult result;
	const float scale = spec.get<float>("coordinateConversion.scale", 0.01f);
	const btVector3 center = creature.getCenterOfMassPosition();
	result.x = center.x() * scale;
	result.y = center.z() * scale;
	result.z = -center.y() * scale;
	result.finite = std::isfinite(result.x) && std::isfinite(result.y) && std::isfinite(result.z);
	for (auto* body : creature.getCapsules()) {
		const btTransform& transform = body->getWorldTransform();
		const btVector3 position = transform.getOrigin();
		const btQuaternion rotation = transform.getRotation();
		hashFloat(result.digest, position.x());
		hashFloat(result.digest, position.y());
		hashFloat(result.digest, position.z());
		hashFloat(result.digest, rotation.x());
		hashFloat(result.digest, rotation.y());
		hashFloat(result.digest, rotation.z());
		hashFloat(result.digest, rotation.w());
	}
	creature.terminate();
	result.seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count();
	return result;
}

double quantile(std::vector<double> values, double amount) {
	std::sort(values.begin(), values.end());
	const double index = (values.size() - 1) * amount;
	const auto lower = static_cast<std::size_t>(std::floor(index));
	const auto upper = static_cast<std::size_t>(std::ceil(index));
	if (lower == upper) return values[lower];
	return values[lower] + (values[upper] - values[lower]) * (index - lower);
}

std::string hexDigest(std::uint64_t value) {
	std::ostringstream output;
	output << std::hex << std::setfill('0') << std::setw(16) << value;
	return output.str();
}
}

int main(int argc, char** argv) {
	try {
		const Options options = parseOptions(argc, argv);
		pt::ptree spec;
		pt::read_json(options.specPath, spec);
		if (spec.get<int>("schemaVersion") != 1)
			throw std::runtime_error("Unsupported benchmark spec schema");
		const auto tape = readActionTape(spec);
		const int ticks = options.ticks > 0 ? options.ticks : spec.get<int>("benchmark.horizonTicks");
		const int physicsRateHz = spec.get<int>("bulletPhysics.physicsRateHz");
		const int controlRateHz = spec.get<int>("bulletPhysics.controlRateHz");
		if (physicsRateHz % controlRateHz != 0)
			throw std::runtime_error("Physics rate must be an integer multiple of control rate");

		std::vector<RolloutResult> results(static_cast<std::size_t>(options.rollouts));
		std::vector<std::exception_ptr> errors(static_cast<std::size_t>(options.workers));
		std::atomic<int> next{0};
		std::atomic<int> ready{0};
		std::atomic<bool> go{false};
		std::vector<std::thread> threads;
		threads.reserve(static_cast<std::size_t>(options.workers));
		for (int worker = 0; worker < options.workers; ++worker) {
			threads.emplace_back([&, worker]() {
				try {
					for (int warmup = 0; warmup < options.warmupRollouts; ++warmup)
						runOne(spec, tape, ticks);
					ready.fetch_add(1, std::memory_order_release);
					while (!go.load(std::memory_order_acquire)) std::this_thread::yield();
					for (;;) {
						const int index = next.fetch_add(1);
						if (index >= options.rollouts) break;
						results[static_cast<std::size_t>(index)] = runOne(spec, tape, ticks);
					}
				} catch (...) {
					errors[static_cast<std::size_t>(worker)] = std::current_exception();
					ready.fetch_add(1, std::memory_order_release);
				}
			});
		}
		while (ready.load(std::memory_order_acquire) < options.workers) std::this_thread::yield();
		const auto wallStarted = std::chrono::steady_clock::now();
		go.store(true, std::memory_order_release);
		for (auto& thread : threads) thread.join();
		const double wallSeconds = std::chrono::duration<double>(
			std::chrono::steady_clock::now() - wallStarted).count();
		for (const auto& error : errors) if (error) std::rethrow_exception(error);

		std::vector<double> durations;
		std::set<std::uint64_t> digests;
		bool finite = true;
		for (const auto& result : results) {
			durations.push_back(result.seconds);
			digests.insert(result.digest);
			finite = finite && result.finite;
		}
		const double simulatedSeconds = static_cast<double>(options.rollouts * ticks) / controlRateHz;
		const double physicsSteps = static_cast<double>(options.rollouts * ticks)
			* (physicsRateHz / controlRateHz);
		const auto& sample = results.front();
		std::cout << std::setprecision(12)
			<< "{\"schemaVersion\":1,\"engine\":\"bullet-native\",\"specId\":\""
			<< spec.get<std::string>("id") << "\",\"actionTapeId\":\""
			<< spec.get<std::string>("actionTape.id") << "\",\"workers\":" << options.workers
			<< ",\"rollouts\":" << options.rollouts << ",\"warmupRolloutsPerWorker\":" << options.warmupRollouts
			<< ",\"controlTicksPerRollout\":" << ticks << ",\"physicsStepsPerRollout\":"
			<< ticks * (physicsRateHz / controlRateHz) << ",\"wallSeconds\":" << wallSeconds
			<< ",\"rolloutsPerSecond\":" << options.rollouts / wallSeconds
			<< ",\"simulatedSecondsPerSecond\":" << simulatedSeconds / wallSeconds
			<< ",\"physicsStepsPerSecond\":" << physicsSteps / wallSeconds
			<< ",\"latencySeconds\":{\"p50\":" << quantile(durations, .50)
			<< ",\"p95\":" << quantile(durations, .95) << ",\"p99\":" << quantile(durations, .99)
			<< "},\"finite\":" << (finite ? "true" : "false")
			<< ",\"uniqueFinalStateDigests\":" << digests.size()
			<< ",\"sampleFinalState\":{\"centerOfMass\":{\"x\":" << sample.x
			<< ",\"y\":" << sample.y << ",\"z\":" << sample.z << "},\"digest\":\""
			<< hexDigest(sample.digest) << "\"}}\n";
		return finite ? 0 : 2;
	} catch (const std::exception& error) {
		std::cerr << "physicsbenchmark: " << error.what() << '\n';
		return 1;
	}
}
