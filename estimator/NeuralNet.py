# Containing all neural net related code using tensorflow.

import tensorflow as tf
import datetime
import re
from pprint import pprint

class NeuralNet:
    def __init__(self, features_rank, labels_rank, config, model_dir = None):
        def model_fn(features, labels, mode):
            net = features["x"]				# input
            for layer in config["layers"]:
                # TODO:
                #   * Test with normalization, maybe tf.layers.BatchNormalization???

                # TODO: 
                #   * If want to do normalization: Switch from dense to fully_connected so that normalization can be passed in
                #   * Parameterize activation function
                #   * Research, test and maybe add support for other layer types, se tf.layers module.
                net = tf.layers.dense(net, units=layer["units"], activation=tf.nn.relu)
                
                if layer["dropout"] > 1e-9:
                    net = tf.layers.dropout(net, rate=layer["dropout"], training= mode==tf.estimator.ModeKeys.TRAIN)  

            output = tf.layers.dense(net, labels_rank, activation=None)

            if mode == tf.estimator.ModeKeys.PREDICT:
                return tf.estimator.EstimatorSpec(mode, predictions=output, export_outputs={"out": tf.estimator.export.PredictOutput(output)})

            # TODO:
            #   * Parameterize loss-function, also have cross entropy and others
            loss = tf.losses.mean_squared_error(labels, output)

            if mode == tf.estimator.ModeKeys.EVAL:
                return tf.estimator.EstimatorSpec(mode, loss=loss)

            # TODO: * Parameterize optimizer and learning rate
            optimizer = tf.train.AdagradOptimizer(learning_rate=0.01)
            train_op = optimizer.minimize(loss, global_step=tf.train.get_global_step())
            return tf.estimator.EstimatorSpec(mode, loss=loss, train_op=train_op)

        self.__features_rank = features_rank
        self.__labels_rank = labels_rank
        self.__model_dir = model_dir or "model_dir\\{date:%Y-%m-%d %H.%M.%S}".format(date=datetime.datetime.now())

        self.__model = tf.estimator.Estimator(
            model_fn=model_fn,	
            config=tf.estimator.RunConfig(keep_checkpoint_max=2),
            model_dir=self.__model_dir)

        self.__predictor = None     # Invalidate

    def randomize(self):
        self.__init__(self.__features_rank, self.__labels_rank, self.__model_dir)   # Clone this instance into self. TODO: See if weights can be randomized directly

    def get_model(self):
        return self.__model

    def get_predictor(self):
        self.__predictor = self.__predictor or tf.contrib.predictor.from_estimator(self.__model, lambda: self.serving_input_fn(self.__features_rank))
        return self.__predictor

    def train(self, features, labels, steps):
        self.__model.train(input_fn=lambda: self.get_input_fn(features, labels, steps-1), steps=steps)	
        self.__predictor = None # Invalidate predictor since it no longer matches the trained model

    # samples the dataset and returns a input_fn like estimator.train() expects
    def get_input_fn(self, features, labels, repeat_count):
        # TODO: Examine performance. The best option might be to keep the Dataset instance and use a tf.placeholder for passing values.
        dataset = tf.data.Dataset.from_tensors(({"x": features}, labels))
        if repeat_count > 0:
            dataset = dataset.repeat(repeat_count)
        return dataset.make_one_shot_iterator().get_next()

    def serving_input_fn(self, numInputs):
        x = tf.placeholder(dtype=tf.float32, shape=[None, numInputs], name='x')		# match dtype in input_fn
        inputs = {'x': x }
        return tf.estimator.export.ServingInputReceiver(inputs, inputs)

