#pragma once

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

#include <boost/property_tree/ptree.hpp>

#include "CreatureBase.h"

namespace pt = boost::property_tree;

class MotionMetrics
{
public:
	void initialize(CreatureBase* creature, const pt::ptree& objective)
	{
		credibleScoring = objective.get<std::string>("id", "max-horizontal-distance-v1") == "credible-grounded-distance-v1";
		clearanceEpsilon = objective.get<double>("credibility.clearanceEpsilonSimulationUnits", 2.0);
		maxSpinRate = objective.get<double>("credibility.maxSpinRateRadiansPerSecond", 10.0);
		maxCapsuleRotationRate = objective.get<double>("credibility.maxCapsuleRotationRateRadiansPerSecond", maxSpinRate);
		maxUnsupportedPathFraction = objective.get<double>("credibility.maxUnsupportedPathFraction", 0.25);
		minFinalToMaxDistanceRatio = objective.get<double>("credibility.minFinalToMaxDistanceRatio", 0.9);

		startingPosition = horizontal(creature->getCenterOfMassPosition());
		previousPosition = startingPosition;
		const auto poses = creature->getCapsulePoses();
		previousRotations.reserve(poses.size());
		capsuleRotationRadians.assign(poses.size(), 0.0);
		for (const auto& pose : poses)
			previousRotations.push_back(normalized(pose.rotation));
	}

	void tick(CreatureBase* creature)
	{
		const btVector3 position = horizontal(creature->getCenterOfMassPosition());
		const double distance = static_cast<double>((position - startingPosition).length());
		maxDistance = std::max(maxDistance, distance);
		finalDistance = distance;
		const double segment = static_cast<double>((position - previousPosition).length());
		pathLength += segment;
		previousPosition = position;

		const auto poses = creature->getCapsulePoses();
		if (poses.size() != previousRotations.size())
			throw std::runtime_error("Capsule count changed while collecting motion metrics.");
		double minimumClearance = std::numeric_limits<double>::infinity();
		for (std::size_t index = 0; index < poses.size(); ++index) {
			const btQuaternion rotation = normalized(poses[index].rotation);
			const btVector3 axis = btMatrix3x3(rotation) * btVector3(0, 0, 1);
			const double clearance = poses[index].position.z()
				- poses[index].radius
				- 0.5 * poses[index].innerHeight * std::abs(static_cast<double>(axis.z()));
			minimumClearance = std::min(minimumClearance, clearance);
			capsuleRotationRadians[index] += quaternionTravel(previousRotations[index], rotation);
			previousRotations[index] = rotation;
		}

		const bool supported = minimumClearance <= clearanceEpsilon;
		if (supported) {
			nearGroundTicks++;
			currentUnsupportedTicks = 0;
		}
		else {
			unsupportedPath += segment;
			currentUnsupportedTicks++;
			longestUnsupportedTicks = std::max(longestUnsupportedTicks, currentUnsupportedTicks);
		}
		ticks++;
	}

	void finalize(double simulatedSeconds)
	{
		finalToMaxDistanceRatio = maxDistance > 0.0 ? finalDistance / maxDistance : 1.0;
		unsupportedPathFraction = pathLength > 0.0 ? unsupportedPath / pathLength : 0.0;
		nearGroundTimeFraction = ticks > 0 ? static_cast<double>(nearGroundTicks) / ticks : 1.0;
		longestUnsupportedSeconds = ticks > 0 ? simulatedSeconds * longestUnsupportedTicks / ticks : 0.0;
		capsuleRotationRates.clear();
		capsuleRotationRates.reserve(capsuleRotationRadians.size());
		for (const double rotation : capsuleRotationRadians)
			capsuleRotationRates.push_back(simulatedSeconds > 0.0 ? rotation / simulatedSeconds : 0.0);
		rootSpinRate = capsuleRotationRates.empty() ? 0.0 : capsuleRotationRates.front();
		maximumCapsuleRotationRate = capsuleRotationRates.empty()
			? 0.0
			: *std::max_element(capsuleRotationRates.begin(), capsuleRotationRates.end());
		credible = !credibleScoring || (
			rootSpinRate <= maxSpinRate
			&& maximumCapsuleRotationRate <= maxCapsuleRotationRate
			&& unsupportedPathFraction <= maxUnsupportedPathFraction
			&& finalToMaxDistanceRatio >= minFinalToMaxDistanceRatio);
		fitness = credible ? maxDistance : 0.0;
	}

	bool credibleScoring = false;
	bool credible = true;
	double maxDistance = 0.0;
	double finalDistance = 0.0;
	double pathLength = 0.0;
	double unsupportedPathFraction = 0.0;
	double nearGroundTimeFraction = 1.0;
	double longestUnsupportedSeconds = 0.0;
	double finalToMaxDistanceRatio = 1.0;
	double rootSpinRate = 0.0;
	double maximumCapsuleRotationRate = 0.0;
	double fitness = 0.0;
	std::vector<double> capsuleRotationRates;

private:
	static btVector3 horizontal(btVector3 value)
	{
		value.setZ(0);
		return value;
	}

	static btQuaternion normalized(btQuaternion value)
	{
		value.normalize();
		return value;
	}

	static double quaternionTravel(const btQuaternion& previous, const btQuaternion& current)
	{
		const double dot = std::abs(static_cast<double>(previous.dot(current)));
		return 2.0 * std::acos(std::max(-1.0, std::min(1.0, dot)));
	}

	double clearanceEpsilon = 2.0;
	double maxSpinRate = 10.0;
	double maxCapsuleRotationRate = 10.0;
	double maxUnsupportedPathFraction = 0.25;
	double minFinalToMaxDistanceRatio = 0.9;
	btVector3 startingPosition;
	btVector3 previousPosition;
	double unsupportedPath = 0.0;
	std::vector<btQuaternion> previousRotations;
	std::vector<double> capsuleRotationRadians;
	int ticks = 0;
	int nearGroundTicks = 0;
	int currentUnsupportedTicks = 0;
	int longestUnsupportedTicks = 0;
};
