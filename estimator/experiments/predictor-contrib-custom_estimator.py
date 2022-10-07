# Making a custom contrib estimator for use with the contrib predictor.
# 
# Developed on tensorflow 1.8r

import tensorflow as tf

def serving_input_fn():
  inputs = tf.placeholder(dtype=tf.float32, shape=[3], name='inputs')

  features = {'inputs': inputs }
  return tf.contrib.learn.utils.input_fn_utils.InputFnOps(
	  features, None, default_inputs=features)

input_feature_column_inputs = tf.feature_column.numeric_column('inputs', shape=[1])
estimator = tf.contrib.learn.DNNRegressor(
    feature_columns=[input_feature_column_inputs],
    hidden_units=[10, 20, 10],
    model_dir="model_dir\\predictor-test")

estimator_predictor = tf.contrib.predictor.from_contrib_estimator(estimator, serving_input_fn)

output_dict = estimator_predictor({'inputs': [1., 2., 3.] })

print("Finished successfully! result: {}".format(output_dict))

