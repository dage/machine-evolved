# This is a test to see how many physics servers that can be run on a single machine
#
# Only one robot is simulated on a single physics server since pyBullet does not provide collision filter and offsetting instances makes it non-deterministic
#
# Results:
#	A test shows that about 600 physics servers can be run simultanously on a 16GB mem laptop (maybe 800 if pushing it).
#	600 physics servers then uses about 60 seconds to simulate 600 robots for 30 real world seconds (60*30=1800 ticks) 
#	each tick then takes about 0.03 seconds. It means estimator predict still takes about 90% of the performance time. :-(
#	TODO: Have to create even bigger batches! Look into pyBullet saveState() and restoreState()!!!!
#		Quick test without verifying the results: 
#
#	After upgrading pyBullet each physics server consumes about 50% more memory. Max now is about 400 physics servers. It's also 20-40% slower than the old version.
#	A single p.saveState() call uses about 100k mem. 

import pybullet as p
import pybullet_data
import time
import math
import statistics
import itertools
import json
import timeit

def printRobotInfo(robotId):
	numJoints = p.getNumJoints(robotId)
	print("Robot imported. Number of joints={}".format(numJoints))
	for i in range(numJoints):
		jointInfo = p.getJointInfo(robotId, i)
		print("  joint {}: {}".format(i, jointInfo))

# Returns the distance between point1 and point2 in the xy-plane. 
def getDistanceXY(point1, point2):
	return math.sqrt((point1[0]-point2[0])**2+((point1[1]-point2[1])**2))

# Returns the standard deviation. If only 1 element, return 0.
def stdev(data):
	if(len(data)==1):
		return 0
	return statistics.stdev(data)

trials = [1,1,2,3,4,5,6,7,8,9,10,20,30,40,50,60,70,80,90,100,200,300]
MAX_FORCE = 10000
startOrientation = p.getQuaternionFromEuler([-0.5,0.5,0])
iterations = 60*30
simulations = []

for numPhysicsServers in trials:
	robots = []
	for i in range(numPhysicsServers):
		physicsClientId = p.connect(p.DIRECT)	# p.GUI (rendered) or p.DIRECT (shell)

		p.setAdditionalSearchPath(pybullet_data.getDataPath()) # used by loadURDF
		p.setGravity(0, 0, -10, physicsClientId=physicsClientId)
		p.loadURDF("plane.urdf", physicsClientId=physicsClientId)

		robots.append({ 
			"id": p.loadMJCF("capsules.xml", flags = p.URDF_USE_SELF_COLLISION_EXCLUDE_ALL_PARENTS, physicsClientId=physicsClientId)[1],
			"maxTravelDistance": 0,
			"physicsClientId": physicsClientId})


	startTime = time.time()
	print("Testing {} simultanous physics servers...".format(numPhysicsServers))
	for i in range(iterations):
		targetPositions = [2.*math.sin(.03*i), 1.4*math.sin(.07*i), 1.7*math.sin(.05*i)]
		for robot in robots:
			p.setJointMotorControlArray(
				robot["id"], 
				[0,1,2],	# joint indices
				controlMode=p.POSITION_CONTROL, 
				targetPositions=targetPositions, 
				forces=[MAX_FORCE, MAX_FORCE, MAX_FORCE],
				physicsClientId=robot["physicsClientId"])
		
			p.stepSimulation(physicsClientId=robot["physicsClientId"])

			# timeit.timeit("")		# Not working with p. Time it manually

			currentPosition = p.getBasePositionAndOrientation(robot["id"], physicsClientId=robot["physicsClientId"])[0]
			distanceTraveled = getDistanceXY(currentPosition, (0,0))
			robot["maxTravelDistance"] = max(robot["maxTravelDistance"], distanceTraveled)
			#print("{}: {}-{}. max={}".format(robot["id"], currentPosition, distanceTraveled, maxTravelDistance))

			#time.sleep(1/60)	# Use with p.connect(p.GUI) 


	deltaTime = time.time() - startTime
	iterationsPerSecondPerRobot = iterations / deltaTime * len(robots)
	realtimeRatioPerRobot = iterationsPerSecondPerRobot / 60.

	for robot in robots:
		robot["deltaPosition"] = p.getBasePositionAndOrientation(robot["id"], physicsClientId=robot["physicsClientId"])[0]
		p.disconnect(physicsClientId=robot["physicsClientId"])
	
	deltaPositions = [robot["deltaPosition"] for robot in robots]
	deltaPositionsX = [p[0] for p in deltaPositions]
	deltaPositionsY = [p[1] for p in deltaPositions]
	simulations.append({
		"numRobots": len(robots),
		"deltaTime": deltaTime,
		"realtimeRatioPerRobot": realtimeRatioPerRobot,
		"maxTravelDistanceMean": statistics.mean([robot["maxTravelDistance"] for robot in robots]),
		"maxTravelDistanceStdDev": stdev([robot["maxTravelDistance"] for robot in robots]),
		"deltaPositionsXMean": statistics.mean(deltaPositionsX),
		"deltaPositionsYMean": statistics.mean(deltaPositionsY),
		"deltaPositionsXStdDev": stdev(deltaPositionsX),
		"deltaPositionsYStdDev": stdev(deltaPositionsY)
	}) 


#finalPositionAndOrientation = p.getBasePositionAndOrientation(robotId)
#print("{} iterations performed in {:.2f} seconds. Realtime ratio: {:.0f} RT".format(iterations, deltaTime, realtimeRatioPerRobot))
#print("Final position: {}. Maximum travel distance: {}".format(endPosition, maxTravelDistance))

print("\n\nSimulations:\n")
for sim in simulations:
	print("{}: {:.0f} RT (total time={:.5f}s), max travel distance {:.3f} (variance {:.10f}), delta position: ({:.3f} (variance {:.10f}), {:.3f} (variance {:.10f}))".format(sim["numRobots"], sim["realtimeRatioPerRobot"], sim["deltaTime"], sim["maxTravelDistanceMean"], sim["maxTravelDistanceStdDev"], sim["deltaPositionsXMean"], sim["deltaPositionsXStdDev"], sim["deltaPositionsYMean"], sim["deltaPositionsYStdDev"]))
