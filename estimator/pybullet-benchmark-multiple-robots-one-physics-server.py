# This is a test to see how many simulations can be executed simultanously on a single physics server instance.
#
# No collision filtering is available in pyBullet so it's attempted to simultanously show many different robots at non-overlapping positions.
#
# Two approaces are examined:
#	1.) Running several different robots in the same simulator instance
#		- See if collisions between robots can be ignored. If not, then try to position robots so far apart that they will never interact
#	2.) Run several different simulator instanses simultanously. This will exploit the multi-threading capabilities of modern CPUs
#
# Testing to see if simulations are deterministic 01.05.2018 by looking at the final position and orientation when the simulation completes:
#	* Deterministic between runs when time.sleep() is enabled/disabled
#	* When offsetting start position it is deterministic with none-offseted the first 10 decimals, but only if one robot is shown at a time
#  
# .mjcf is even less deterministic!!!!
# Since collision filters are not yet implemented in pyBullet, this approach is a FAIL!!!!!!
# Test instead with lots of simultanous physics simulation servers - see how many can be used simultanously
#
# A test run 02.05.2018 gave the following result:
# 1: 434 RT, max travel distance 6.522 (variance 0.0000000000), delta position: (0.476 (variance 0.0000000000), -6.181 (variance 0.0000000000))
# 2: 549 RT, max travel distance 7.682 (variance 0.0001117975), delta position: (1.561 (variance 0.0000455264), -7.522 (variance 0.0001047321))
# 3: 488 RT, max travel distance 8.914 (variance 0.0002060714), delta position: (-0.729 (variance 0.0003222933), -8.884 (variance 0.0002332073))
# 4: 650 RT, max travel distance 6.582 (variance 0.0110292358), delta position: (1.240 (variance 0.0165707561), -6.464 (variance 0.0080355848))
# 5: 671 RT, max travel distance 8.910 (variance 0.0000024154), delta position: (-0.713 (variance 0.0000109563), -8.882 (variance 0.0000015437))
# 6: 696 RT, max travel distance 6.970 (variance 0.0000004608), delta position: (-0.523 (variance 0.0000003775), -6.950 (variance 0.0000004905))
# 7: 667 RT, max travel distance 9.121 (variance 0.0081321685), delta position: (-1.743 (variance 0.0221885540), -8.953 (variance 0.0042262842))
# 8: 692 RT, max travel distance 9.406 (variance 0.0003063883), delta position: (0.068 (variance 0.0000477919), -9.406 (variance 0.0003060529))
# 9: 665 RT, max travel distance 9.601 (variance 0.0002619004), delta position: (-2.209 (variance 0.0003674393), -9.343 (variance 0.0003557486))
# 10: 719 RT, max travel distance 9.894 (variance 0.0000158994), delta position: (-2.196 (variance 0.0000171402), -9.647 (variance 0.0000202081))
# 20: 751 RT, max travel distance 5.815 (variance 0.0001537455), delta position: (-0.628 (variance 0.0000460883), -5.781 (variance 0.0001496420))
# 30: 757 RT, max travel distance 6.639 (variance 0.0000105111), delta position: (-0.166 (variance 0.0000472267), -6.637 (variance 0.0000093344))
# 40: 725 RT, max travel distance 5.848 (variance 0.0000027684), delta position: (-0.745 (variance 0.0000144432), -5.774 (variance 0.0000201265))
# 50: 719 RT, max travel distance 6.210 (variance 0.0000994576), delta position: (-0.248 (variance 0.0002708210), -6.205 (variance 0.0000887173))
# 60: 714 RT, max travel distance 6.382 (variance 0.0000004293), delta position: (-0.357 (variance 0.0000003863), -6.372 (variance 0.0000004516))
# 70: 751 RT, max travel distance 7.487 (variance 0.0091385411), delta position: (-1.505 (variance 0.0013577212), -7.334 (variance 0.0090503502))
# 80: 733 RT, max travel distance 7.556 (variance 0.0000614504), delta position: (-1.515 (variance 0.0000045652), -7.402 (variance 0.0000617928))
# 90: 742 RT, max travel distance 7.298 (variance 0.0145444562), delta position: (-2.145 (variance 0.0034856122), -6.975 (variance 0.0145620508))
# 100: 744 RT, max travel distance 6.678 (variance 0.0000003431), delta position: (-0.919 (variance 0.0000002839), -6.570 (variance 0.0000017496))
# 200: 706 RT, max travel distance 7.659 (variance 0.0019613219), delta position: (1.469 (variance 0.0051761900), -7.517 (variance 0.0013401017))
# 300: 662 RT, max travel distance 6.802 (variance 0.0000827644), delta position: (-0.359 (variance 0.0000539483), -6.793 (variance 0.0000800324))
# 400: 639 RT, max travel distance 7.302 (variance 0.0020926297), delta position: (-0.037 (variance 0.0006648771), -7.302 (variance 0.0020959145))
# 500: 619 RT, max travel distance 7.932 (variance 0.0001338941), delta position: (0.795 (variance 0.0000877337), -7.892 (variance 0.0001257338))#
#
# ==> Even in a best case scenario, the performance increase is less than 2x. For mjcf files, there is a performance decrease per robot by using several simultanously

