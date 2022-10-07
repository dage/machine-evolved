# Tests how to make the optimial starting condition for each robot and also looks at
# deteriorating performance as the same physics server is reused for multiple simulations.
#
# Results: Not not use p.removeBody(). Performance decreases at a rapid pace.
#   When using .resetSimulation(): 
#       Mean simulation time: 0.00893s
#   When creating a new physics server for every simulation run:
#       Mean simulation time: 0.02421s
#   ==> It's about a 0.01528s performance cost of spawning a physics server!!

import pybullet as p
import pybullet_data
import time
import numpy as np
from RobotFileFactory import RobotFileFactory
import matplotlib.pyplot as plt

RENDER = True
MAX_FORCE = 5000
MAX_TICKS = 60*5
MAX_ANGULAR_POSITION = 1.57		# range property from joint definition in mujoco .xml file

def getActiveJointIndices(robotId):
	indices = []
	for i in range(p.getNumJoints(robotId)):
		jointInfo = p.getJointInfo(robotId, i)
		if jointInfo[2] == p.JOINT_REVOLUTE:	# Currently only hinge/revolute supported
			indices.append(i)
	return indices

def printRobotInfo(robotId):
	def prettyPrintType(intType):
		strMap = { p.JOINT_REVOLUTE: "revolute", p.JOINT_PRISMATIC: "prismatic", p.JOINT_SPHERICAL: "spherical", p.JOINT_PLANAR: "planar", p.JOINT_FIXED: "fixed"}
		if not intType in strMap:
			return "unknown({})".format(intType)
		return strMap[intType]

	numJoints = p.getNumJoints(robotId)
	print("Robot imported. Number of joints={}".format(numJoints))
	for i in range(numJoints):
		jointInfo = p.getJointInfo(robotId, i)
		print("  joint {}: type={}, rest={}".format(i, prettyPrintType(jointInfo[2]), jointInfo))

rff = RobotFileFactory()

NUM = 50 if RENDER else 1000
INITIAL_HEIGHT = 2
collision_ticks = np.array([-1]*NUM)
simulation_durations = np.array([-1]*NUM, dtype=np.float64)

physicsClient = p.connect(p.GUI if RENDER else p.DIRECT)

for si in range(NUM):
    start_time = time.clock()

    p.setPhysicsEngineParameter(fixedTimeStep=1.0/60., numSolverIterations=5, numSubSteps=2)
    p.setAdditionalSearchPath(pybullet_data.getDataPath()) # used by loadURDF
    p.setGravity(0,0,-10)

    robot_filename = rff.create(RobotFileFactory.ROBOT_CAPSULES_2, INITIAL_HEIGHT)
    mjcfInfo = p.loadMJCF(robot_filename, flags = p.URDF_USE_SELF_COLLISION_EXCLUDE_ALL_PARENTS)
    rff.delete(robot_filename)
    robotId = mjcfInfo[1]

    step = 0
    jointIndices = getActiveJointIndices(robotId)
    startPosition, _ = p.getBasePositionAndOrientation(robotId)

    #print("-------------------------------------------------------------")
    #print("pyBullet API version {}.".format(p.getAPIVersion()))
    #printRobotInfo(robotId)

    targetPositions = (MAX_ANGULAR_POSITION*(-1+2*np.random.rand(1,3)))[0].tolist()
    i = 0
    is_free_fall = True
    while i < MAX_TICKS and is_free_fall:
        p.setJointMotorControlArray(robotId, jointIndices, controlMode=p.POSITION_CONTROL, targetPositions=targetPositions, forces=[MAX_FORCE, MAX_FORCE, MAX_FORCE])
        p.stepSimulation()
        collisions = p.getContactPoints()
        if collisions:
            is_free_fall = False
            collision_ticks[si] = i
            print("{:.1f}%: Collision at tick {}".format(si/NUM*100, i))

        if RENDER:
            time.sleep(1/60)  
        i += 1

    simulation_durations[si] = time.clock() - start_time

    #p.removeBody(robotId)  # NO NO NO NO!!!!
    p.resetSimulation()
    #p.disconnect()

print("Collision ticks: {}".format(collision_ticks))
print("initial_height={}".format(INITIAL_HEIGHT))
numZeroes = (collision_ticks == 0).sum()
print("Ratio in initial collision: {:.2f}%".format(numZeroes*100/NUM))
print("Mean simulation time: {:.5f}s".format(np.mean(simulation_durations)))

plt.plot(simulation_durations)
plt.show()

p.disconnect()