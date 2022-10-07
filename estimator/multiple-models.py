# A DNN reinforcement learning experiment using pyBullet, MuJoCo xml data files and tensorflow estimator API
#
# This experiment creates many different models and tries to improve each model by letting them mimick each other.
# It seeks to use a similar approach at genetic algorithms only the DNN is trained on each others output as a crossover operator.
#
# To avoid the explosive disk usage, the tensorflow python environment should be changed 2 places:
#   1.) Comment out self._ev_writer.WriteEvent(event)` statement in `Anaconda3\envs\tensorflow\Lib\site-packages\tensorflow\python\summary\event_file_writer.py`. This is necesary also to avoid writing a read-only file which DiskCleaner struggles with deleting.
#   2.) The write_graph(..) function in Anaconda3\envs\tensorflow\Lib\site-packages\tensorflow\python\framework\graph_io.py should return instantly without writing any data to disk
#
# Results of a multi-threading scaling test done on a Intel i7 7700k 2018-07-27:
#   Workers, Total time per batch (lower is better)
#   1, 3.8110
#   2, 2.0320
#   3, 1.5840
#   4, 1.3515
#   5, 1.1020
#   6, 1.0020
#   7, 0.9690
#   8, 0.9470
#   9, 0.9880
#   10, 0.9870
#   .	
#   16, 1.0170

# TODO:
#   * Finn ut av stabilitetsproblemene. Prøv å øke tyngdekraften, eventuelt redusere max_force
#   * Endre fitness-funksjon til å se på hastighet i xy-planet
#   * Lag randomized dnn_structure og andre (optimizer, loss operatør osv) når ting ikke er spesifisert. Kan da brukes for hyper-parameter optimalisering.
#   * Test og muligens implementer normalization layers. Se om dette kan automatiseres slik at transfer functions enkelt kan erstattes.
#   * VENT: Gjør mer research først. Implementer auto-termination. Se på en 2. grads regresjon og avbryt når stigningen er liten relativ til initiel fitness
#   * Se på transfer-function, men må da muligens endre standardization... Gjør ferdig normalization først.
#   * Implementer parameterisering ført opp som TODO punkter i NeuralNet.py
#   * Gjør om fitness funksjon til at skapning skal maksimere hastighet fremfor bevege seg bort i fra spawn-koordinat
#   * Test mer avanserte skapninger med flere capsules

from multiprocessing import Process, Queue, JoinableQueue
import deepdish as dd
import json
import msvcrt
import argparse
import os
import shutil
import time
import numpy as np
from copy import deepcopy
from Worker import Worker
from DiskCleaner import DiskCleaner
from Plotting import Plotting

DEFAULT_INITIAL_MODEL_TRIALS = 30
DEFAULT_POPULATION_SIZE = 20         # The number of models kept in the population.
DEFAULT_NUM_GENERATIONS = 100000000

WARMUP_TICKS = 60*5      # Ignore these first ticks for training as they are mostly based on initial conditions with falling etc
DEFAULT_SIMULATION_TICKS = WARMUP_TICKS + 60*30  # 60*60
DEFAULT_NUM_SIMULTANOUS_SIMULATIONS = 20
DEFAULT_CROSSOVER_TRAINING_EPOCHS = 100
default_num_workers = os.cpu_count()    # num threads

storage = {
    "population": []
}

analyze_crossover_training_epochs = [i for i in range(1,500)]
analyze_crossover_training_results = []

