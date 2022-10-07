# Tests performance in the innerloop, looking at inference vs physics simulation performance.
#
# Results from run 2018-05-12:
#    physics time for 20000 ticks: 1.24499s
#    predictor time for 20000 ticks: 7.60043s
#      ==> predictor consumes 85.9% of the performance cost.

import tensorflow as tf
import pybullet as p
import pybullet_data
import datetime
import time
import numpy as np
from RobotFileFactory import RobotFileFactory
import matplotlib.pyplot as plt

NUM = 20000
INITIAL_HEIGHT = 2
MAX_FORCE = 5000
FEATURES_RANK = 14
LABELS_RANK = 3

def getActiveJointIndices(robotId):
	indices = []
	for i in range(p.getNumJoints(robotId)):
		jointInfo = p.getJointInfo(robotId, i)
		if jointInfo[2] == p.JOINT_REVOLUTE:	# Currently only hinge/revolute supported
			indices.append(i)
	return indices

def serving_input_fn():
	x = tf.placeholder(dtype=tf.float32, shape=[None, FEATURES_RANK], name='x')		# match dtype in input_fn
	inputs = {'x': x }
	return tf.estimator.export.ServingInputReceiver(inputs, inputs)

def createModel(numInputs, numOutputs):
	def model_fn(features, labels, mode):
		net = features["x"]				# input
		for units in [15, 30, 5]:		# hidden units
			net = tf.layers.dense(net, units=units, activation=tf.nn.relu)
			net = tf.layers.dropout(net, rate=0.1)
		output = tf.layers.dense(net, LABELS_RANK, activation=None)
	
		if mode == tf.estimator.ModeKeys.PREDICT:
			return tf.estimator.EstimatorSpec(mode, predictions=output, export_outputs={"out": tf.estimator.export.PredictOutput(output)})
	
		loss = tf.losses.mean_squared_error(labels, output)

		if mode == tf.estimator.ModeKeys.EVAL:
			return tf.estimator.EstimatorSpec(mode, loss=loss)
	
		optimizer = tf.train.AdagradOptimizer(learning_rate=0.1)
		train_op = optimizer.minimize(loss, global_step=tf.train.get_global_step())
		return tf.estimator.EstimatorSpec(mode, loss=loss, train_op=train_op)

	model = tf.estimator.Estimator(
		model_fn=model_fn,	
		model_dir="model_dir\\inner-loop-performance-test-{date:%Y-%m-%d %H.%M.%S}".format(date=datetime.datetime.now()))

	predictor = tf.contrib.predictor.from_estimator(model, serving_input_fn)

	return model, predictor

def getObservations(robotId):
	def getBaseStates(robotId):
		position, orientation = p.getBasePositionAndOrientation(robotId)
		return [position[2], *orientation]	# TODO: Normalize position.z
		
	def getJointStates(robotId):
		observables = []
		for i in range(p.getNumJoints(robotId)):
			jointInfo = p.getJointInfo(robotId, i)
			if jointInfo[2] == p.JOINT_REVOLUTE:	# Currently only hinge/revolute supported
				lowerLimit = jointInfo[8]
				upperLimit = jointInfo[9]
				middle = 2 * (lowerLimit + upperLimit)

				jointState = p.getJointState(robotId, i)
				position = 2 * (jointState[0] - middle) / (upperLimit - lowerLimit)
				velocity = 0.15 * jointState[1]
				force = jointState[3] / MAX_FORCE

				# print("{}: {} --> {}".format(i, jointState, [position, velocity, force]))
		
				observables.append(position)
				observables.append(velocity)
				observables.append(force)	
		return observables

	return [*getBaseStates(robotId), *getJointStates(robotId)]



physicsClient = p.connect(p.DIRECT)

p.setPhysicsEngineParameter(fixedTimeStep=1.0/60., numSolverIterations=5, numSubSteps=2)
p.setAdditionalSearchPath(pybullet_data.getDataPath()) # used by loadURDF
p.setGravity(0,0,-10)

rff = RobotFileFactory()
robot_filename = rff.create(RobotFileFactory.ROBOT_CAPSULES_2, INITIAL_HEIGHT)
mjcfInfo = p.loadMJCF(robot_filename, flags = p.URDF_USE_SELF_COLLISION_EXCLUDE_ALL_PARENTS)
rff.delete(robot_filename)
robotId = mjcfInfo[1]

step = 0
jointIndices = getActiveJointIndices(robotId)
startPosition, _ = p.getBasePositionAndOrientation(robotId)

i = 0
targetPositions = (-1+2*np.random.rand(1,3))[0].tolist()
start_time_physics = time.clock()
while i < NUM:
    p.setJointMotorControlArray(robotId, jointIndices, controlMode=p.POSITION_CONTROL, targetPositions=targetPositions, forces=[MAX_FORCE, MAX_FORCE, MAX_FORCE])
    p.stepSimulation()
    i += 1

delta_time_physics  = time.clock() - start_time_physics 


model, predictor = createModel(len(getObservations(robotId)), len(jointIndices))

start_time_predictor = time.clock()
for i in range(NUM):
    observations = getObservations(robotId)
    predictor_input = {"x": np.array(observations).reshape(1, FEATURES_RANK) }
    predictor_output = predictor(predictor_input)

delta_time_predictor  = time.clock() - start_time_predictor

p.disconnect()

print("physics time for {} ticks: {:.5f}s".format(NUM, delta_time_physics))
print("predictor time for {} ticks: {:.5f}s".format(NUM, delta_time_predictor))
print("  ==> predictor consumes {:.1f}% of the performance cost.".format(delta_time_predictor/(delta_time_physics + delta_time_predictor)*100))

