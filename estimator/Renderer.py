# Handles all rendering to the screen

import numpy as np

import pybullet as p

class Renderer:
    def __init__(self, physics):
        self.physics = physics

    def render_robot(self, neural_net, steps = 60*30, sleep_tick_modulo=1, distance_travelled_extra_info = True):
        def get_distance(position):
            distance = np.sqrt(np.sum(np.array(position[0:2])**2))
            return distance

        try:
            camera_target_smoothed = np.array([0,0,0])
            predictor = neural_net.get_predictor()
            server = self.physics.create_robot_for_rendering()
            line_id, text_id, debug_color = None, None, (0, 0, 1)

            for i in range(steps):
                observations = self.physics.get_observations_for_server(server, i)
                predictor_output = predictor({"x": observations.reshape(1, observations.shape[0]) })
                self.physics.apply_forces_on_server(server, predictor_output["output"][0])
                self.physics.tick_rendering_server(i % sleep_tick_modulo == 0)

                position, _ = p.getBasePositionAndOrientation(server["robot_id"], physicsClientId=server["id"])
                camera_target_smoothed = .98 * camera_target_smoothed + .02 * np.array(position)

                p.resetDebugVisualizerCamera( cameraDistance=4, cameraYaw=50, cameraPitch=-35, cameraTargetPosition=camera_target_smoothed, physicsClientId=server["id"])

                if distance_travelled_extra_info and i % 60 == 0:
                    if line_id:
                        p.removeUserDebugItem(line_id, physicsClientId=server["id"])
                    if text_id:
                        p.removeUserDebugItem(text_id, physicsClientId=server["id"])
                    line_id = p.addUserDebugLine(
                        (0,0,0), (position[0], position[1], 0), 
                        lineColorRGB = debug_color,
                        lineWidth = 5,
                        physicsClientId=server["id"])
                    text_id = p.addUserDebugText(
                        "{:.3f}".format(get_distance(position)),
                        (position[0], position[1], 1.2),
                        textColorRGB = debug_color,
                        textSize = 1,
                        physicsClientId=server["id"])
            
            if distance_travelled_extra_info:
                print("Rendering robot travelled {}".format(get_distance(self.physics.get_rendering_robot_position())))

            self.physics.destroy_robot(server)
        except Exception as e:
            print("exception={}".format(e))