#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include <boost/property_tree/json_parser.hpp>
#include <boost/property_tree/ptree.hpp>

#include "BulletInterface.h"
#include "CreatureBase.h"
#include "MotionMetrics.h"

namespace pt = boost::property_tree;

namespace
{
constexpr int FIXED_STEP_HZ = 60;
constexpr double DISPLAY_SCALE = 0.01;

struct Options
{
	std::string config;
	std::string output;
	int sampleHz = 20;
};

struct ReplaySample
{
	int tick;
	btVector3 center;
	std::vector<CreatureBase::CapsulePose> capsules;
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
		<< "Usage: " << executable << " --config FILE --output FILE [--sample-hz N]\n"
		<< "\nExports a deterministic replay of the highest-fitness saved creature.\n";
}

Options parseOptions(int argc, char* argv[])
{
	Options options;
	for (int index = 1; index < argc; ++index) {
		const std::string argument = argv[index];
		if (argument == "--help") {
			printUsage(argv[0]);
			std::exit(0);
		}
		if (argument == "--config" || argument == "--output" || argument == "--sample-hz") {
			if (++index >= argc)
				throw std::runtime_error(argument + " requires a value.");
			if (argument == "--config") options.config = argv[index];
			else if (argument == "--output") options.output = argv[index];
			else options.sampleHz = parsePositiveInt(argv[index], argument);
			continue;
		}
		throw std::runtime_error("Unknown argument '" + argument + "'.");
	}
	if (options.config.empty() || options.output.empty())
		throw std::runtime_error("--config and --output are required.");
	if (options.sampleHz > FIXED_STEP_HZ || FIXED_STEP_HZ % options.sampleHz != 0)
		throw std::runtime_error("--sample-hz must divide the fixed 60 Hz simulation rate.");
	return options;
}

std::string jsonString(const std::string& value)
{
	std::ostringstream output;
	output << '"';
	for (const unsigned char character : value) {
		switch (character) {
		case '"': output << "\\\""; break;
		case '\\': output << "\\\\"; break;
		case '\b': output << "\\b"; break;
		case '\f': output << "\\f"; break;
		case '\n': output << "\\n"; break;
		case '\r': output << "\\r"; break;
		case '\t': output << "\\t"; break;
		default:
			if (character < 0x20)
				output << "\\u" << std::hex << std::setw(4) << std::setfill('0')
					<< static_cast<int>(character) << std::dec << std::setfill(' ');
			else
				output << character;
		}
	}
	output << '"';
	return output.str();
}

btVector3 displayPosition(const btVector3& source)
{
	return btVector3(
		source.x() * DISPLAY_SCALE,
		source.z() * DISPLAY_SCALE,
		-source.y() * DISPLAY_SCALE);
}

btQuaternion displayRotation(const btQuaternion& source)
{
	const btMatrix3x3 sourceRotation(source);
	const btMatrix3x3 basis(
		1, 0, 0,
		0, 0, 1,
		0, -1, 0);
	const btMatrix3x3 converted = basis * sourceRotation * basis.transpose();
	btQuaternion output;
	converted.getRotation(output);
	output.normalize();
	return output;
}

void writeVector(std::ostream& output, const btVector3& value)
{
	output << "{\"x\":" << value.x()
		<< ",\"y\":" << value.y()
		<< ",\"z\":" << value.z() << '}';
}

void writeQuaternion(std::ostream& output, const btQuaternion& value)
{
	output << "{\"x\":" << value.x()
		<< ",\"y\":" << value.y()
		<< ",\"z\":" << value.z()
		<< ",\"w\":" << value.w() << '}';
}

void writePose(std::ostream& output, const btVector3& position, const btQuaternion& rotation)
{
	output << "{\"translation\":";
	writeVector(output, displayPosition(position));
	output << ",\"rotation\":";
	writeQuaternion(output, displayRotation(rotation));
	output << '}';
}

void writeReplay(
	const Options& options,
	const pt::ptree& config,
	const pt::ptree& creatureData,
	double configuredFitness,
	double measuredDistance,
	double measuredFitness,
	const MotionMetrics& motion,
	int horizonTicks,
	const std::vector<ReplaySample>& samples)
{
	const std::filesystem::path outputPath(options.output);
	if (!outputPath.parent_path().empty())
		std::filesystem::create_directories(outputPath.parent_path());
	std::filesystem::path temporaryPath = outputPath;
	temporaryPath += ".tmp";
	std::ofstream output(temporaryPath, std::ios::out | std::ios::trunc);
	if (!output)
		throw std::runtime_error("Unable to open temporary replay output: " + temporaryPath.string());
	output << std::setprecision(9);
	const auto& experiment = config.get_child("experiment");
	const auto& physics = experiment.get_child("physics");
	const auto& capsules = creatureData.get_child("structure.capsules");
	output << "{\n"
		<< " \"schemaVersion\":1,\n"
		<< " \"kind\":\"machine-evolved-capsules-v1\",\n"
		<< " \"backendId\":" << jsonString(experiment.get<std::string>("backend", "machine-evolved-bullet-v1")) << ",\n"
		<< " \"profile\":" << jsonString(experiment.get<std::string>("profile", "unknown")) << ",\n"
		<< " \"creatureId\":\"machine-evolved-three-capsule-v1\",\n"
		<< " \"displayName\":\"Machine Evolved · Three Capsule Distance\",\n"
		<< " \"sampleHz\":" << options.sampleHz << ",\n"
		<< " \"durationSeconds\":" << static_cast<double>(horizonTicks) / FIXED_STEP_HZ << ",\n"
		<< " \"configuredFitness\":" << configuredFitness << ",\n"
		<< " \"measuredMaxDistanceSimulationUnits\":" << measuredDistance << ",\n"
		<< " \"measuredFitness\":" << measuredFitness << ",\n"
		<< " \"fitnessParity\":{\"absoluteError\":" << std::abs(configuredFitness - measuredFitness)
		<< ",\"verified\":true},\n"
		<< " \"motionMetrics\":{\"credible\":" << (motion.credible ? "true" : "false")
		<< ",\"finalDistanceSimulationUnits\":" << motion.finalDistance
		<< ",\"pathLengthSimulationUnits\":" << motion.pathLength
		<< ",\"unsupportedPathFraction\":" << motion.unsupportedPathFraction
		<< ",\"nearGroundTimeFraction\":" << motion.nearGroundTimeFraction
		<< ",\"longestUnsupportedSeconds\":" << motion.longestUnsupportedSeconds
		<< ",\"rawMaxDistanceSimulationUnits\":" << motion.maxDistance
		<< ",\"discountedFitnessSimulationUnits\":" << motion.fitness
		<< ",\"rollingExplainedFraction\":" << motion.rollingExplainedFraction
		<< ",\"rollingDiscountEnabled\":" << (motion.rollingDiscountEnabled ? "true" : "false")
		<< ",\"rollingDiscountLambda\":" << motion.rollingDiscountLambda
		<< ",\"rollingDiscountEpsilonSimulationUnits\":" << motion.rollingDiscountEpsilon
		<< ",\"rollingDiscountConfig\":{\"enabled\":" << (motion.rollingDiscountEnabled ? "true" : "false")
		<< ",\"lambda\":" << motion.rollingDiscountLambda
		<< ",\"epsilonSimulationUnits\":" << motion.rollingDiscountEpsilon << '}'
		<< ",\"rootSpinRateRadiansPerSecond\":" << motion.rootSpinRate
		<< ",\"rootRotationRadians\":" << motion.rootRotationRadians
		<< ",\"rootAxisRotationRadians\":" << motion.rootAxisRotationRadians
		<< ",\"rootRollingCoupling\":" << motion.rootRollingCoupling
		<< ",\"rootTransverseTravelFraction\":" << motion.rootTransverseTravelFraction
		<< ",\"rootAxisStability\":" << motion.rootAxisStability
		<< ",\"rollingSignatureEnabled\":" << (motion.rollingSignatureEnabled ? "true" : "false")
		<< ",\"rollingSignature\":" << (motion.rollingSignature ? "true" : "false")
		<< ",\"rollingSignatureConfig\":{\"enabled\":" << (motion.rollingSignatureEnabled ? "true" : "false")
		<< ",\"minSpinRateRadiansPerSecond\":" << motion.rollingSignatureMinSpinRate
		<< ",\"minRootRollingCoupling\":" << motion.rollingSignatureMinCoupling
		<< ",\"maxRootRollingCoupling\":" << motion.rollingSignatureMaxCoupling
		<< ",\"minRootTransverseTravelFraction\":" << motion.rollingSignatureMinTransverseTravelFraction
		<< ",\"maxRootAxisStability\":" << motion.rollingSignatureMaxAxisStability
		<< ",\"maxRootTravelAlignment\":" << motion.rollingSignatureMaxTravelAlignment
		<< ",\"minActiveSegmentSimulationUnits\":" << motion.rollingSignatureMinActiveSegment << '}'
		<< ",\"maxCapsuleRotationRateRadiansPerSecond\":" << motion.maximumCapsuleRotationRate
		<< ",\"minJointRotationRateRadiansPerSecond\":" << motion.minimumJointRotationRate
		<< ",\"finalToMaxDistanceRatio\":" << motion.finalToMaxDistanceRatio << "},\n"
		<< " \"displayScale\":" << DISPLAY_SCALE << ",\n"
		<< " \"sourceCoordinateSystem\":{\"upAxis\":\"z\",\"horizontalAxes\":[\"x\",\"y\"],\"units\":\"simulation-units\"},\n"
		<< " \"coordinateSystem\":{\"upAxis\":\"y\",\"horizontalAxes\":[\"x\",\"z\"],\"units\":\"m\"},\n"
		<< " \"objective\":{\"id\":" << jsonString(experiment.get<std::string>("objective.id", "max-horizontal-distance-v1"))
		<< ",\"metric\":\"max-horizontal-distance\"},\n"
		<< " \"physics\":{\"gravityX\":" << physics.get<double>("gravityX", 0.0)
		<< ",\"gravityY\":" << physics.get<double>("gravityY", 0.0)
		<< ",\"gravityZ\":" << physics.get<double>("gravityZ")
		<< ",\"groundFriction\":" << physics.get<double>("groundFriction")
		<< ",\"capsuleFriction\":" << physics.get<double>("capsuleFriction", 0.5)
		<< ",\"capsuleRollingFriction\":" << physics.get<double>("capsuleRollingFriction", 0.0)
		<< ",\"capsuleSpinningFriction\":" << physics.get<double>("capsuleSpinningFriction", 0.0)
		<< ",\"capsuleRestitution\":" << physics.get<double>("capsuleRestitution", 0.0)
		<< ",\"capsuleLinearDamping\":" << physics.get<double>("capsuleLinearDamping", 0.0)
		<< ",\"capsuleAngularDamping\":" << physics.get<double>("capsuleAngularDamping", 0.0)
		<< ",\"capsuleMassScale\":" << physics.get<double>("capsuleMassScale", 0.0001)
		<< ",\"motorMaxForce\":" << physics.get<double>("motorMaxForce")
		<< ",\"motorTargetVelocityLimit\":" << physics.get<double>("motorTargetVelocityLimit", 0.0) << "},\n"
		<< " \"capsules\":[";
	bool first = true;
	for (const pt::ptree::value_type& item : capsules) {
		if (!first) output << ',';
		first = false;
		const auto& capsule = item.second;
		output << "{\"id\":" << jsonString(capsule.get<std::string>("id"))
			<< ",\"innerHeight\":" << capsule.get<double>("innerHeight") * DISPLAY_SCALE
			<< ",\"radius\":" << capsule.get<double>("radius") * DISPLAY_SCALE << '}';
	}
	output << "],\n \"samples\":[\n";
	for (std::size_t sampleIndex = 0; sampleIndex < samples.size(); ++sampleIndex) {
		const ReplaySample& sample = samples[sampleIndex];
		if (sampleIndex > 0) output << ",\n";
		output << "  {\"tick\":" << sample.tick << ",\"poses\":{\"body\":";
		writePose(output, sample.center, btQuaternion(0, 0, 0, 1));
		output << ",\"parts\":{";
		for (std::size_t capsuleIndex = 0; capsuleIndex < sample.capsules.size(); ++capsuleIndex) {
			if (capsuleIndex > 0) output << ',';
			const auto& capsule = sample.capsules[capsuleIndex];
			output << jsonString(capsule.id) << ':';
			writePose(output, capsule.position, capsule.rotation);
		}
		output << "}}}";
	}
	output << "\n ]\n}\n";
	output.flush();
	if (!output)
		throw std::runtime_error("Failed while writing replay output: " + options.output);
	output.close();
	std::filesystem::rename(temporaryPath, outputPath);
}

pt::ptree bestCreature(const pt::ptree& config, double& bestFitness)
{
	bestFitness = -std::numeric_limits<double>::infinity();
	pt::ptree selected;
	for (const pt::ptree::value_type& entry : config.get_child("structure.creatures")) {
		const std::string serializedFitness = entry.second.get<std::string>("fitness", "");
		if (serializedFitness.empty() || serializedFitness == "null")
			continue;
		const double fitness = std::stod(serializedFitness);
		if (std::isfinite(fitness) && fitness > bestFitness) {
			bestFitness = fitness;
			selected = entry.second.get_child("data");
		}
	}
	if (!std::isfinite(bestFitness) || selected.empty())
		throw std::runtime_error("The configuration does not contain a finite saved creature.");
	return selected;
}
}

