# A Worker class, meant to be run in a seperate process. 

import uuid
import time
import deepdish as dd
import numpy as np
import shutil
from PhysicsServerPool import PhysicsServerPool
from DataGenerator import DataGenerator
from NeuralNet import NeuralNet
from DiskCleaner import DiskCleaner
from pprint import pprint

class Worker:

    # path: Path to the directory where the storage.h5 file can be found
    def __init__(self, path, num_simultanous_simulations, simulation_ticks, warmup_ticks, dnn_config):
        self.path = path
        self.storage_file_path = path + "\\storage.h5"
        self.cleanup_timestamp = time.clock()
        self.dnn_config = dnn_config

        self.physics = PhysicsServerPool(path + "\\robot_file_definitions", num_simultaneous_simulations=num_simultanous_simulations)
        self.data_generator = DataGenerator(self.physics, simulation_ticks=simulation_ticks, warmup_ticks=warmup_ticks)
        self.features_rank, self.labels_rank = self.physics.get_ranks()

    def __sample_creature(self, creature_id):
        features, labels = self.__load_creature_features_lables(creature_id)
        features_flattened = features.reshape(features.shape[0]*features.shape[1], features.shape[2])
        labels_flattened = labels.reshape(labels.shape[0]*labels.shape[1], labels.shape[2])
        # TODO: Could reduce dataset size here by sampling random
        return features_flattened, labels_flattened

    def __load_creature_features_lables(self, creature_id):
        filename = self.__get_creature_path(creature_id) + "\\features_labels.h5"
        container = dd.io.load(filename)
        return container["features"], container["labels"]

    def __create_empty_creature(self):
        return { 
            "fitness": None,
            "id": str(uuid.uuid4())
        }

    def __get_batch_mean_distance(self, positions):
        distances = np.sqrt(np.sum(positions[-1][:,0:2]**2, 1))
        return np.mean(distances)

    def __get_creature_path(self, creature_id):
        return self.path + "\\" + creature_id

    # save_creature_features_lables_base():
    #
    #  Benchmarked different ways of saving 2018-06-13:
    #   numpy_uncompressed: 11.989 MB in 0.094 seconds
    #   numpy_compressed: 8.884 MB in 0.730 seconds
    #   deepdish zlib: 8.515 MB in 1.432 seconds
    #   deepdish blosc: 10.628 MB in 0.087 seconds   <--- !!!
    #   deepdish None: 11.993 MB in 0.014 seconds
    #
    #  Revisited 2018-08-02: Are CPU-limited so considering disabling compression
    #   Total time for 100x 4MB saves uncompressed: 2.3s, blosc compressed: 4.7s. File increase for uncompressed: 13% larger files. ==> Disabling compression for now since CPU-limited and IO is cheap.
    def __save_creature_features_lables(self, creature_id, features, labels):
        filename = self.__get_creature_path(creature_id) + "\\features_labels.h5"
        dd.io.save(filename, {"features": features, "labels": labels}, "None")    # "blosc"

    def __create_initial_population_creature(self):
        creature = self.__create_empty_creature()
    
        neural_net = NeuralNet(self.features_rank, self.labels_rank, self.dnn_config, model_dir = self.__get_creature_path(creature["id"]))
        neural_net.train(   # Just to make tensorflow save a model checkpoint
            -1+2*np.random.rand(1,self.features_rank).astype(np.float32), 
            -1+2*np.random.rand(1,self.labels_rank).astype(np.float32), 
            1)   
        features, labels, positions, _ = self.data_generator.create_raw_data_batch(neural_net)
        
        creature["fitness"] = self.__get_batch_mean_distance(positions)

        self.__save_creature_features_lables(creature["id"], features, labels)

        return {"task": "initial", "creature": creature}

    def __create_crossover_creature(self, clone_creature_id, mimic_creature_id, crossover_train_epochs):
        creature = self.__create_empty_creature()

        shutil.copytree(
            self.__get_creature_path(clone_creature_id), 
            self.__get_creature_path(creature["id"]),
            ignore=shutil.ignore_patterns('*.h5'))
    
        neural_net = NeuralNet(self.features_rank, self.labels_rank, self.dnn_config, model_dir = self.__get_creature_path(creature["id"]))
        neural_net.train(*self.__sample_creature(mimic_creature_id), crossover_train_epochs)
        features, labels, positions, _ = self.data_generator.create_raw_data_batch(neural_net)
        new_distances = np.expand_dims(np.sqrt(np.sum(positions[-1][:,0:2]**2, 1)), axis=0)
        creature["fitness"] = self.__get_batch_mean_distance(positions)

        self.__save_creature_features_lables(creature["id"], features, labels)
   
        distances = np.expand_dims(np.sqrt(np.sum(positions[-1][:,0:2]**2, 1)), axis=0)
        return {
            "task": "crossover",
            "clone_id": clone_creature_id, 
            "mimic_id": mimic_creature_id,
            "epochs": crossover_train_epochs, 
            "creature": creature, 
            "distances": distances}

    def do_work(self, task):
        if task["task"] == "crossover":
            return self.__create_crossover_creature(task["clone_creature_id"], task["mimic_creature_id"], task["epochs"])
        else:
            return self.__create_initial_population_creature()
