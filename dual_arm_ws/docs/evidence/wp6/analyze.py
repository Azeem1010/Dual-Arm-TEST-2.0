"""Offline analysis of WP6 evidence. Reads files only; moves nothing."""
from pathlib import Path
import re
import sys

ROOT = Path('/mnt/e/dual_arm_system/dual_arm_ws')
sys.path.insert(0, str(ROOT / 'src/dual_arm_coordinator'))
from dual_arm_coordinator.kinematics import CadKinematics  # noqa: E402

URDF = (ROOT / 'src/dual_arm_description/urdf/dual_arm_cad.urdf.xacro').read_text(encoding='utf-8')
EVIDENCE = ROOT / 'docs/evidence/wp6'
STAMP = re.compile(r'\[(\d{10}\.\d+)\]')


def reach():
    model = CadKinematics(URDF, 'arm1')
    print('cap  x      y       approach  contact')
    for index in range(8):
        x, y = 0.14 + (index % 2) * 0.06, 0.1 - (index // 2) * 0.065
        results = []
        for z in (0.054, 0.0243):
            try:
                model.solve([x, y, z])
                results.append('ok')
            except ValueError:
                results.append('NO_IK')
        print(f'cap_{index + 1} {x:.3f} {y:+.3f}  {results[0]:8}  {results[1]}')


def timing(group):
    starts, ends = [], []
    for line in (EVIDENCE / group / 'sim_launch.log').read_text(errors='replace').splitlines():
        match = STAMP.search(line)
        if match and 'Starting trajectory execution' in line:
            starts.append(float(match.group(1)))
        elif match and 'Completed trajectory execution' in line:
            ends.append(float(match.group(1)))
    pairs = list(zip(starts, ends))
    executing = sum(end - start for start, end in pairs)
    span = pairs[-1][1] - pairs[0][0]
    durations = sorted(end - start for start, end in pairs)
    print(f'{group}: {len(pairs)} trajectories, span {span:.1f} s, executing {executing:.1f} s '
          f'({100 * executing / span:.0f}%), between trajectories {span - executing:.1f} s')
    print(f'  duration min {durations[0]:.1f} median {durations[len(durations) // 2]:.1f} max {durations[-1]:.1f} s')
    print('  in order:', ' '.join(f'{end - start:.1f}' for start, end in pairs[:26]))


reach()
for name in sys.argv[1:]:
    timing(name)
