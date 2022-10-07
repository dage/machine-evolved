# A simple test for CreatureStructure

from CreatureStructure import CreatureStructure, CAPSULE

capsule = CAPSULE(100, 50, 11.725204, 16.815704, 259.013641, 0.623920, -0.739164, -0.121800, 0.222544, None)
structure = CreatureStructure()
structure.addCapsule(capsule)
structure.addCapsuleWithConstraint(200, 100, capsule)

structureCopy = CreatureStructure(structure.serialize())

print("numConstraints = " + str(structure.getNumConstraints()))
print("numMotors = " + str(structure.getNumOutputs()))
print("stateSize = " + str(structure.getNumInputs()))
print("----")
print("structure:" + structure.serialize())
print("structureCopy:" + structureCopy.serialize())
