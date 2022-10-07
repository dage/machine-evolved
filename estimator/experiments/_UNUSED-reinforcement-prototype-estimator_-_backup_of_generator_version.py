# TODO:
#	1.) DONE: estimator-tutorial-_-wide-deep sub directory. Reproduce the tutorial at https://www.tensorflow.org/tutorials/wide
#	2.) Change it into a simple "hello world" version which is closer to my goal:
#       a.) Study https://stackoverflow.com/questions/46982168/trying-to-use-linearregressor
#       b.) Use numpy arrays instead of generators. See Import Data -> From numpy @ https://towardsdatascience.com/how-to-use-dataset-in-tensorflow-c758ef9e4428
#	3.) Store file for future reference
#	4.) Expand into pyBullet driven dataset
#	5.) Store best model, explore optimalization etc etc etc
#	6.) Customize Dataset to match asia-idea

import math
import numpy as np
import tensorflow as tf

PI = 3.14159265359

def input_fn():
	def generator():
		NUM = 10
		for i in range(NUM):
			angle = i/NUM*PI*2
			output = math.sin(angle)
			yield angle, output

# for testing the generator:
#	for angle, output in generator():
#		print("{} -> {}".format(angle, output))

	dataset = tf.data.Dataset.from_generator(generator, (tf.float32, tf.float32), (tf.TensorShape([]), tf.TensorShape([])))

	iterator = dataset.make_one_shot_iterator()

	features, labels = iterator.get_next()
	return features, labels

def build_estimator():
	feature_columns = [
		tf.feature_column.numeric_column('angle', shape=[1])
	]
	return tf.estimator.LinearRegressor(feature_columns)


if __name__ == '__main__':
	model = build_estimator()
	model.train(input_fn=input_fn, steps=10)# TODO:
#	1.) DONE: estimator-tutorial-_-wide-deep sub directory. Reproduce the tutorial at https://www.tensorflow.org/tutorials/wide
#	2.) Change it into a simple "hello world" version which is closer to my goal
#       Use numpy arrays instead of generators, see Import Data .. From Numpy @ https://towardsdatascience.com/how-to-use-dataset-in-tensorflow-c758ef9e4428
#	3.) Store file for future reference
#	4.) Expand into pyBullet driven dataset
#	5.) Store best model, explore optimalization etc etc etc
#	6.) Customize Dataset to match asia-idea

import math
import tensorflow as tf

PI = 3.14159265359

def input_fn():
	def generator():
		NUM = 10
		for i in range(NUM):
			angle = i/NUM*PI*2
			output = math.sin(angle)
			yield angle, output

# for testing the generator:
#	for angle, output in generator():
#		print("{} -> {}".format(angle, output))

	dataset = tf.data.Dataset.from_generator(generator, (tf.float32, tf.float32), (tf.TensorShape([]), tf.TensorShape([])))

	iterator = dataset.make_one_shot_iterator()

	features, labels = iterator.get_next()

	return features, labels

def build_estimator():
	feature_columns = [
		tf.feature_column.numeric_column(''),
		tf.feature_column.numeric_column('')
	]
	return tf.estimator.LinearRegressor(feature_columns)


if __name__ == '__main__':
    sess = tf.Session()
    print(sess.run(input_fn))

    exit()

	#model = build_estimator()
	#model.train(input_fn=input_fn, steps=10)
