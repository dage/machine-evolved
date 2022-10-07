import tensorflow as tf
from tensorflow.contrib import predictor

def model_fn(features, labels, mode):
    # this will trigger other errors once the type check is passed
    return None
est = tf.estimator.Estimator(model_fn=model_fn)

def serving_input_receiver_fn():
    inputs = {'X': tf.placeholder(shape=[None, 1], dtype=tf.float32)}
    return tf.estimator.export.ServingInputReceiver(inputs, inputs)

est_pred = predictor.from_estimator(est , serving_input_receiver_fn)