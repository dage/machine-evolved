# Minimalistic example of the using the tensorflow predictor, to do high performance inference with the estimator API
#
# Based on predictor-contrib-example.py but changed from using the deprecated contrib estimator to the official non-contrib core estimator.



# TODO: predictor.from_estimator(..) statement throws an exception because export_outputs from EstimatorSpec not specified.
#	1. PRI: Instead of manually specifying model_fn, use pre-built DNNRegressor core estimator, get inspiration from my trigonometric-regressor repo
#	2. PRI: If 1.pri not working, try to reproduce default behaviour for EstimatorSpec by explicitly specifying export_outputs!!!!!!

# I might be building my ServingInputReveiver wrong. Try to find some regressor examples. Have only found a classification example so far: 
#	https://github.com/GoogleCloudPlatform/cloudml-samples/blob/master/census/estimator/trainer/model.py
# Here's some usefull info:
#	https://github.com/tensorflow/tensorflow/issues/12508


import tensorflow as tf
from tensorflow.contrib import predictor

def model_fn(features, labels, mode):
  z = tf.add(features['x'], features['y'], name='z')
  return tf.estimator.EstimatorSpec(
      mode, {'z': z}, loss=tf.constant(0.0), train_op=tf.no_op())

def serving_input_fn():
  #feature_spec = {
  #  'x': tf.FixedLenFeature(dtype=tf.float32, shape=[2]),
  #  'y': tf.FixedLenFeature(dtype=tf.float32, shape=[2])}
  #return tf.estimator.export.build_parsing_serving_input_receiver_fn(feature_spec)()

  x = tf.placeholder(dtype=tf.float32, shape=[None], name='x')
  y = tf.placeholder(dtype=tf.float32, shape=[None], name='y')
  inputs = {'x': x, 'y': y}
  return tf.estimator.export.ServingInputReceiver(inputs, inputs)

  #x = tf.placeholder(dtype=tf.float32, shape=[None], name='x')
  #y = tf.placeholder(dtype=tf.float32, shape=[None], name='y')
  #features = {'x': x, 'y': y}
  # TODO: The next 2 lines might be better than current return statement since it's using core and not contrib
  #receiver_tensors = {'z': tf.placeholder(dtype=tf.string, shape=[1,1], name='z')}
  #return tf.estimator.export.ServingInputReceiver(features=features, receiver_tensors=receiver_tensors)  
  #return tf.contrib.learn.utils.input_fn_utils.InputFnOps(
	 #features, None, default_inputs=features)

#estimator = tf.estimator.Estimator(model_fn=model_fn)
#x = tf.placeholder(dtype=tf.float32, shape=[None], name='x')
x = tf.feature_column.numeric_column('x', shape=[2])
#y = tf.placeholder(dtype=tf.float32, shape=[None], name='y')
y = tf.feature_column.numeric_column('y', shape=[2])
features = [x, y]
estimator = tf.estimator.DNNRegressor(
    feature_columns=features,
    hidden_units=[32],
    model_dir="model_dir\\predictor-test")
	# TODO: If this works, delete model_fn


estimator_predictor = predictor.from_estimator(estimator, serving_input_fn)

output_dict = estimator_predictor({'x': [1., 2.], 'y': [3., 4.]})
#output_dict = estimator_predictor({'inputs': [[1.]]})

print("Finished successfully!")