# Like predictor-contrib-example.py, only it tries to recreate the model required for reinforcement-prototype-estimator.py
#
# Status 06.05.2018: Unable to change the number of outputs. outputs in InputFnOps/serving_input_fn() is ignored.
# Making custom estimator instead so I have full control of the output layer.

import tensorflow as tf
from tensorflow.contrib import predictor

def serving_input_fn():
  inputs = tf.placeholder(dtype=tf.float32, shape=[3], name='inputs')
  outputs = tf.placeholder(dtype=tf.float32, shape=[20], name='outputs')

  features = {'inputs': inputs }
  return tf.contrib.learn.utils.input_fn_utils.InputFnOps(
	  features, outputs, default_inputs=features)

input_feature_column_inputs = tf.feature_column.numeric_column('inputs', shape=[1])
estimator = tf.contrib.learn.DNNRegressor(
    feature_columns=[input_feature_column_inputs],
    hidden_units=[10, 20, 10],
    model_dir="model_dir\\predictor-test")

estimator_predictor = tf.contrib.predictor.from_contrib_estimator(estimator, serving_input_fn)

output_dict = estimator_predictor({'inputs': [1., 2., 3.] })

print("Finished successfully! result: {}".format(output_dict))
