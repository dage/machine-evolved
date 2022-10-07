# A collection of functions for visualizing the internal data

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.cbook as cbook
import numpy as np

class Plotting():
    # epochs        list of epochs tested
    # y             list of normalized y values
    # generations   list of generations
    def analyze_crossover(self, epochs, y, generations):
        max_generations = max(generations)
        generations_normalized = [40 * g / max_generations for g in generations]

        plt.xlabel("Epochs")
        plt.ylabel("Relative fitness")
        plt.axhline(linewidth=2, color='r')
        plt.scatter(epochs, y, s=generations_normalized, alpha=0.5)

        # Regression
        z = np.polyfit(epochs, y, 3)
        f = np.poly1d(z)
        epochs_new = np.linspace(min(epochs), max(epochs), 200)
        y_new = f(epochs_new)
        plt.plot(epochs_new, y_new, color="orange", linewidth=4, alpha=0.7)

        plt.show()

    def plot_distance_development(self, distances_history, horizontal_lines = [], title="Distance development"):
        x = range(len(distances_history))
        y = np.mean(distances_history, 1)
        #plt.boxplot(np.transpose(distances_history))
        plt.scatter(x, y, marker=".", alpha=0.15)

        # Regression
        z = np.polyfit(x, y, 3)
        f = np.poly1d(z)
        x_new = np.linspace(x[0], x[-1], 200)
        y_new = f(x_new)
        plt.plot(x_new, y_new, color="orange", linewidth=4)

        # Horizontal lines for initial population
        COLORS = ['r', 'g', 'b']    # TODO: Add more if every using more than 3 horizontal lines
        for i in range(len(horizontal_lines)):
            line = horizontal_lines[i]
            plt.hlines(y=line["y"], color=COLORS[i], linestyle='-', label=line["label"], xmin=0, xmax=len(distances_history)-1, linewidth=3)
        plt.legend()
        
        plt.title(title)
        plt.show()

    # Examines both the distribution and continuity of features
    def examine_features(self, physics, features):
        matplotlib.rc('font', size=7)
        fig = plt.figure(figsize=(12,8))
        colors = list(matplotlib.colors.get_named_colors_mapping().values())

        features_flattened = features.reshape(features.shape[0]*features.shape[1], features.shape[2])

        # Plot actual data for a single random simulation run
        feature_index = 0
        individual_index = np.random.randint(features.shape[1]) 
        features_description = physics.get_observations_description()
        num_feature_groups = len(features_description)
        for i in range(num_feature_groups):
            desc = features_description[i]
            feature_indices = desc[2]
            num_features_in_group = len(feature_indices)
            ax_left = plt.subplot2grid((num_feature_groups, 1000), (i, 0), colspan=500)
            ax_left.set_title(desc[0])
            delta = 500./num_features_in_group
            for i2 in range(num_features_in_group-1,-1,-1): # reverse order so that force is drawn first, just to make chart look better
                ax_left.plot(features[:, individual_index, feature_indices[i2]], linewidth=0.7, color=colors[feature_index+i2])
                ax_right = plt.subplot2grid((num_feature_groups, 1000), (i, 500+int(i2*delta)), colspan=int(delta))
                ax_right.hist(features_flattened[:, feature_indices[i2]], color=colors[feature_index+i2], bins=25, range=(-2,2))
                ax_right.set_title(desc[1][i2])

            feature_index += num_features_in_group

        plt.tight_layout()
        plt.show()
