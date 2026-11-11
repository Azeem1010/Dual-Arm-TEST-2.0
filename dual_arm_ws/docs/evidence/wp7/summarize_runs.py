"""Summarize the repeated vision pick runs. Reads reports only."""
import json
from pathlib import Path
import sys

base = Path(sys.argv[1])
for path in sorted(item for item in base.iterdir() if item.is_dir() and item.name.startswith('pick')):
    name = path.name
    report = json.loads((base / name / 'report.json').read_text(encoding='utf-8'))
    run = report['checks'].get('two_objects_succeeded_with_vision_targets', {})
    observations = report['observations']
    print(name, report['status'], '|', run.get('detail'))
    positions, tcp = observations.get('final_cap_positions', {}), observations.get('final_tcp')
    if tcp and run.get('status') == 'FAIL':
        arm2 = tcp['arm2']['tcp_m']
        print('   arm2 tcp', [round(v, 5) for v in arm2], 'tilt', round(tcp['arm2']['tool_tilt_deg'], 3))
        near = sorted(positions.items(), key=lambda item: (item[1][0] - arm2[0]) ** 2 + (item[1][1] - arm2[1]) ** 2)[0]
        lateral = ((near[1][0] - arm2[0]) ** 2 + (near[1][1] - arm2[1]) ** 2) ** 0.5
        print('   nearest', near[0], [round(v, 5) for v in near[1]], 'lateral_mm', round(lateral * 1000, 3),
              'vertical_mm', round((arm2[2] - near[1][2] - 0.005) * 1000, 3),
              'quat', [round(v, 4) for v in observations['final_cap_rotations_xyzw'][near[0]]])
    else:
        print('   cap_4', [round(v, 5) for v in positions.get('cap_4', [])] if positions else '-')