def parse_command_line_arguments():
    parser = argparse.ArgumentParser(description='Reinforcement learning prototype. Multiple models evolve experiment.')
    parser.add_argument("directory", help="Directory for data. If used before, everything will be loaded from here and resumed. If not, new models will be created with settings as defined by the other command line arguments.", action="store")		
    parser.add_argument("dnn_structure_filename", help="Filename of json file with configuraiton of the neural network.", action="store", nargs='?')
    parser.add_argument("--num_workers", help="The number of worker processes to spawn. [default auto-detected threads={}]".format(default_num_workers), default=default_num_workers, nargs='?', type=int)		
    parser.add_argument("--population_size", help="The number of models that will be kept in the population.", default=DEFAULT_POPULATION_SIZE, nargs='?', type=int)		
    parser.add_argument("--initial_model_trials", help="The number of randomly created models that will be tried when creating the initial population.", default=DEFAULT_INITIAL_MODEL_TRIALS, nargs='?', type=int)		
    parser.add_argument("--simulation_ticks", help="The number of ticks to perform each simulation.", default=DEFAULT_SIMULATION_TICKS, nargs='?', type=int)		
    parser.add_argument("--num_simultanous_simulations", help="The number of simulations that should be run in parallell for each model", default=DEFAULT_NUM_SIMULTANOUS_SIMULATIONS, nargs='?', type=int)		
    parser.add_argument("--crossover_training_epochs", help="The number of training epochs that should be performed for each individual during crossover where learning to mimic another individual.", default=DEFAULT_CROSSOVER_TRAINING_EPOCHS, nargs='?', type=int)		
    parser.add_argument("--num_generations", help="Stop the script after this many generations have been trained.", default=-1, nargs='?', type=int)
    parser.add_argument('--analyze_crossover_training', action='store_true')
    return parser.parse_args()

def save_storage_base(path_and_filename, storage):
    start_time = time.clock()
    path_and_filename_backup = path_and_filename.replace("storage.h5", "storage_backup.h5")
    if os.path.isfile(path_and_filename):
        shutil.copy(path_and_filename, path_and_filename_backup)
    dd.io.save(path_and_filename, storage, "blosc")
    print("Saved {} in {:.3f} seconds.".format(path_and_filename, time.clock() - start_time))

def get_creature_path(creature_id):
    return args.directory + "\\" + creature_id

def spawn_worker(base_path, storage, task_queue, result_queue):
    dnn_config = deepcopy(storage["dnn_structure"])

    worker = Worker(base_path, storage["num_simultanous_simulations"], storage["simulation_ticks"], storage["warmup_ticks"], dnn_config)
    while True:
        task = task_queue.get()
        result = worker.do_work(task)
        result_queue.put(result)
        task_queue.task_done()

def handle_worker_result(result):
    def get_creature_fitness(id):
        creature = [i for i in storage["population"] if i["id"] == id]
        if not len(creature) == 1:
            print("ERROR: Could not retrieve creature with id {} from population. Expecting len=1, got len={}".format(id, len(creature)))
            exit()
        return creature[0]["fitness"]

    creature = result["creature"]

    accepted = False
    if len(storage["population"]) < storage["population_size"]:
        # Fill initial population
        storage["population"].append(creature)
        accepted = True
    else:
        # Replace weakest creature
        fitnesses = [x["fitness"] for x in storage["population"]]
        index = np.argmin(fitnesses)
        if creature["fitness"] > storage["population"][index]["fitness"]:
            disk_cleaner.mark_for_delete(get_creature_path(storage["population"][index]["id"]))
            storage["population"][index] = creature
            accepted = True

    if result["task"] == "initial":
        # For creating initial population
        storage["initial_random_distance_history"].append(creature["fitness"])
        storage["initial_model_trials_completed"] += 1
    else:
        # For evolving existing population
        storage["distances_history"] = np.append(storage["distances_history"], result["distances"], axis=0)
        
        if is_analyze_crossover_training:
            analyze_crossover_training_results.append({
                "fitness": result["creature"]["fitness"],
                "generation": storage["iteration_index"],
                "clone_fitness": get_creature_fitness(result["clone_id"]),
                "mimic_fitness": get_creature_fitness(result["mimic_id"]),
                "epochs": result["epochs"]})

        if storage["iteration_index"] == 0:
            storage["initial_mean_kept_distance"] = np.mean([x["fitness"] for x in storage["population"]])

        storage["iteration_index"] += 1

    if not accepted:
        disk_cleaner.mark_for_delete(get_creature_path(creature["id"]))

