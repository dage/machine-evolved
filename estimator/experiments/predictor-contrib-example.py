# Minimalistic example of the using the tensorflow predictor, to do high performance inference with the estimator API
#
# Uses the contrib canned estimator since there are so many problems with using the core one.
#
# Based on the github README at https://github.com/tensorflow/tensorflow/tree/master/tensorflow/contrib/predictor
# Using the deprecated tensorflow.contrib version.

import tensorflow as tf
from tensorflow.contrib import predictor

# Not used for canned estimator:
#def model_fn(features, labels, mode):
#  z = tf.add(features['x'], features['y'], name='z')
#  return tf.contrib.learn.ModelFnOps(
#      mode, {'z': z}, loss=tf.constant(0.0), train_op=tf.no_op())

def serving_input_fn():
  x = tf.placeholder(dtype=tf.float32, shape=[None], name='x')
  y = tf.placeholder(dtype=tf.float32, shape=[None], name='y')

  features = {'x': x, 'y': y}
  return tf.contrib.learn.utils.input_fn_utils.InputFnOps(
	  features, None, default_inputs=features)

#estimator = tf.contrib.learn.Estimator(model_fn=model_fn)
input_feature_column_x = tf.feature_column.numeric_column('x', shape=[1])
input_feature_column_y = tf.feature_column.numeric_column('y', shape=[1])
estimator = tf.contrib.learn.DNNRegressor(
    feature_columns=[input_feature_column_x, input_feature_column_y],
    hidden_units=[10, 20, 10],
    model_dir="model_dir\\predictor-test")

estimator_predictor = predictor.from_contrib_estimator(estimator, serving_input_fn)

output_dict = estimator_predictor({'x': [1., 2., 3.], 'y': [4., 5., 6.]})

print("Finished successfully! result: {}".format(output_dict))
