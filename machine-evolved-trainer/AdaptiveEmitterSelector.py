import math


class AdaptiveEmitterSelector:
	"""Sliding-window UCB selector over fixed, topology-agnostic emitter IDs."""

	SCHEMA_VERSION = 1
	STRATEGY = "sliding-window-ucb-v1"
	ARMS = (
		"small-independent",
		"large-independent",
		"fresh-template",
		"small-shared",
	)

	def __init__(self, config):
		self.config = config
		strategy = config.get("strategy", self.STRATEGY)
		if strategy != self.STRATEGY:
			raise ValueError("Unknown adaptive emitter selector strategy: {}".format(strategy))
		self.windowSize = int(config.get("windowSize", 64))
		self.warmupSelectionsPerArm = int(config.get("warmupSelectionsPerArm", 1))
		self.minExplorationRate = float(config.get("minExplorationRate", 0.05))
		self.ucbExploration = float(config.get("ucbExploration", math.sqrt(2.0)))
		self.rewardClip = float(config.get("rewardClip", 1.0))
		if self.windowSize < 1:
			raise ValueError("adaptiveSelector.windowSize must be positive")
		if self.warmupSelectionsPerArm < 1:
			raise ValueError("adaptiveSelector.warmupSelectionsPerArm must be positive")
		if self.minExplorationRate < 0.05 or self.minExplorationRate * len(self.ARMS) >= 1.0:
			raise ValueError("adaptiveSelector.minExplorationRate must be at least 0.05 and leave room for UCB")
		if self.ucbExploration < 0 or self.rewardClip <= 0:
			raise ValueError("adaptiveSelector UCB exploration and reward clip must be non-negative and positive")

		state = config.get("state")
		if state is None:
			state = self._newState()
			config["state"] = state
		self._validateState(state)
		self.state = state

	def _newState(self):
		return {
			"schemaVersion": self.SCHEMA_VERSION,
			"totalSelections": 0,
			"totalAttempts": 0,
			"totalOutcomes": 0,
			"totalFailures": 0,
			"totalInvalidOutcomes": 0,
			"totalPositiveQdGain": 0.0,
			"totalNormalizedReward": 0.0,
			"currentBest": None,
			"rewardWindow": [],
			"arms": {
				emitterId: {
					"selections": 0,
					"attempts": 0,
					"outcomes": 0,
					"failures": 0,
					"invalidOutcomes": 0,
					"positiveQdGain": 0.0,
					"normalizedReward": 0.0,
					"coverageGains": 0,
					"replacements": 0,
					"rejections": 0,
					"globalBests": 0,
				}
				for emitterId in self.ARMS
			},
		}

	def _validateState(self, state):
		if int(state.get("schemaVersion", 0)) != self.SCHEMA_VERSION:
			raise ValueError("Unsupported adaptive emitter selector state schema")
		if set(state.get("arms", {})) != set(self.ARMS):
			raise ValueError("Adaptive emitter selector state has different arms")
		for key in ("totalAttempts", "totalFailures", "totalInvalidOutcomes"):
			state.setdefault(key, 0)
		for key in ("totalPositiveQdGain", "totalNormalizedReward"):
			state.setdefault(key, 0.0)
		rewardWindow = state.get("rewardWindow")
		if not isinstance(rewardWindow, list) or len(rewardWindow) > self.windowSize:
			raise ValueError("Adaptive emitter selector reward window is invalid")
		for observation in rewardWindow:
			if observation.get("emitterId") not in self.ARMS or not math.isfinite(float(observation.get("reward"))):
				raise ValueError("Adaptive emitter selector reward observation is invalid")
		for emitterId in self.ARMS:
			arm = state["arms"][emitterId]
			for key in ("attempts", "failures", "invalidOutcomes", "rejections", "globalBests"):
				arm.setdefault(key, 0)
			for key in ("positiveQdGain", "normalizedReward"):
				arm.setdefault(key, 0.0)
			for key in ("selections", "attempts", "outcomes", "failures", "invalidOutcomes", "coverageGains", "replacements", "rejections", "globalBests"):
				if int(arm.get(key, -1)) < 0:
					raise ValueError("Adaptive emitter selector state contains a negative count")
			for key in ("positiveQdGain", "normalizedReward"):
				if not math.isfinite(float(arm[key])) or float(arm[key]) < 0:
					raise ValueError("Adaptive emitter selector state contains an invalid gain")

	def _leastSelected(self, emitterIds):
		return min(emitterIds, key=lambda emitterId: (self.state["arms"][emitterId]["selections"], self.ARMS.index(emitterId)))

	def _floorArm(self):
		total = int(self.state["totalSelections"])
		deadlines = {
			emitterId: int(math.floor(int(self.state["arms"][emitterId]["selections"]) / self.minExplorationRate)) + 1
			for emitterId in self.ARMS
		}
		for deadline in sorted(set(deadlines.values())):
			due = [emitterId for emitterId in self.ARMS if deadlines[emitterId] <= deadline]
			remainingSlots = deadline - total
			if len(due) >= remainingSlots:
				return min(due, key=lambda emitterId: (deadlines[emitterId], self.state["arms"][emitterId]["selections"], self.ARMS.index(emitterId)))
		return None

	def _recentRewards(self, emitterId):
		return [
			observation["reward"] for observation in self.state["rewardWindow"]
			if observation["emitterId"] == emitterId
		]

	def _feedbackBalancedArm(self):
		withoutFeedback = [emitterId for emitterId in self.ARMS if not self._recentRewards(emitterId)]
		if not self.state["rewardWindow"]:
			return min(
				self.ARMS,
				key=lambda emitterId: (
					self.state["arms"][emitterId]["selections"] - self.state["arms"][emitterId]["outcomes"],
					self.state["arms"][emitterId]["selections"],
					self.ARMS.index(emitterId),
				))
		ready = [
			emitterId for emitterId in withoutFeedback
			if self.state["arms"][emitterId]["selections"] == self.state["arms"][emitterId]["outcomes"]
		]
		return self._leastSelected(ready) if ready else None

	def _ucbScore(self, emitterId):
		rewards = self._recentRewards(emitterId)
		if not rewards:
			return float("-inf")
		meanReward = sum(rewards) / len(rewards)
		total = max(2, len(self.state["rewardWindow"]))
		return meanReward + self.ucbExploration * math.sqrt(math.log(total) / len(rewards))

	def selectEmitter(self, controllerSignatureOrLength, morphologyId):
		"""Select an emitter using only opaque controller and morphology context."""
		# The context is deliberately accepted but not inspected. It makes the
		# selector safe for arbitrary parameter counts and morphology identifiers.
		_ = controllerSignatureOrLength, morphologyId
		underWarmup = [
			emitterId for emitterId in self.ARMS
			if int(self.state["arms"][emitterId]["selections"]) < self.warmupSelectionsPerArm
		]
		if underWarmup:
			emitterId = self._leastSelected(underWarmup)
		else:
			emitterId = self._floorArm()
			if emitterId is None:
				emitterId = self._feedbackBalancedArm()
			if emitterId is None:
				emitterId = max(self.ARMS, key=lambda candidate: (self._ucbScore(candidate), -self.ARMS.index(candidate)))

		self.state["arms"][emitterId]["selections"] += 1
		self.state["totalSelections"] += 1
		return emitterId

	def recordAttempt(self, emitterId):
		if emitterId not in self.state["arms"]:
			return False
		self.state["arms"][emitterId]["attempts"] += 1
		self.state["totalAttempts"] += 1
		return True

	def recordFailure(self, emitterId, invalidOutcome=False):
		if emitterId not in self.state["arms"]:
			return False
		arm = self.state["arms"][emitterId]
		arm["failures"] += 1
		self.state["totalFailures"] += 1
		if invalidOutcome:
			arm["invalidOutcomes"] += 1
			self.state["totalInvalidOutcomes"] += 1
		return True

	def recordOutcome(self, controllerSignatureOrLength, morphologyId, fitness, descriptor, insertionResult, qdDelta, emitterId):
		"""Record one completed emission without receiving creature topology."""
		_ = controllerSignatureOrLength, morphologyId, descriptor
		fitness = float(fitness)
		self.observeFitness(fitness)
		if emitterId not in self.state["arms"]:
			return None
		qdDelta = float(qdDelta)
		currentBest = self.state["currentBest"]
		denominator = max(abs(float(currentBest)), 1e-12)
		reward = max(0.0, qdDelta) / denominator
		reward = max(0.0, min(self.rewardClip, reward))

		arm = self.state["arms"][emitterId]
		arm["outcomes"] += 1
		positiveQdGain = max(0.0, qdDelta)
		arm["positiveQdGain"] += positiveQdGain
		arm["normalizedReward"] += reward
		self.state["totalPositiveQdGain"] += positiveQdGain
		self.state["totalNormalizedReward"] += reward
		if bool(insertionResult.get("coverageGain", False)):
			arm["coverageGains"] += 1
		if bool(insertionResult.get("replacement", False)):
			arm["replacements"] += 1
		if insertionResult.get("outcome") == "rejected":
			arm["rejections"] += 1
		if bool(insertionResult.get("newGlobalBest", False)):
			arm["globalBests"] += 1
		self.state["rewardWindow"].append({"emitterId": emitterId, "reward": reward})
		if len(self.state["rewardWindow"]) > self.windowSize:
			del self.state["rewardWindow"][:-self.windowSize]
		self.state["totalOutcomes"] += 1
		return reward

	def observeFitness(self, fitness):
		"""Synchronize the scalar best when enabling the selector on an archive."""
		fitness = float(fitness)
		if not math.isfinite(fitness):
			return
		currentBest = self.state.get("currentBest")
		if currentBest is None or fitness > float(currentBest):
			self.state["currentBest"] = fitness

	def getState(self):
		return self.state
