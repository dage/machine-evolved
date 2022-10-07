# This is an attempt of making a minimalistic example of using canned estimators with contrib predictor for fast inference.

import tensorflow as tf
from tensorflow.contrib import predictor

def serving_input_fn():
  x = tf.placeholder(dtype=tf.float32, shape=[1], name='x')
  return tf.estimator.export.TensorServingInputReceiver(x, x)

input_feature_column = tf.feature_column.numeric_column('x', shape=[1])
estimator = tf.estimator.DNNRegressor(
    feature_columns=[input_feature_column],
    hidden_units=[10, 20, 10],
    model_dir="model_dir\\predictor-test")

#estimator_predictor = predictor.from_estimator(estimator, serving_input_fn)
estimator_predictor = predictor.from_estimator(
	estimator, 
	tf.estimator.export.build_raw_serving_input_receiver_fn(
		{"x": tf.placeholder(dtype=tf.string, shape=[1], name='x')}))
		#{"x": tf.placeholder(dtype=tf.float32, shape=[1], name='x')}))



estimator_predictor({"inputs": [1.0]})