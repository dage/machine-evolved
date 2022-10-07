# Renders the best model.

import argparse
import time
import deepdish as dd
import numpy as np
from PhysicsServerPool import PhysicsServerPool
from Renderer import Renderer
from NeuralNet import NeuralNet

WARMUP_TICKS = 60*5      # Ignore these first ticks for training as they are mostly based on initial conditions with falling etc

def parse_command_line_arguments():
	parser = argparse.ArgumentParser(description='Reinforcement learning prototype best model renderer.')
	parser.add_argument("directory", help="Directory for where to find the models.", action="store")		
	return parser.parse_args()

def get_model_dir(base_dir, creature_id):
    return base_dir + "\\" + creature_id

args = parse_command_line_arguments()

get_creature_model_dir = lambda creature_id: get_model_dir(args.directory, creature_id)
storage_file_path = args.directory + "\\storage.h5"

try:
    storage = dd.io.load(storage_file_path)
    print("storage loaded from {}".format(storage_file_path))
except OSError:
    print("Could not find storage in {}. Giving up...".format(storage_file_path))
    exit()

physics = PhysicsServerPool(args.directory + "\\robot_file_definitions", num_simultaneous_simulations=storage["num_simultanous_simulations"])
renderer = Renderer(physics)
features_rank, labels_rank = physics.get_ranks()
fitnesses = [x["fitness"] for x in storage["population"]]
best_creature_index = np.argmax(fitnesses)
creature = storage["population"][best_creature_index]

#neural_net = NeuralNet(self.features_rank, self.labels_rank, self.dnn_config, model_dir = self.__get_creature_path(creature["id"]))
#neural_net = NeuralNet(features_rank, labels_rank, model_dir = get_creature_model_dir(creature["id"]), structure = storage["dnn_structure"])
neural_net = NeuralNet(features_rank, labels_rank, storage["dnn_structure"], model_dir = get_creature_model_dir(creature["id"]))

print("Rendering creature with fitness {:.3f}".format(creature["fitness"]))
renderer.render_robot(neural_net, steps = 1000000000, distance_travelled_extra_info = True)