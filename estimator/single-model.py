# A DNN reinforcement learning experiment using pyBullet, MuJoCo xml data files and tensorflow estimator API
#
# This experiment uses a single model trained on a large set of data dereived from lots of randomized models.
# See multiple-models.py for a different approach.

import numpy as np
import matplotlib.pyplot as plt
from PhysicsServerPool import PhysicsServerPool
from Dataset import Dataset
from DataGenerator import DataGenerator
from NeuralNet import NeuralNet
from Renderer import Renderer
from Plotting import Plotting

INITIAL_POPULATION_FILENAME = "c:\\temp\\reinforcement_prototype_initial_population.npz" 
FITNESS_TIME_DELTAS = [5, 15, 30, 60, 120]  # How long to look into the future to calculate position deltas for fitness value
DATASET_SIZE_INITIAL_RATIO = 0.1    # Ratio of initial raw data
DATASET_TRAINING_SAMPLE_SIZE = 0.01    # If <1: Use as a ratio of the dataset size (f.ex. 0.5=train on 50% of the data already accepted into the dataset). If >1: Use as the number of entries to use.
SIMULATION_TICKS = 60*45 + FITNESS_TIME_DELTAS[-1]
WARMUP_TICKS = 60*5      # Ignore these first ticks for training as they are mostly based on initial conditions with falling etc
NUM_SIMULTANOUS_SIMULATIONS = 20
EPOCHS_PER_SIMULATION = 50	# After the initial population has been created
REPEATING_SIMULATIONS = 20

def transform_raw_data_to_dataset(features, labels, positions, dataset): 
    indices = np.arange(SIMULATION_TICKS-WARMUP_TICKS-FITNESS_TIME_DELTAS[-1])
    future_indices = np.vstack(indices)+FITNESS_TIME_DELTAS
    
    start_positions = np.expand_dims(positions[indices], 1)
    start_positions = np.repeat(start_positions, len(FITNESS_TIME_DELTAS), axis=1)  # One for each future position
    future_positions = positions[future_indices]
    delta_positions = future_positions - start_positions
    future_distances = np.sqrt(np.sum(delta_positions**2, axis=3))
    fitness = np.sum(future_distances, axis=1)

    for i in range(fitness.shape[0]):
        for si in range(fitness.shape[1]):
            data.add(features[i][si], labels[i][si], fitness[i][si])

physics = PhysicsServerPool(num_simultaneous_simulations=NUM_SIMULTANOUS_SIMULATIONS)
renderer = Renderer(physics)
data_generator = DataGenerator(physics, renderer, simulation_ticks=SIMULATION_TICKS, warmup_ticks=WARMUP_TICKS)
features_rank, labels_rank = physics.get_ranks()
neural_net = NeuralNet(features_rank, labels_rank)
plotting = Plotting()


# Uncomment to regenerate raw data and save to file!
data_generator.create_initial_raw_data_to_file(5, neural_net, INITIAL_POPULATION_FILENAME)
#exit()
features, labels, positions = data_generator.load_raw_data(INITIAL_POPULATION_FILENAME)
data_generator.examine_standarization(features)
plotting.examine_features(physics, features)

data = Dataset(int(DATASET_SIZE_INITIAL_RATIO*features.shape[0]*features.shape[1]), features_rank, labels_rank)

transform_raw_data_to_dataset(features, labels, positions, data)

print(data.statistics_to_string())
initial_distances = np.sqrt(np.sum(positions[-1][:,0:2]**2, 1))
initial_mean_distance = np.mean(initial_distances)
print("All data in raw dataset: Distances: [{:.3f}-{:.3f}], mean={:.3f}, std={:.3f}.".format(min(initial_distances), max(initial_distances), np.mean(initial_distances), np.std(initial_distances)))

num_entries_training_set = DATASET_TRAINING_SAMPLE_SIZE if DATASET_TRAINING_SAMPLE_SIZE >1 else int(data.capacity*DATASET_TRAINING_SAMPLE_SIZE)
distances_history = np.zeros((REPEATING_SIMULATIONS, NUM_SIMULTANOUS_SIMULATIONS))
for i in range(REPEATING_SIMULATIONS):
    if i!=0:    # Do not train first iteration because we want to see statistics on how the untrained model behaves
        neural_net.train(*data.sample(num_entries_training_set), EPOCHS_PER_SIMULATION)

    features_batch, labels_batch, positions_batch, _ = data_generator.create_raw_data_batch(neural_net)
    transform_raw_data_to_dataset(features_batch, labels_batch, positions_batch, data)    

    distances_history[i] = np.sqrt(np.sum(positions_batch[-1][:,0:2]**2, 1))
    print("{}/{}: Distances: [{:.3f}-{:.3f}], mean={:.3f}, std={:.3f}.".format(i+1, REPEATING_SIMULATIONS, min(distances_history[i]), max(distances_history[i]), np.mean(distances_history[i]), np.std(distances_history[i])))

    #renderer.render_robot(neural_net, steps=SIMULATION_TICKS, sleep_tick_modulo=1)


print(data.statistics_to_string())

plotting.plot_distance_development(distances_history, horizontal_lines=[initial_mean_distance])
#renderer.render_robot(neural_net, steps=SIMULATION_TICKS)