int main(int argc, char* argv[])
{
	try {
		const Options options = parseOptions(argc, argv);
		pt::ptree config;
		pt::read_json(options.config, config);
		double configuredFitness = 0;
		pt::ptree creatureData = bestCreature(config, configuredFitness);
		const auto& experiment = config.get_child("experiment");
		const auto& physics = experiment.get_child("physics");
		const auto& objective = experiment.get_child("objective");
		const int horizonTicks = experiment.get<int>("objective.horizonTicks");
		const int sampleInterval = FIXED_STEP_HZ / options.sampleHz;

		BulletInterface bullet;
		bullet.init();
		bullet.configure(physics);
		CreatureBase creature(
			&bullet,
			btVector3(0, 0, 0),
			creatureData,
			physics.get<float>("motorMaxForce", 2000.f),
			physics.get<float>("motorTargetVelocityLimit", 0.f));

		MotionMetrics motion;
		motion.initialize(&creature, objective);
		std::vector<ReplaySample> samples;
		samples.reserve(static_cast<std::size_t>(horizonTicks / sampleInterval + 1));
		samples.push_back(ReplaySample{ 0, creature.getCenterOfMassPosition(), creature.getCapsulePoses() });
		for (int tick = 1; tick <= horizonTicks; ++tick) {
			bullet.tick(1.f / FIXED_STEP_HZ);
			creature.tick();
			motion.tick(&creature);
			btVector3 position = creature.getCenterOfMassPosition();
			if (tick % sampleInterval == 0)
				samples.push_back(ReplaySample{ tick, position, creature.getCapsulePoses() });
		}
		motion.finalize(static_cast<double>(horizonTicks) / FIXED_STEP_HZ);
		const double measuredDistance = motion.maxDistance;
		const double measuredFitness = motion.fitness;

		const double parityTolerance = 1e-3 + std::abs(configuredFitness) * 1e-7;
		const double parityError = std::abs(configuredFitness - measuredFitness);
		if (parityError > parityTolerance)
			throw std::runtime_error(
				"Saved fitness does not match deterministic replay. configured=" + std::to_string(configuredFitness) +
				", measured=" + std::to_string(measuredFitness) +
				", absoluteError=" + std::to_string(parityError));

		writeReplay(
			options,
			config,
			creatureData,
			configuredFitness,
			measuredDistance,
			measuredFitness,
			motion,
			horizonTicks,
			samples);
		creature.terminate();
		bullet.destroy();
		std::cout << "Replay exported: " << options.output
			<< " (samples=" << samples.size()
			<< ", configuredFitness=" << configuredFitness
			<< ", measuredDistance=" << measuredDistance
			<< ", measuredFitness=" << measuredFitness << ")\n";
		return 0;
	}
	catch (const std::exception& exception) {
		std::cerr << "replayworker: " << exception.what() << "\n";
		printUsage(argv[0]);
		return 2;
	}
}
