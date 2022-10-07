# Attempt of getting stackoverflow answer suggestion for canned estimator to work:
# https://stackoverflow.com/questions/50111636/unable-to-use-core-estimator-with-contrib-predictor/50204796#50204796


import tensorflow as tf

def serving_input_fn():
  x = tf.placeholder(dtype=tf.float32, shape=[1], name='x')
  inputs = {'x': x }
  return tf.estimator.export.ServingInputReceiver(inputs, inputs)

input_feature_column = tf.feature_column.numeric_column('x', shape=[1])
estimator = tf.estimator.DNNRegressor(
    feature_columns=[input_feature_column],
    hidden_units=[10, 20, 10],
    model_dir="model_dir\\stackoverflow-answer-2")

estimator_predictor = tf.contrib.predictor.from_estimator(estimator, serving_input_fn)

estimator_predictor({"x": [1.0]})