import pybullet as p
import pybullet_data
import time
import math
import statistics
import itertools
import json

def printRobotInfo(robotId):
	numJoints = p.getNumJoints(robotId)
	print("Robot imported. Number of joints={}".format(numJoints))
	for i in range(numJoints):
		jointInfo = p.getJointInfo(robotId, i)
		print("  joint {}: {}".format(i, jointInfo))

def getActiveJointIndices(robotId):
	indices = []
	for i in range(p.getNumJoints(robotId)):
		jointInfo = p.getJointInfo(robotId, i)
		if jointInfo[2] == p.JOINT_REVOLUTE:	# Currently only hinge/revolute supported
			indices.append(i)
	return indices

# Returns the distance between point1 and point2 in the xy-plane. 
def getDistanceXY(point1, point2):
	return math.sqrt((point1[0]-point2[0])**2+((point1[1]-point2[1])**2))

# Returns the standard deviation. If only 1 element, return 0.
def stdev(data):
	if(len(data)==1):
		return 0
	return statistics.stdev(data)

physicsClient = p.connect(p.GUI)	# p.GUI (rendered) or p.DIRECT (shell)
p.setAdditionalSearchPath(pybullet_data.getDataPath()) # used by loadURDF
p.setGravity(0,0,-10)
planeId = p.loadURDF("plane.urdf", globalScaling=2.)
#planeId = p.loadURDF("plane.urdf")

startOrientation = p.getQuaternionFromEuler([-0.5,0.5,0])
iterations = 60*30
robotSeperation = 50	# Distance between robots. They move identical so they can be close, but experiment with large values to see how deterministic this approach is for a real world case
startPositionPermutations = list(itertools.product([n*robotSeperation for n in range(0, 23)], repeat=2))
numRobotsToTest = [1, 2, 3, 4] # [1,2,3,4,5,6,7,8,9,10,20,30,40,50,60,70,80,90,100,200,300,400,500]	
simulations = []

