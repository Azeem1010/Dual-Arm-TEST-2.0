"""Saves the demonstration states as images so the layout can be reviewed and recorded."""
import argparse
import os
from pathlib import Path
import sys

RESOLUTIONS = ((1920, 1080), (1280, 720), (1366, 768), (2560, 1440))
BASE_RESOLUTION = RESOLUTIONS[0]
SIZE_CHECK_SCENARIOS = ('working', 'latched')


class FixedClock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


def capture(window_factory, clock, scenario, size, path, app):
    from ..sources.fake_source import STEP_PERIOD_S, WORK_SEQUENCE
    window = window_factory(scenario)
    window.resize(*size)
    window.show()
    app.processEvents()
    if scenario == 'working':
        # A step where most of the display, including the zone B interlock, is populated.
        clock.now += STEP_PERIOD_S * WORK_SEQUENCE.index('ARM2:DESCEND_B')
    window.refresh()
    app.processEvents()
    window.refresh()
    app.processEvents()
    window.grab().save(str(path))
    window.timer.stop()
    window.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--platform', default='offscreen', help='Qt platform plugin, for example offscreen or xcb')
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    os.environ['QT_QPA_PLATFORM'] = args.platform

    from ..app import create_application
    from ..sources.fake_source import FakeSource
    from ..ui import theme
    from ..ui.main_window import MainWindow

    app = create_application(sys.argv[:1])
    if not theme.font_available():
        print('Noto Sans CJK TC is missing; screenshots would not represent the design.', file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)

    def run(scenario, size):
        clock = FixedClock()
        name = f'{scenario}_{size[0]}x{size[1]}.png'
        capture(lambda key: MainWindow(FakeSource(key, clock=clock)), clock, scenario, size, args.out / name, app)
        print(name, flush=True)

    keys = tuple(key for key, _ in FakeSource().scenarios())
    for scenario in keys:
        run(scenario, BASE_RESOLUTION)
    for size in RESOLUTIONS[1:]:
        for scenario in SIZE_CHECK_SCENARIOS:
            run(scenario, size)
    return 0


if __name__ == '__main__':
    sys.exit(main())
