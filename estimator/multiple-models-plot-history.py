# Plots the fitness history

import argparse
import time
import deepdish as dd
import numpy as np
from Plotting import Plotting

def parse_command_line_arguments():
	parser = argparse.ArgumentParser(description='Reinforcement learning prototype fitness history plotter.')
	parser.add_argument("directory", help="Directory for where to find the models.", action="store")		
	return parser.parse_args()

def get_model_dir(base_dir, creature_id):
    return base_dir + "\\" + creature_id

args = parse_command_line_arguments()

get_creature_model_dir = lambda creature_id: get_model_dir(args.directory, creature_id)
storage_file_path = args.directory + "\\storage.h5"
plotting = Plotting()

try:
    start_time = time.clock()
    storage = dd.io.load(storage_file_path)
    print("storage loaded from {} in {:.3f} seconds".format(storage_file_path, time.clock() - start_time))
except OSError:
    print("ERROR: Could not find storage in {}.".format(storage_file_path))
    exit()

if len(storage["distances_history"]) == 0:
    print("ERROR: No history exists. Still building initial population.")
    exit()

plotting.plot_distance_development(
    storage["distances_history"], 
    horizontal_lines=[
        {"y": np.mean(storage["initial_random_distance_history"]), "label": "Initial random distance"}, 
        {"y": storage["initial_mean_kept_distance"], "label": "Initial kept distance"}],
    title="Fitness development, dnn={}, pop={}, sim={}*{}".format(storage["dnn_structure"], storage["population_size"], storage["simulation_ticks"], storage["num_simultanous_simulations"]))
