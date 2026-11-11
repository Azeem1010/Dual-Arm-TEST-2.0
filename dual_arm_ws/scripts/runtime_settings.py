"""Shared simulation geometry, speeds and explicit HOME calibration requirements."""
from pathlib import Path
import json
import sys
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/dual_arm_coordinator'))
from dual_arm_coordinator.home_pose import convert_home

SETTINGS=json.loads((ROOT/'src/dual_arm_coordinator/config/sim/runtime.json').read_text())
SURFACE_Z=SETTINGS['surface_z_m']
CAP_CENTER_Z=SURFACE_Z+SETTINGS['cap_height_m']/2
CONTACT_Z=SURFACE_Z+SETTINGS['cap_height_m']+.0003
# Field layout from the simulation task config (generate_world.py writes the same values).
# Caps start at the C slots mirrored about x = 0.
ZONES=yaml.safe_load((ROOT/'src/dual_arm_coordinator/config/sim/coordinator.yaml').read_text(encoding='utf-8'))['zones']
SLOTS_XY=[tuple(xy) for xy in ZONES['c_slots_xy_m']]
CAPS_XY=[(-x,y) for x,y in SLOTS_XY]
B_XY=tuple(ZONES['b_place_xy_m'])


def configured_homes(models):
    homes={}
    for arm,model in models.items():
        config=SETTINGS['home'][arm]
        try:
            q=convert_home(config['raw'],config['raw_at_cad_zero'],config['direction'])
        except ValueError as error:
            raise ValueError(config['name']+': '+str(error)+'. See docs/HOME_POSES.md.') from error
        if any(value<lo or value>hi for value,lo,hi in zip(q,model.lower,model.upper)):
            raise ValueError(config['name']+' exceeds current model limits; do not widen limits to bypass this')
        homes[arm]=q
    return homes
