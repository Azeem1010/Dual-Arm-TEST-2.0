"""Starts the operator interface.

Default: live data, and the interface may start and stop the system. --monitor only
watches. --fake shows invented demonstration data without ROS.
"""
import argparse
import fcntl
import os
from pathlib import Path
import sys

from PyQt5.QtCore import QCoreApplication, Qt
from PyQt5.QtWidgets import QApplication

from .sources.fake_source import FakeSource
from .ui import theme
from .ui.main_window import MainWindow

STATE_DIR = Path('~/.ros/dual_arm_hmi').expanduser()


def create_application(argv):
    QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    app = QApplication.instance() or QApplication(argv)
    app.setStyle('Fusion')
    app.setFont(theme.sans())
    app.setStyleSheet(theme.style_sheet())
    return app


def parse_arguments(argv):
    parser = argparse.ArgumentParser(description='Dual arm operator interface.')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--fake', action='store_true', help='use invented demonstration data')
    group.add_argument('--monitor', action='store_true', help='only watch; never start or stop anything')
    parser.add_argument('--scenario', default='ready', help='demonstration state to start in')
    return parser.parse_args(argv)


def acquire_single_instance(state_dir=STATE_DIR):
    """Only one interface may own the system. Returns the open lock file, or None if another holds it."""
    state_dir.mkdir(parents=True, exist_ok=True)
    handle = open(state_dir / 'hmi.lock', 'w')
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return handle


def live_source(monitor_only):
    # Imported here so demonstration mode works without a ROS environment.
    from ament_index_python.packages import get_package_prefix, get_package_share_directory

    from .launcher.process import Launcher
    from .launcher.profiles import apply_environment, load_profiles, workspace_from_prefix
    from .sources.live_source import LiveSource, SettingsStore
    from .sources.ros_source import RosSource

    profiles = load_profiles(os.path.join(get_package_share_directory('dual_arm_hmi'), 'config', 'profiles.yaml'))
    # Must happen before the ROS context exists so this interface joins the same domain it starts.
    apply_environment(profiles)
    ros = RosSource()
    if monitor_only:
        return ros
    return LiveSource(ros, Launcher(STATE_DIR), profiles, workspace_from_prefix(get_package_prefix('dual_arm_hmi')),
                      SettingsStore(str(STATE_DIR / 'settings.json')))


def main(argv=None):
    args = parse_arguments(sys.argv[1:] if argv is None else argv)
    lock = None
    if not args.fake and not args.monitor:
        lock = acquire_single_instance()
        if lock is None:
            print('Another operator interface is already running. Use --monitor for a second, watch-only window.',
                  file=sys.stderr)
            return 3
    app = create_application(sys.argv[:1])
    if not theme.font_available():
        print('Noto Sans CJK TC is missing; install fonts-noto-cjk or Chinese text will not display.', file=sys.stderr)
    source = FakeSource(args.scenario) if args.fake else live_source(args.monitor)
    window = MainWindow(source)
    window.resize(1920, 1080)
    window.show()
    code = app.exec_()
    if lock is not None:
        lock.close()
    return code


if __name__ == '__main__':
    sys.exit(main())
