"""Starts the operator interface: read-only live data, or demonstration data with --fake."""
import argparse
import sys

from PyQt5.QtCore import QCoreApplication, Qt
from PyQt5.QtWidgets import QApplication

from .sources.fake_source import FakeSource
from .ui import theme
from .ui.main_window import MainWindow


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
    parser.add_argument('--fake', action='store_true', help='use invented demonstration data')
    parser.add_argument('--scenario', default='ready', help='demonstration state to start in')
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_arguments(sys.argv[1:] if argv is None else argv)
    app = create_application(sys.argv[:1])
    if not theme.font_available():
        print('Noto Sans CJK TC is missing; install fonts-noto-cjk or Chinese text will not display.', file=sys.stderr)
    if args.fake:
        source = FakeSource(args.scenario)
    else:
        # Imported here so demonstration mode works without a ROS environment.
        from .sources.ros_source import RosSource
        source = RosSource()
    window = MainWindow(source)
    window.resize(1920, 1080)
    window.show()
    return app.exec_()


if __name__ == '__main__':
    sys.exit(main())
