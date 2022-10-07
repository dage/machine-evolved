# DataGenerator

import numpy as np
import time

from PhysicsServerPool import PhysicsServerPool

class DataGenerator:
    def __init__(self, physics, renderer = None, simulation_ticks=60*30, warmup_ticks=60*5):
        self.warmup_ticks = warmup_ticks
        self.simulation_ticks = simulation_ticks
        self.physics = physics
        self.renderer = renderer
        self.features_rank, self.labels_rank = self.physics.get_ranks()

    # Prints a fresh set of standardization constants to the console.
    # Before running this function, all standardization constants must be set to std-dev=1, mean=0
    # and all serialized features->labels will be invalid after changing these constants.
    def examine_standarization(self, features):
        def get_keys_for_type(desc, type):
            groups_with_type = list(filter(lambda group: group[3]==type, desc))  # could be multiple (joints)
            keys_with_duplicates = list(map(lambda group: group[1], groups_with_type))
            flatten_keys_with_duplicates = [item for sublist in keys_with_duplicates for item in sublist]
            distinct_keys = list(set(flatten_keys_with_duplicates)) 
            return sorted(distinct_keys)

        def get_indices(type, key):
            groups_with_type = list(filter(lambda group: group[3]==type, desc))
            indices = []
            for group in groups_with_type:
                local_indices = list(filter(lambda index: group[1][index] == key, range(len(group[1]))))
                indices += map(lambda local_index: group[2][local_index], local_indices)
            return indices


        features_flattened = features.reshape(features.shape[0]*features.shape[1], features.shape[2])   # 3D->2D
        features_standardization = { 
            "std": np.std(features_flattened, 0),
            "mean": np.mean(features_flattened, 0)}
        
        desc = self.physics.get_observations_description()
        distinct_group_types = sorted(list(set([desc[n][3] for n in range(len(desc))])))
        for type in distinct_group_types:
            keys = get_keys_for_type(desc, type)
            for key in keys:
                indices = get_indices(type, key)
                for stat_key in ["std", "mean"]:
                    print("{}_{}_{} = {:.5f} {}".format(
                        type, 
                        key, 
                        stat_key, 
                        np.mean(features_standardization[stat_key][indices]),
                        "# {}".format(features_standardization[stat_key][indices]) if len(indices)>1 else ""))


    # target_size_mb: Stop generating data when data size reaches this size [MegaBytes]
    def create_initial_raw_data_to_file(self, target_size_mb, neural_net, filename):
        is_size_reached = False
        trial = 0
        while not is_size_reached:
            neural_net.randomize()
            features_batch, labels_batch, positions_batch, _ = self.create_raw_data_batch(neural_net)
            if trial == 0:
                features_complete, labels_complete, positions_complete = features_batch, labels_batch, positions_batch
            else:
                features_complete = np.concatenate((features_complete, features_batch), axis=1)
                labels_complete = np.concatenate((labels_complete, labels_batch), axis=1)
                positions_complete = np.concatenate((positions_complete, positions_batch), axis=1)

            trial += 1
            memory_footprint_mb = 1./1000/1000.*(features_complete.nbytes + labels_complete.nbytes + positions_complete.nbytes)
            print("{:.2f}%: {:.2f} MB of {:.0f} MB generated.".format(100*memory_footprint_mb/target_size_mb, memory_footprint_mb, target_size_mb))
            is_size_reached = memory_footprint_mb > target_size_mb

        self.save_raw_data(features_complete, labels_complete, positions_complete, filename)

    def save_raw_data(self, features_batch, labels_batch, positions_batch, filename):
        start_time = time.clock()
        print("Saving dataset to {}".format(filename))
        np.savez(filename, features=features_batch, labels=labels_batch, positions=positions_batch)
        print("..finished in {:.3f} seconds.".format(time.clock()-start_time))

    def load_raw_data(self, filename):
        start_time = time.clock()
        print("Loading dataset from {}".format(filename))
        with np.load(filename) as loaded:
            features, labels, positions = loaded["features"], loaded["labels"], loaded["positions"]
        print("..finished in {:.3f} seconds. {} simulations, {} entries.".format(
            time.clock()-start_time,
            features.shape[1],
            features.shape[0]*features.shape[1]))
        return features, labels, positions

    # Performs a simulation run for the model and predictor passed on multiple simultanous physics servers 
    def create_raw_data_batch(self, neural_net, servers = None):
        self.physics.create_all_robots(servers)

        batch_ticks = self.simulation_ticks - self.warmup_ticks
        features_batch = np.zeros((batch_ticks, self.physics.num_simultaneous_simulations, self.features_rank), dtype=np.float32)
        labels_batch = np.zeros((batch_ticks, self.physics.num_simultaneous_simulations, self.labels_rank), dtype=np.float32)
        positions_batch = np.zeros((batch_ticks, self.physics.num_simultaneous_simulations, 2), dtype=np.float32)

        predictor = neural_net.get_predictor()
        for i in range(self.simulation_ticks):
            tick_index = max(0, i - self.warmup_ticks)  # keep using index 0 until warmup perdiod is passed 
            features_batch[tick_index] = self.physics.get_observations(i)

            predictor_output = predictor({"x": features_batch[tick_index] })
            labels_batch[tick_index] = predictor_output["output"]

            self.physics.apply_forces(predictor_output["output"])  # forces shape (NUM_PHYSICS_SERVERS, LABELS_RANK)    
            self.physics.tick()

            positions_batch[tick_index] = self.physics.get_robot_positions()[:,0:2]

        servers = self.physics.get_cloned_servers()

        self.physics.destroy_all_robots()

        return features_batch, labels_batch, positions_batch, servers