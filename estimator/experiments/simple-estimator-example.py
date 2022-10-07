# Testing a simple Estimator usage

import tensorflow as tf
import numpy as np
import itertools

def dataset_from_tensor_slices_input_fn():
	NUM = 200
	input_values = np.random.rand(NUM, 1)
	output_values = 0.5 * input_values
	inputs = {"inputs": input_values}
	outputs = output_values
	print("					input_fn yields ({}, {})....N={}".format(inputs["inputs"][0], outputs[0], NUM))
	dataset = tf.data.Dataset.from_tensor_slices((inputs, outputs))
	iterator = dataset.make_one_shot_iterator()
	return iterator.get_next()

estimator = tf.estimator.DNNRegressor([10], [tf.feature_column.numeric_column("inputs")], model_dir="model_dir\\simple-estimator-test-{}".format(np.random.rand(1,1)[0][0]))

for i in range(100):
	estimator.train(input_fn=dataset_from_tensor_slices_input_fn, max_steps=1)
	evaluate_results = estimator.evaluate(input_fn=dataset_from_tensor_slices_input_fn)
	prediction = estimator.predict(input_fn=dataset_from_tensor_slices_input_fn)
	print("{}: evaluate={}. prediction={}".format(i, evaluate_results, list(prediction)[0]))

#print("{}".format(list(prediction)))