def get_next_task():
    def get_crossover_task():
        def get_ids_for_clone_and_mimic_creatures():
            def get_id_of_best_creature(id_1, id_2):
                return storage["population"][id_1]["id"] if storage["population"][id_1]["fitness"] > storage["population"][id_2]["fitness"] else storage["population"][id_2]["id"]

            population_ids = np.arange(len(storage["population"]))
            np.random.shuffle(population_ids)
            ids = population_ids[:4]

            return get_id_of_best_creature(ids[0], ids[1]), get_id_of_best_creature(ids[2], ids[3])

        creature_id_to_clone, creature_id_to_mimic = get_ids_for_clone_and_mimic_creatures()

        if is_analyze_crossover_training:
            epochs = np.random.choice(analyze_crossover_training_epochs)
        else:
            epochs = storage["crossover_training_epochs"]

        return {
            "task": "crossover", 
            "clone_creature_id": creature_id_to_clone, 
            "mimic_creature_id": creature_id_to_mimic, 
            "epochs": epochs}

    def get_initial_population_task():
        return {"task": "initial" }

    if storage["initial_model_trials_completed"] >= storage["initial_model_trials_target"]:
        return get_crossover_task()
    else:
        return get_initial_population_task()


if __name__ == '__main__':
    args = parse_command_line_arguments()
    if not os.path.exists(args.directory):
        os.makedirs(args.directory)
        os.makedirs(args.directory + "\\robot_file_definitions")
    is_first_run = False
    storage_file_path = args.directory + "\\storage.h5"
    is_analyze_crossover_training = args.analyze_crossover_training
    save_storage = lambda : save_storage_base(storage_file_path, storage)
    disk_cleaner = DiskCleaner()
    plotting = Plotting()

    try:
        storage = dd.io.load(storage_file_path)
    except OSError:
        is_first_run = True
        print("Could not find storage in {}. Assuming this is the first run against this directory.".format(storage_file_path))

    if is_first_run:
        with open(args.dnn_structure_filename, "r") as f:
            dnn_structure = json.load(f)

        storage["dnn_structure"] = dnn_structure
        storage["population_size"] = args.population_size
        storage["initial_model_trials_target"] = max(args.initial_model_trials, storage["population_size"])
        storage["initial_model_trials_completed"] = 0
        storage["simulation_ticks"] = max(args.simulation_ticks, WARMUP_TICKS)
        storage["num_simultanous_simulations"] = max(args.num_simultanous_simulations, 1)
        storage["initial_random_distance_history"] = []
        storage["distances_history"] = np.zeros((0, storage["num_simultanous_simulations"]))
        storage["initial_mean_kept_distance"] = -1
        storage["warmup_ticks"] = WARMUP_TICKS
        storage["iteration_index"] = 0
        storage["crossover_training_epochs"] = args.crossover_training_epochs
        storage["num_generations"] = args.num_generations if args.num_generations != -1 else DEFAULT_NUM_GENERATIONS
        save_storage()
    else:
        if args.num_generations != -1:
            # num_generations was explicitly specified for an existing storage: Use the new value
            storage["num_generations"] = args.num_generations if args.num_generations != -1 else DEFAULT_NUM_GENERATIONS
        elif not "num_generations" in storage:
            storage["num_generations"] = 10000000    # Backward compability: Old projects trained indefinetly, continue this behaviour

        # Provide backward compability:
        if not "crossover_training_epochs" in storage:
            storage["crossover_training_epochs"] = 1    # Old projects without crossover_training_epochs only used a value of 1

    is_early_exit = storage["iteration_index"] >= storage["num_generations"]

    if not is_early_exit:
        print("{}, using settings:".format("Creating new project" if is_first_run else "Loaded from disk"))
        keys = ["num_generations", "crossover_training_epochs", "dnn_structure", "population_size", "simulation_ticks", "num_simultanous_simulations", "warmup_ticks", "initial_model_trials_target", "initial_model_trials_completed", "iteration_index"]
        settings = ""
        for key in keys:
            if settings != "":
                settings = settings + ", "
            settings = settings + "{} = {}".format(key, storage[key])
        print(settings)

        processes = []
        result_queue = Queue()
        task_queue = JoinableQueue()
        for i in range(args.num_workers):
            p = Process(target=spawn_worker, args=(args.directory, storage, task_queue, result_queue))
            p.start()
            processes.append(p)
    
        backup_time_stamp = time.clock()

    while not is_early_exit and storage["iteration_index"] < storage["num_generations"]:
        batch_start_time = time.clock()
        for i in range(args.num_workers):
            task_queue.put(get_next_task())
        
        if batch_start_time > backup_time_stamp + 60:    # Do IO while workers are busy
            disk_cleaner.clean()
            save_storage()
            backup_time_stamp = batch_start_time

        task_queue.join()   # Wait for all workers to finish

        time_per_task = 1./args.num_workers * (time.clock() - batch_start_time)

        fitnesses = []
        while not result_queue.empty():
            result = result_queue.get()
            fitnesses.append(result["creature"]["fitness"])
            handle_worker_result(result)
     
        print("{} tasks completed. Average fitness={:.3f}. {}. Time per task={:.3f}s".format(
            args.num_workers, 
            np.mean(fitnesses),
            "initial {}/{}".format(storage["initial_model_trials_completed"], storage["initial_model_trials_target"]) if storage["initial_model_trials_completed"] < storage["initial_model_trials_target"] else "Generation={}".format(storage["iteration_index"]),
            time_per_task
            ))

        key_pressed = False
        while msvcrt.kbhit():   # detect a keypress from the previous iteration
            msvcrt.getch()      # empty keyboard buffer
            key_pressed = True
    
        if key_pressed:
            a = input("Break out of iteration loop (Y/N)?[Y]: ")
            if len(a) == 0 or a == "y" or a == "Y" or a == "yes" or a == "Yes" or a == "YES":
                print("Terminating...")
                break
            else:
                print("Continuing iteration loop...")

    if is_early_exit:
        print("Popluation already trained {} generations which exceeds num_generations={}. Terminating...".format(storage["iteration_index"], storage["num_generations"]))
    else:
        for p in processes:
            p.terminate()
        disk_cleaner.clean()
        save_storage()
        
        if is_analyze_crossover_training:
            # Normalize fitness
            epochs = []
            normalized_y = []
            generations = []
            for result in analyze_crossover_training_results:
                # map epoch to [0,1], where 0 is zero epochs and 1 is the maximum epoch tested
                epoch_ratio = result["epochs"] / max(analyze_crossover_training_epochs)
                expected_fitness = result["clone_fitness"] + epoch_ratio * (result["mimic_fitness"] - result["clone_fitness"])
                normalized_fitness = (result["fitness"] - expected_fitness) / result["clone_fitness"]
                epochs.append(result["epochs"])
                normalized_y.append(normalized_fitness)
                generations.append(result["generation"])

                print("clone {:.4} -> mimic {:.4}, epoch {} = {:.4} vs expected {:.4} (normalized = {:.4})".format(result["clone_fitness"], result["mimic_fitness"], result["epochs"], result["fitness"], expected_fitness, normalized_fitness))
            
            plotting.analyze_crossover(epochs, normalized_y, generations)


# Testing determinism:
#_, _, positions_batch, servers = data_generator.create_raw_data_batch(neural_net)
#_, _, positions_batch, servers = data_generator.create_raw_data_batch(neural_net, servers)
#print("model #1, tick #1: ({:.3f}, {:.3f})".format(positions_batch[-1,0,0], positions_batch[-1,0,1]))
#print("model #1, tick #2: ({:.3f}, {:.3f})".format(positions_batch[-1,0,0], positions_batch[-1,0,1]))

#neural_net = NeuralNet(features_rank, labels_rank, model_dir = "model_dir\\determinisme-test-2")
#_, _, positions_batch, servers = data_generator.create_raw_data_batch(neural_net, servers)
#print("model #2, tick #1: ({:.3f}, {:.3f})".format(positions_batch[-1,0,0], positions_batch[-1,0,1]))

#neural_net = NeuralNet(features_rank, labels_rank, model_dir = "model_dir\\determinisme-test")
#_, _, positions_batch, servers = data_generator.create_raw_data_batch(neural_net, servers)
#print("model #1, tick #3: ({:.3f}, {:.3f})".format(positions_batch[-1,0,0], positions_batch[-1,0,1]))