for numRobots in numRobotsToTest:
	robots = []

	for robotIndex in range(numRobots):
		startPosition = (0,0)
		robots.append({ 
			# TODO: loadMJCF doesn't support basePosition, so need to work around. Make lots of temp files based on xml template in memory
			"id": p.loadMJCF("capsules-{}.xml".format(robotIndex).format(robotIndex), flags = p.URDF_USE_SELF_COLLISION_EXCLUDE_ALL_PARENTS)[1],
			#"id": p.loadURDF("2-capsules.urdf", [startPosition[0], startPosition[1], 1], startOrientation),
			"startPosition": startPosition,
			"maxTravelDistance": 0})
	#printRobotInfo(robots[0]["id"])

	startTime = time.time()
	for i in range(iterations):
		#target = math.sin(.03*i)
		#torque = [10*target, 15*target, 25*target]
		
		#for robot in robots:
		#	p.applyExternalTorque(robot["id"], 0, torque, p.LINK_FRAME)

		#   OOOOPS!!! p.applyExternalTorque(robot["id"], 0, torque, p.LINK_FRAME) on one robot moves other robots where no force is applied!!! WOW!!! Lucikly it's not how I'm doing it in the current reinforcement prototype
		#p.applyExternalTorque(robots[0]["id"], 0, torque, p.LINK_FRAME)
		#print("robot position {},{}: {}, {}".format(robots[0]["id"], robots[1]["id"], p.getBasePositionAndOrientation(robots[0]["id"])[0], p.getBasePositionAndOrientation(robots[1]["id"])[0]))

		#numJoints = p.getNumJoints(robots[0]["id"])
		#jointIndices = getActiveJointIndices(robots[0]["id"])

		
		MAX_FORCE = 10000
		targetPositions = [2.*math.sin(.03*i), 1.4*math.sin(.07*i), 1.7*math.sin(.05*i)]
		for robot in robots:
			p.setJointMotorControlArray(
				robot["id"], 
				[0,1,2],	# joint indices
				controlMode=p.POSITION_CONTROL, 
				targetPositions=targetPositions, 
				forces=[MAX_FORCE, MAX_FORCE, MAX_FORCE])
		
		#print("robot position {},{}: {}, {}".format(robots[0]["id"], robots[1]["id"], p.getBasePositionAndOrientation(robots[0]["id"])[0], p.getBasePositionAndOrientation(robots[1]["id"])[0]))

		p.stepSimulation()

		# TODO: 
		#	* Detect if a collision happened!! If so, invalidate the robot or the whole simulation
		#	* Do more logic for checking consistancy and determinism. Examine every robot creature
		#	* Run several simultanous physics servers. Is module on robot index to decide which server to use, so that for 3 servers order for robots are 1,2,3, 1,2,3, 1,2,3

		for robot in robots:
			currentPosition = p.getBasePositionAndOrientation(robot["id"])[0]
			distanceTraveled = getDistanceXY(currentPosition, robot["startPosition"])
			robot["maxTravelDistance"] = max(robot["maxTravelDistance"], distanceTraveled)
			#print("{}: {}-{}. max={}".format(robot["id"], currentPosition, distanceTraveled, maxTravelDistance))

		time.sleep(1/60)	# Use with p.connect(p.GUI) 


	deltaTime = time.time() - startTime
	iterationsPerSecondPerRobot = iterations / deltaTime * numRobots
	realtimeRatioPerRobot = iterationsPerSecondPerRobot / 60.

	for robot in robots:
		endPosition = p.getBasePositionAndOrientation(robot["id"])[0]
		robot["deltaPosition"] = (endPosition[0]-robot["startPosition"][0], endPosition[1]-robot["startPosition"][1])
		p.removeBody(robot["id"])
	
	deltaPositions = [robot["deltaPosition"] for robot in robots]
	deltaPositionsX = [p[0] for p in deltaPositions]
	deltaPositionsY = [p[1] for p in deltaPositions]
	simulations.append({
		"numRobots": len(robots),
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
	print("{}: {:.0f} RT, max travel distance {:.3f} (variance {:.10f}), delta position: ({:.3f} (variance {:.10f}), {:.3f} (variance {:.10f}))".format(sim["numRobots"], sim["realtimeRatioPerRobot"], sim["maxTravelDistanceMean"], sim["maxTravelDistanceStdDev"], sim["deltaPositionsXMean"], sim["deltaPositionsXStdDev"], sim["deltaPositionsYMean"], sim["deltaPositionsYStdDev"]))

p.disconnect()
