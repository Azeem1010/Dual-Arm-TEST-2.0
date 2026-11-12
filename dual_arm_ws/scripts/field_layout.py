"""Measured field geometry shared by the model, world and simulation scripts.

The single source for the arm axis positions, the C slot grid and the simulated cap
starts (2026-11-11 measurement, docs/evidence/hardware/20261111_H1/,
docs/COORDINATE_FRAMES.md). Changing a value here and regenerating
(generate_cad_robot.py, generate_world.py) moves everything that depends on it;
test_cad_pose.py checks the generated URDF and test_task_config.py the slot list in
config/sim/coordinator.yaml.
"""
# j1 axes in world: arm1 at -X (zone A side), arm2 at +X, both on the y line about
# 5 mm outside the arm-side edge of the 240 mm board (user's decision 2026-11-12).
ARM_AXIS_X_M = 0.10
ARM_AXIS_Y_M = 0.125
ARM_BASES_XY_M = {'arm1': (-ARM_AXIS_X_M, ARM_AXIS_Y_M), 'arm2': (ARM_AXIS_X_M, ARM_AXIS_Y_M)}

# C slots, numbered as on the real board: 1 and 2 nearest the arms, odd slots in the
# column next to B. Measured from the arm axes: rows 75/110/145/180 mm toward the
# user, columns 235/270 mm from arm1's axis toward C.
SLOT_COLUMNS_X_M = (round(-ARM_AXIS_X_M + 0.235, 4), round(-ARM_AXIS_X_M + 0.270, 4))
SLOT_ROWS_Y_M = tuple(round(ARM_AXIS_Y_M - f, 4) for f in (0.075, 0.110, 0.145, 0.180))
SLOTS_XY_M = [(SLOT_COLUMNS_X_M[col], SLOT_ROWS_Y_M[row]) for row in range(4) for col in range(2)]

# Cap starts in A are a simulation choice; real caps may lie anywhere in A. Caps 1-7
# mirror slots 1-7 about x = 0. The mirror of slot 8 can only be picked with the cup
# tilted, and a cap picked tilted shifts about 1 mm when put down at B, more than
# arm2's suction tolerance (2026-11-12, docs/evidence/tilt_slot8_20261112/). So cap 8
# starts further out, reachable straight down and clear of arm1 at HOME: at
# (-0.205, 0.015) the arm hid part of it from the fixed camera and the simulated
# calibration error rose to 2.2 mm (budget 1 mm).
CAPS_XY_M = [(-x, y) for x, y in SLOTS_XY_M[:7]] + [(-0.24, 0.05)]
