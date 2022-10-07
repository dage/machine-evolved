# RobotFileFactory.py
#
# Serves configurable mujoco xml based robots as files, meant to be served from a memory based file system.

import uuid
import os
from pyquaternion import Quaternion

class RobotFileFactory:
    ROBOT_CAPSULES_2 = 1
    
    TEMPLATE_TAGS_INITIAL_Z_HEIGHT = "$$$TEMPLATE_TAGS_INITIAL_Z_HEIGHT$$$"
    TEMPLATE_TAGS_ORIENTATION_QUATERNIONS = "TEMPLATE_TAGS_ORIENTATION_QUATERNIONS"

    filenames_this_session = []

    # TODO: Finn ut hvor man konfigurer maks-kraften som gjør at constraints ikke blir brutt. armature?? damping?? stiffness?? Kan leses ut i PhysicsServerPool på joint info tror jeg....

    robot_type_to_template = {
        ROBOT_CAPSULES_2: """       # http://mujoco.org/book/modeling.html#CSchema
            <mujoco model='capsules_2'> 
                <worldbody>
                    <geom name='floor' pos='0 0 0' size='10 10 0.125' type='plane' material="MatPlane" condim='3' friction='100'/>
                    <body name='capsule-1-body' """ + TEMPLATE_TAGS_ORIENTATION_QUATERNIONS + """ """ + TEMPLATE_TAGS_INITIAL_Z_HEIGHT + """>
                      <geom name='capsule-1' type='capsule' fromto='-.5 0 0 .5 0 0' size='0.5' />          
                      <body name='capsule-2-body' pos='0 0 0'>
                        <joint name='capsule-1-2-x' type='hinge' range='-1.57 1.57' limited='true' pos='1 0 0' axis='1 0 0' damping='1e-7' stiffness='1' armature='1e-3' />
                        <joint name='capsule-1-2-y' type='hinge' range='-1.57 1.57' limited='true' pos='1 0 0' axis='0 1 0' damping='1e-7' stiffness='1' armature='1e-3' />
                        <joint name='capsule-1-2-z' type='hinge' range='-1.57 1.57' limited='true' pos='1 0 0' axis='0 0 1' damping='1e-7' stiffness='1' armature='1e-3' />
                        <geom name='capsule-2' type='capsule' fromto='1.5 0 0 2.5 0 0' size='0.5' />
                      </body>
                    </body>
                </worldbody>
            </mujoco>"""
    }

    def __init__(self, robot_file_definition_path):
        self.robot_file_definition_path = robot_file_definition_path

    # Returns the filename for the newly created robot mujoco xml file
    def create(self, robot_type, initial_height = 2, is_orientation_randomized = True):
        def get_transformed_template(robot_type):
            quaternion = Quaternion.random()    # http://kieranwynn.github.io/pyquaternion/#random

            template = self.robot_type_to_template[robot_type]
            transformed = template.replace(
                self.TEMPLATE_TAGS_INITIAL_Z_HEIGHT, 
                "pos='0 0 {}'".format(initial_height))

            orientation = "quat={}".format(quaternion.elements).replace("[", "'").replace("]", "'") if is_orientation_randomized else ""
            transformed = transformed.replace(
                self.TEMPLATE_TAGS_ORIENTATION_QUATERNIONS, 
                orientation)
            
            return transformed

        filename = "{}\\{}.xml".format(self.robot_file_definition_path, uuid.uuid4())
        file = open(filename, "w+")
        file.write(get_transformed_template(robot_type))
        file.close()
        return filename

    # Call this when finished with the file created with create()
    def delete(self, filename):
        try:
            os.remove(filename)
        except Exception:
            pass
