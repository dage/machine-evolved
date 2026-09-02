#pragma once

#include <algorithm>
#include <cmath>
#include <initializer_list>
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
		minJointRotationRate = objective.get<double>("credibility.minJointRotationRateRadiansPerSecond", 0.0);
		rollingDiscountEnabled = false;
		rollingDiscountLambda = 1.0;
		rollingDiscountPower = 1.0;
		rollingDiscountEpsilon = 1e-6;
		if (credibleScoring) {
			if (auto configuredRollingDiscount = objective.get_child_optional("credibility.rollingDiscount")) {
				const pt::ptree& rolling = configuredRollingDiscount.get();
				rollingDiscountEnabled = rolling.get<bool>("enabled", true);
				rollingDiscountLambda = configuredDouble(rolling, "lambda", 1.0);
				rollingDiscountPower = configuredDouble(rolling, "power", 1.0);
				rollingDiscountEpsilon = configuredDouble(rolling, "epsilonSimulationUnits", 1e-6);
			}
		}
		if (!std::isfinite(rollingDiscountLambda) || rollingDiscountLambda < 0.0)
			rollingDiscountLambda = 1.0;
		if (!std::isfinite(rollingDiscountPower) || rollingDiscountPower <= 0.0)
			rollingDiscountPower = 1.0;
		if (!std::isfinite(rollingDiscountEpsilon) || rollingDiscountEpsilon < 0.0)
			rollingDiscountEpsilon = 1e-6;

		// The rolling signature is deliberately opt-in.  Existing distance-only
		// and credible campaigns without this block retain their prior behavior.
		rollingSignatureEnabled = false;
		rollingSignatureMinSpinRate = 1.0;
		rollingSignatureMinCoupling = 0.8;
		rollingSignatureMaxCoupling = 1.2;
		rollingSignatureMinTransverseTravelFraction = 0.8;
		rollingSignatureMaxAxisStability = 0.2;
		rollingSignatureMaxTravelAlignment = 0.25;
		rollingSignatureMinActiveSegment = 0.0;
		if (auto configuredRollingSignature = objective.get_child_optional("credibility.rollingSignature")) {
			const pt::ptree& rolling = configuredRollingSignature.get();
			rollingSignatureEnabled = rolling.get<bool>("enabled", true);
			rollingSignatureMinSpinRate = configuredDouble(
				rolling, { "minSpinRateRadiansPerSecond", "minRootSpinRateRadiansPerSecond" }, 1.0);
			rollingSignatureMinCoupling = configuredDouble(rolling, "minRootRollingCoupling", 0.8);
			rollingSignatureMaxCoupling = configuredDouble(rolling, "maxRootRollingCoupling", 1.2);
			rollingSignatureMinTransverseTravelFraction = configuredDouble(
				rolling, "minRootTransverseTravelFraction", 0.8);
			rollingSignatureMaxAxisStability = configuredDouble(rolling, "maxRootAxisStability", 0.2);
			rollingSignatureMaxTravelAlignment = configuredDouble(rolling, "maxRootTravelAlignment", 0.25);
			rollingSignatureMinActiveSegment = configuredDouble(
				rolling, "minActiveSegmentSimulationUnits", 0.0);
		}

		maxDistance = 0.0;
		finalDistance = 0.0;
		pathLength = 0.0;
		unsupportedPath = 0.0;
		unsupportedPathFraction = 0.0;
		nearGroundTimeFraction = 1.0;
		longestUnsupportedSeconds = 0.0;
		finalToMaxDistanceRatio = 1.0;
		rootSpinRate = 0.0;
		rootRotationRadians = 0.0;
		rootAxisRotationRadians = 0.0;
		rootRollingCoupling = 0.0;
		rootTransverseTravelFraction = 0.0;
		rootAxisStability = 0.0;
		rollingExplainedDistance = 0.0;
		rollingExplainedFraction = 0.0;
		maximumCapsuleRotationRate = 0.0;
		minimumJointRotationRate = 0.0;
		fitness = 0.0;
		credible = true;
		rollingSignature = false;
		previousRotations.clear();
		previousRelativeRotations.clear();
		capsuleRotationRadians.clear();
		jointRotationRadians.clear();
		capsuleRotationRates.clear();
		jointRotationRates.clear();
		transverseTravel = 0.0;
		activePathLength = 0.0;
		ticks = 0;
		nearGroundTicks = 0;
		currentUnsupportedTicks = 0;
		longestUnsupportedTicks = 0;

		startingPosition = horizontal(creature->getCenterOfMassPosition());
		previousPosition = startingPosition;
		const auto poses = creature->getCapsulePoses();
		previousRotations.reserve(poses.size());
		capsuleRotationRadians.assign(poses.size(), 0.0);
		for (const auto& pose : poses)
			previousRotations.push_back(normalized(pose.rotation));
		rootRadius = poses.empty() ? 0.0 : static_cast<double>(poses.front().radius);
		previousRootAxis = poses.empty()
			? btVector3(0, 0, 1)
			: capsuleAxis(previousRotations.front());
		jointRotationRadians.assign(poses.size() > 1 ? poses.size() - 1 : 0, 0.0);
		previousRelativeRotations.reserve(jointRotationRadians.size());
		for (std::size_t index = 0; index + 1 < previousRotations.size(); ++index)
			previousRelativeRotations.push_back(relative(previousRotations[index], previousRotations[index + 1]));
	}

	void tick(CreatureBase* creature)
	{
		const btVector3 position = horizontal(creature->getCenterOfMassPosition());
		const double distance = static_cast<double>((position - startingPosition).length());
		maxDistance = std::max(maxDistance, distance);
		finalDistance = distance;
		const double segment = static_cast<double>((position - previousPosition).length());
		pathLength += segment;

		const auto poses = creature->getCapsulePoses();
		if (poses.size() != previousRotations.size())
			throw std::runtime_error("Capsule count changed while collecting motion metrics.");
		double minimumClearance = std::numeric_limits<double>::infinity();
		btVector3 currentRootAxis = previousRootAxis;
		double rootRotationStep = 0.0;
		for (std::size_t index = 0; index < poses.size(); ++index) {
			const btQuaternion rotation = normalized(poses[index].rotation);
			const btVector3 axis = capsuleAxis(rotation);
			const double clearance = poses[index].position.z()
				- poses[index].radius
				- 0.5 * poses[index].innerHeight * std::abs(static_cast<double>(axis.z()));
			minimumClearance = std::min(minimumClearance, clearance);
			capsuleRotationRadians[index] += quaternionTravel(previousRotations[index], rotation);
			if (index == 0) {
				rootRotationStep = quaternionTravel(previousRotations[index], rotation);
				rootRotationRadians += rootRotationStep;
				rootAxisRotationRadians += axisTravel(previousRootAxis, axis);
				currentRootAxis = axis;
			}
			previousRotations[index] = rotation;
		}
		for (std::size_t index = 0; index + 1 < previousRotations.size(); ++index) {
			const btQuaternion currentRelative = relative(previousRotations[index], previousRotations[index + 1]);
			jointRotationRadians[index] += quaternionTravel(previousRelativeRotations[index], currentRelative);
			previousRelativeRotations[index] = currentRelative;
		}
		if (!poses.empty()) {
			const double activeSegment = segment > rollingSignatureMinActiveSegment ? segment : 0.0;
			activePathLength += activeSegment;
			const btVector3 horizontalAxis(currentRootAxis.x(), currentRootAxis.y(), 0);
			const btVector3 horizontalTravel(position.x() - previousPosition.x(), position.y() - previousPosition.y(), 0);
			const double axisLength = static_cast<double>(horizontalAxis.length());
			const double travelLength = static_cast<double>(horizontalTravel.length());
			if (segment > 0.0 && axisLength > 0.0 && travelLength > 0.0) {
				const double alignment = std::abs(static_cast<double>(horizontalAxis.dot(horizontalTravel)))
					/ (axisLength * travelLength);
				const double transverseWeight = std::max(0.0, 1.0 - alignment * alignment);
				const double rollingDisplacement = rootRadius
					* rootRotationStep
					* axisLength * transverseWeight;
				const double explained = segment
					* (1.0 - std::exp(-rollingDisplacement / (segment + rollingDiscountEpsilon)));
				rollingExplainedDistance += std::isfinite(explained) ? explained : 0.0;
			}
			if (activeSegment > 0.0 && axisLength > 0.0 && travelLength > 0.0) {
				const double alignment = std::abs(static_cast<double>(horizontalAxis.dot(horizontalTravel)))
					/ (axisLength * travelLength);
				if (alignment <= rollingSignatureMaxTravelAlignment)
					transverseTravel += activeSegment;
			}
			previousRootAxis = currentRootAxis;
		}
		previousPosition = position;

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
		jointRotationRates.clear();
		jointRotationRates.reserve(jointRotationRadians.size());
		for (const double rotation : jointRotationRadians)
			jointRotationRates.push_back(simulatedSeconds > 0.0 ? rotation / simulatedSeconds : 0.0);
		minimumJointRotationRate = jointRotationRates.empty()
			? 0.0
			: *std::min_element(jointRotationRates.begin(), jointRotationRates.end());
		rootRollingCoupling = rootRotationRadians > 0.0 && rootRadius > 0.0
			? pathLength / (rootRotationRadians * rootRadius)
			: 0.0;
		rootTransverseTravelFraction = activePathLength > 0.0
			? transverseTravel / activePathLength
			: 0.0;
		rootAxisStability = rootRotationRadians > 0.0
			? rootAxisRotationRadians / rootRotationRadians
			: 0.0;
		rollingExplainedFraction = pathLength > 0.0
			? std::max(0.0, std::min(1.0, rollingExplainedDistance / pathLength))
			: 0.0;
		rollingSignature = rollingSignatureEnabled &&
			rootSpinRate >= rollingSignatureMinSpinRate &&
			rootRollingCoupling >= rollingSignatureMinCoupling &&
			rootRollingCoupling <= rollingSignatureMaxCoupling &&
			rootTransverseTravelFraction >= rollingSignatureMinTransverseTravelFraction &&
			rootAxisStability <= rollingSignatureMaxAxisStability;
		credible = !credibleScoring || (
			rootSpinRate <= maxSpinRate
			&& maximumCapsuleRotationRate <= maxCapsuleRotationRate
			&& unsupportedPathFraction <= maxUnsupportedPathFraction
			&& finalToMaxDistanceRatio >= minFinalToMaxDistanceRatio
			&& minimumJointRotationRate >= minJointRotationRate
			&& !rollingSignature);
		if (!credible)
			fitness = 0.0;
		else if (rollingDiscountEnabled)
			fitness = maxDistance * std::pow(
				std::max(0.0, 1.0 - rollingDiscountLambda * rollingExplainedFraction),
				rollingDiscountPower);
		else
			fitness = maxDistance;
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
	double rootRotationRadians = 0.0;
	double rootAxisRotationRadians = 0.0;
	double rootRollingCoupling = 0.0;
	double rootTransverseTravelFraction = 0.0;
	double rootAxisStability = 0.0;
	double rollingExplainedFraction = 0.0;
	double maximumCapsuleRotationRate = 0.0;
	double minimumJointRotationRate = 0.0;
	double fitness = 0.0;
	bool rollingSignatureEnabled = false;
	bool rollingSignature = false;
	double rollingSignatureMinSpinRate = 1.0;
	double rollingSignatureMinCoupling = 0.8;
	double rollingSignatureMaxCoupling = 1.2;
	double rollingSignatureMinTransverseTravelFraction = 0.8;
	double rollingSignatureMaxAxisStability = 0.2;
	double rollingSignatureMaxTravelAlignment = 0.25;
	double rollingSignatureMinActiveSegment = 0.0;
	bool rollingDiscountEnabled = false;
	double rollingDiscountLambda = 1.0;
	double rollingDiscountPower = 1.0;
	double rollingDiscountEpsilon = 1e-6;
	std::vector<double> capsuleRotationRates;
	std::vector<double> jointRotationRates;

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

	static btVector3 capsuleAxis(const btQuaternion& rotation)
	{
		return btMatrix3x3(rotation) * btVector3(0, 0, 1);
	}

	static double quaternionTravel(const btQuaternion& previous, const btQuaternion& current)
	{
		const double dot = std::abs(static_cast<double>(previous.dot(current)));
		return 2.0 * std::acos(std::max(-1.0, std::min(1.0, dot)));
	}

	static double axisTravel(const btVector3& previous, const btVector3& current)
	{
		const double previousLength = static_cast<double>(previous.length());
		const double currentLength = static_cast<double>(current.length());
		if (previousLength <= 0.0 || currentLength <= 0.0)
			return 0.0;
		const double dot = std::abs(static_cast<double>(previous.dot(current)))
			/ (previousLength * currentLength);
		return std::acos(std::max(-1.0, std::min(1.0, dot)));
	}

	static double configuredDouble(const pt::ptree& config, const char* key, double fallback)
	{
		try {
			return config.get<double>(key, fallback);
		}
		catch (const boost::property_tree::ptree_bad_data&) {
			return fallback;
		}
	}

	static double configuredDouble(
		const pt::ptree& config,
		std::initializer_list<const char*> keys,
		double fallback)
	{
		for (const char* key : keys) {
			if (auto value = config.get_optional<double>(key))
				return *value;
		}
		return fallback;
	}

	static btQuaternion relative(const btQuaternion& parent, const btQuaternion& child)
	{
		return normalized(parent.inverse() * child);
	}

	double clearanceEpsilon = 2.0;
	double maxSpinRate = 10.0;
	double maxCapsuleRotationRate = 10.0;
	double maxUnsupportedPathFraction = 0.25;
	double minFinalToMaxDistanceRatio = 0.9;
	double minJointRotationRate = 0.0;
	btVector3 startingPosition;
	btVector3 previousPosition;
	btVector3 previousRootAxis;
	double rootRadius = 0.0;
	double unsupportedPath = 0.0;
	double transverseTravel = 0.0;
	double activePathLength = 0.0;
	double rollingExplainedDistance = 0.0;
	std::vector<btQuaternion> previousRotations;
	std::vector<double> capsuleRotationRadians;
	std::vector<btQuaternion> previousRelativeRotations;
	std::vector<double> jointRotationRadians;
	int ticks = 0;
	int nearGroundTicks = 0;
	int currentUnsupportedTicks = 0;
	int longestUnsupportedTicks = 0;
};
