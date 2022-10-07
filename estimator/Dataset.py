# A dataset with support for updating data and creating custom training datasets on the fly

import random       # TODO: Remove after __Dataset_deprecated is deleted.
import numpy as np

class Dataset:
    num_accepted, num_rejected = 0, 0

    # TODO: It should be more cache-friendly to split self.store into self.features, self.labels and self.fitness 
    

    # capacity: The number of entries
    def __init__(self, capacity, features_rank, labels_rank):
        self.features_rank = features_rank
        self.labels_rank = labels_rank
        self.capacity = capacity
        self.fitness_column_index = features_rank + labels_rank
        self.store = np.empty((capacity, features_rank+labels_rank+1), dtype=np.float32)
        self.store_row_used = 0
        self.is_full = False

    def add(self, features, labels, fitness):
        def overwrite(row_index, features, labels, fitness):
            self.store[
                row_index, 
                0:
                self.features_rank] = features
            self.store[
                row_index, 
                self.features_rank:
                self.features_rank+self.labels_rank] = labels
            self.store[
                row_index, 
                self.fitness_column_index:
                self.fitness_column_index+1] = fitness

        if self.is_full:
            trial_index = np.random.randint(len(self.store))
            if self.store[trial_index, self.fitness_column_index] < fitness:
                overwrite(trial_index, features, labels, fitness)
                self.num_accepted += 1
            else:
                self.num_rejected += 1
        else:
            overwrite(self.store_row_used, features, labels, fitness)
            self.store_row_used += 1
            self.is_full = self.store_row_used == len(self.store)
            self.num_accepted += 1

    # Returns a multi-line string with statistics for this Dataset instance
    def statistics_to_string(self):
        return """Dataset: 
  Data entries accepted: {}, rejected: {}, acceptance: {:.2f}%
  {} entries used of capacity {}.
  Memory footprint: {:.2f}MB
  Features rank: {}, labels_rank: {}
  """.format(
      self.num_accepted, self.num_rejected, 100*self.num_accepted/(self.num_accepted+self.num_rejected),
      self.store_row_used, len(self.store), 
      1./1000/1000*self.store.nbytes, 
      self.features_rank, self.labels_rank)

    def sample(self, number_of_rows):
        indices = np.random.randint(0, len(self.store), number_of_rows)
        return self.store[indices,0:self.features_rank], self.store[indices,self.features_rank:self.features_rank+self.labels_rank]
