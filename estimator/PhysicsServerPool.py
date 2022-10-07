# PhysicsServerPool
#
# Runs a set of simultanous physics server and provides support for performing
# inference on a batch of simultanously simulated robots.

import pybullet as p
import pybullet_data
import time
import copy
import numpy as np
import math
from RobotFileFactory import RobotFileFactory

class PhysicsServerPool:
    MAX_FORCE = 100000
    MAX_FORCES = [MAX_FORCE] * 3
    EMPTY_SERVER_CONFIG = { "id": None, "robot_id": None, "orientation": None }
    OSCILLATORS_ANGLE_MULTIPLIERS = [0.25, 0.5, 1., 2., 4.]

    # Standardization constants:
    BASE_POS_COL_num_collisions_std = 0.58711
    BASE_POS_COL_num_collisions_mean = -0.10295
    BASE_POS_COL_quaternion_w_std = 0.48296
    BASE_POS_COL_quaternion_w_mean = 0.09722
    BASE_POS_COL_quaternion_x_std = 0.49170
    BASE_POS_COL_quaternion_x_mean = 0.05241
    BASE_POS_COL_quaternion_y_std = 0.49623
    BASE_POS_COL_quaternion_y_mean = 0.05081
    BASE_POS_COL_quaternion_z_std = 0.48676
    BASE_POS_COL_quaternion_z_mean = 0.05079
    BASE_POS_COL_z_position_std = 1.15392
    BASE_POS_COL_z_position_mean = 0.66409
    BASE_VEL_angular_x_std = 2.77622
    BASE_VEL_angular_x_mean = -0.00089
    BASE_VEL_angular_y_std = 2.78946
    BASE_VEL_angular_y_mean = 0.00718
    BASE_VEL_angular_z_std = 2.52017
    BASE_VEL_angular_z_mean = -0.01869
    BASE_VEL_linear_x_std = 1.49196
    BASE_VEL_linear_x_mean = -0.00377
    BASE_VEL_linear_y_std = 1.54756
    BASE_VEL_linear_y_mean = 0.01143
    BASE_VEL_linear_z_std = 1.40037
    BASE_VEL_linear_z_mean = -0.00760
    JOINT_force_std = 0.90574 # [0.8382459 0.9405701 0.9384172]
    JOINT_force_mean = 0.00082 # [1.1126519e-05 1.2880540e-03 1.1625550e-03]
    JOINT_position_std = 0.27910 # [0.29166552 0.25872353 0.2869125 ]
    JOINT_position_mean = -0.00207 # [ 0.00028892 -0.00391825 -0.00257636]
    JOINT_velocity_std = 0.61481 # [0.71217304 0.55389315 0.57835543]
    JOINT_velocity_mean = -0.00001 # [-2.2912751e-05 -5.9304464e-05  5.1072828e-05]
    OSC_o1_std = 0.71056
    OSC_o1_mean = -0.01576
    OSC_o2_std = 0.70661
    OSC_o2_mean = 0.01131
    OSC_o3_std = 0.70667
    OSC_o3_mean = -0.01117
    OSC_o4_std = 0.70709
    OSC_o4_mean = -0.00000
    OSC_o5_std = 0.71708
    OSC_o5_mean = -0.00000

    OSC_std = np.array([OSC_o1_std, OSC_o2_std, OSC_o3_std, OSC_o4_std, OSC_o5_std])
    OSC_mean = np.array([OSC_o1_mean, OSC_o2_mean, OSC_o3_mean, OSC_o4_mean, OSC_o5_mean])
    BASE_POS_COL_quaternion_std = np.array([BASE_POS_COL_quaternion_x_std, BASE_POS_COL_quaternion_y_std, BASE_POS_COL_quaternion_z_std, BASE_POS_COL_quaternion_w_std])
    BASE_POS_COL_quaternion_mean = np.array([BASE_POS_COL_quaternion_x_mean, BASE_POS_COL_quaternion_y_mean, BASE_POS_COL_quaternion_z_mean, BASE_POS_COL_quaternion_w_mean])
    BASE_VEL_linear_std = np.array([BASE_VEL_linear_x_std, BASE_VEL_linear_y_std, BASE_VEL_linear_z_std])
    BASE_VEL_linear_mean = np.array([BASE_VEL_linear_x_mean, BASE_VEL_linear_y_mean, BASE_VEL_linear_z_mean])
    BASE_VEL_angular_std = np.array([BASE_VEL_angular_x_std, BASE_VEL_angular_y_std, BASE_VEL_angular_z_std])
    BASE_VEL_angular_mean = np.array([BASE_VEL_angular_x_mean, BASE_VEL_angular_y_mean, BASE_VEL_angular_z_mean])
    # -----------------------------------------------------------------------

    rendering_server = EMPTY_SERVER_CONFIG.copy()

    def __init__(self, robot_file_definition_path, num_simultaneous_simulations=10, robot_type=RobotFileFactory.ROBOT_CAPSULES_2):
        self.robot_file_factory = RobotFileFactory(robot_file_definition_path)
        self.robot_type = robot_type
        self.num_simultaneous_simulations = num_simultaneous_simulations
        self.servers = [self.EMPTY_SERVER_CONFIG.copy() for n in range(num_simultaneous_simulations)]
        for server in self.servers:
            id = 0
            while id==0:        # There is some strange behaviour with server with id=0 (maybe a broken check like "if not id:" where both 0 and None is equivalent??), so just ignoring this server instance for now.
                id = p.connect(p.DIRECT)
            server["id"] = id

        self.__calculate_ranks()
 
    def __del__(self):
        for server in self.servers:
            p.disconnect(physicsClientId=server["id"])

    def __get_active_servers(self):
        return [server for server in self.servers if server["robot_id"] != None]

    def get_observations(self, tick):
        all_observations = np.empty((self.num_simultaneous_simulations, self.features_rank), dtype=np.float32)
        active_servers = self.__get_active_servers()
        for i in range(len(active_servers)):
            server = active_servers[i]
            all_observations[i] = self.get_observations_for_server(server, tick)
        return all_observations

    def apply_forces_on_server(self, server, forces):
        p.setJointMotorControlArray(
            server["robot_id"], 
            self.joint_indices, 
            controlMode=p.POSITION_CONTROL, 
            targetPositions=forces, 
            forces=self.MAX_FORCES,
            physicsClientId=server["id"])

    def apply_forces(self, forces):
        active_servers = self.__get_active_servers()
        for i in range(len(active_servers)):
            self.apply_forces_on_server(active_servers[i], forces[i])

    def tick(self):
        for server in self.__get_active_servers():
            p.stepSimulation(physicsClientId=server["id"])

    def tick_rendering_server(self, sleep = True):
        p.stepSimulation(physicsClientId=self.rendering_server["id"])
        if sleep:
            time.sleep(1./60)

    def create_robot_for_rendering(self):
        try:
            self.rendering_server["id"] = p.connect(p.GUI)
        except Exception as e:
            print("Unable to connect to a GUI physics server. Assuming already connected and will continue... Exception={}".format(e))

        return self.create_robot(existing_server = self.rendering_server)

    def create_all_robots(self, existing_servers = None):
        for i in range(len(self.servers)):
            self.servers[i] = self.create_robot(existing_servers[i] if existing_servers != None else None)

    def create_robot(self, existing_server = None, is_randomized = True):
        def get_first_available_server():
            for server in self.servers:
                if server["robot_id"] == None:
                    return server

        INITIAL_HEIGHT = 1
        server = existing_server or get_first_available_server()

        is_initial_collision = True
        while is_initial_collision:
            p.setPhysicsEngineParameter(fixedTimeStep=1.0/60., numSolverIterations=5, numSubSteps=2)
            p.setAdditionalSearchPath(pybullet_data.getDataPath(), physicsClientId=server["id"])
            p.setGravity(0, 0, -50, physicsClientId=server["id"])  # A constant of -9.8 should be used and the world scaled down

            filename = self.robot_file_factory.create(RobotFileFactory.ROBOT_CAPSULES_2, INITIAL_HEIGHT, is_orientation_randomized=is_randomized)
            mjcfInfo = p.loadMJCF(filename, flags = p.URDF_USE_SELF_COLLISION_EXCLUDE_ALL_PARENTS, physicsClientId=server["id"])
            server["robot_id"] = mjcfInfo[1]
            self.robot_file_factory.delete(filename)

            if is_randomized:
                tick = 0
                warmup_ticks = 30
                is_collision_triggered = False
                MAX_ANGULAR_POSITION = 1.57		# range property from joint definition in mujoco .xml file
                target_positions = (MAX_ANGULAR_POSITION*(-1+2*np.random.rand(1,3)))[0].tolist()
                while tick < warmup_ticks and not is_collision_triggered:
                    p.setJointMotorControlArray(
                        server["robot_id"], 
                        self.joint_indices, 
                        controlMode=p.POSITION_CONTROL, 
                        targetPositions=target_positions,
                        forces=self.MAX_FORCES, 
                        physicsClientId=server["id"])
                    p.stepSimulation(physicsClientId=server["id"])

                    collision = p.getContactPoints(physicsClientId=server["id"])

                    if tick == 0:
                        is_initial_collision = True if collision else False

                        if is_initial_collision:
                            # Start over if robot started in a initial collision state (bellow ground)
                            p.resetSimulation(physicsClientId=server["id"])
                
                    is_collision_triggered = is_collision_triggered or (True if collision else False)

                    tick += 1
            else:
                is_initial_collision = False

        return server

    def destroy_all_robots(self):
        for server in self.servers:
            self.destroy_robot(server)

    def destroy_robot(self, server):
        is_rendering_robot = self.rendering_server["id"] == server["id"]
        if is_rendering_robot:
            p.disconnect(physicsClientId=server["id"])
        else:
            p.resetSimulation(physicsClientId=server["id"])

        server["robot_id"] = None
        server["orientation"] = None    

    def __get_active_joint_indices(self, server):
        indices = []
        for i in range(p.getNumJoints(server["robot_id"], physicsClientId=server["id"])):
            jointInfo = p.getJointInfo(server["robot_id"], i, physicsClientId=server["id"])
            if jointInfo[2] == p.JOINT_REVOLUTE:	# Currently only hinge/revolute supported
                indices.append(i)
        return indices

    def get_observations_for_server(self, server, tick):
        def get_base_states():
            position, initial_orientation = p.getBasePositionAndOrientation(server["robot_id"], physicsClientId=server["id"])

            orientation = np.array(initial_orientation)
            if isinstance(server["orientation"], np.ndarray):   # not first run?
                # avoid the sudden quaternion sign flip by picking the quaternion that are closest to the orientation of the previous simulation tick
                flipped_orientation = -orientation
                distance = np.sum(np.absolute(server["orientation"] - orientation))
                flipped_distance = np.sum(np.absolute(server["orientation"] - flipped_orientation))
                if flipped_distance < distance:
                    orientation = flipped_orientation   # We have a sudden sign flip detected and now corrected
            server["orientation"] = orientation

            velocity = p.getBaseVelocity(server["robot_id"], physicsClientId=server["id"])

            direction = np.array(position[0:2])
            direction_length = np.sqrt(np.sum(direction**2))
            direction_standarized = (.7/direction_length if direction_length > 0 else 1.)*direction 

            # apply standardization:
            position_z = position[2] / self.BASE_POS_COL_z_position_std - self.BASE_POS_COL_z_position_mean
            orientation = orientation / self.BASE_POS_COL_quaternion_std - self.BASE_POS_COL_quaternion_mean
            velocity_linear = np.array(velocity[0]) / self.BASE_VEL_linear_std - self.BASE_VEL_linear_mean
            velocity_angular = np.array(velocity[1]) / self.BASE_VEL_angular_std - self.BASE_VEL_angular_mean
        
            return [*direction_standarized, position_z, *orientation, *velocity_linear, *velocity_angular]

        def get_joint_states():
            observables = []    # TODO: Optimize with predefined size
            for i in range(p.getNumJoints(server["robot_id"], physicsClientId=server["id"])):   # TODO: Use known labels_rank instead
                jointInfo = p.getJointInfo(server["robot_id"], i, physicsClientId=server["id"]) # TODO: See if there are any batch versions of these functions
                if jointInfo[2] == p.JOINT_REVOLUTE:	# Currently only hinge/revolute supported
                    lowerLimit = jointInfo[8]
                    upperLimit = jointInfo[9]
                    middle = 0.5 * (lowerLimit + upperLimit)

                    jointState = p.getJointState(server["robot_id"], i, physicsClientId=server["id"])
                    position = 2 * (jointState[0] - middle) / (upperLimit - lowerLimit)
                    velocity = 0.15 * jointState[1]
                    force = jointState[3] / self.MAX_FORCE

                    # apply standardization:
                    position = position / self.JOINT_position_std - self.JOINT_position_mean
                    velocity = velocity / self.JOINT_velocity_std - self.JOINT_velocity_mean
                    force = force / self.JOINT_force_std - self.JOINT_force_mean

                    observables.append(position)
                    observables.append(velocity)
                    observables.append(force)	
            return observables

        def get_oscillators(tick):
            def get_y(angle_multiplier):
                return math.sin(tick/60*angle_multiplier*np.pi)
            return np.array([get_y(i) for i in self.OSCILLATORS_ANGLE_MULTIPLIERS]) / self.OSC_std - self.OSC_mean

        collisions = p.getContactPoints(physicsClientId=server["id"])
        num_collisions = -1+2*len(collisions)/(self.labels_rank+1) if hasattr(self, "labels_rank") else 0
        
        # Apply standardization:
        num_collisions = num_collisions / self.BASE_POS_COL_num_collisions_std - self.BASE_POS_COL_num_collisions_mean

        return np.array([*get_oscillators(tick), num_collisions, *get_base_states(), *get_joint_states()], dtype=np.float32)

    def get_observations_description(self):
        num_oscillators = len(self.OSCILLATORS_ANGLE_MULTIPLIERS)

        groups = [
            (   "Oscillators",                                          # Category name
                ["o{}".format(i+1) for i in range(num_oscillators)],    # Descriptive key name
                [i for i in range(num_oscillators)],                    # Indices into observations
                "OSC"                                                   # Type
            ),
            (   "Base positions and collision",
                ["num_collisions", "direction_x", "direction_y", "z_position", "quaternion_x", "quaternion_y", "quaternion_z", "quaternion_w"],
                [i for i in range(num_oscillators, num_oscillators+8)],
                "BASE_POS_COL"
            ),
            (   "Base velocity",
                ["linear_x", "linear_y", "linear_z", "angular_x", "angular_y", "angular_z"],
                [i for i in range(num_oscillators+8, num_oscillators+8+6)],
                "BASE_VEL"
            )]

        start_index = num_oscillators+8+6
        joint_groups = [
            (   "Joint {}".format(i),
                ["position", "velocity", "force"],
                [start_index + 3*i + i2 for i2 in range(3)],
                "JOINT"
            ) for i in range(self.labels_rank)
            ]

        return groups + joint_groups

    def __calculate_ranks(self):
        temporary_server = self.create_robot(is_randomized=False)
        self.features_rank = self.get_observations_for_server(temporary_server, 0).shape[0]
        self.joint_indices = self.__get_active_joint_indices(temporary_server)
        self.labels_rank = len(self.joint_indices)
        self.destroy_robot(temporary_server)

    def get_ranks(self):
        return self.features_rank, self.labels_rank

    def get_rendering_robot_position(self):
        position, orientation = p.getBasePositionAndOrientation(self.rendering_server["robot_id"], physicsClientId=self.rendering_server["id"])
        return position

    def get_cloned_servers(self):
        return copy.deepcopy(self.servers)

    def get_robot_positions(self):
        active_servers = self.__get_active_servers()
        positions = np.empty((len(active_servers), 3), dtype=np.float32)
        for i in range(len(active_servers)):
            server = active_servers[i]
            position, orientation = p.getBasePositionAndOrientation(server["robot_id"], physicsClientId=server["id"])
            positions[i] = position
        return positions