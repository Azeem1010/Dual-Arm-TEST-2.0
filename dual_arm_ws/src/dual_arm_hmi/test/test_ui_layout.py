"""Renders the real widgets off screen, so a layout mistake fails here rather than on the operator's screen."""
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest  # noqa: E402

QtWidgets = pytest.importorskip('PyQt5.QtWidgets')

from PyQt5.QtCore import QPoint, QRect, Qt  # noqa: E402
from PyQt5.QtTest import QTest  # noqa: E402

from dual_arm_hmi.app import create_application  # noqa: E402
from dataclasses import replace  # noqa: E402

from dual_arm_hmi.model.state import Action, CameraStatus  # noqa: E402
from dual_arm_hmi.sources.fake_source import FakeSource  # noqa: E402
from dual_arm_hmi.ui.camera_panel import fit_4_3  # noqa: E402
from dual_arm_hmi.ui.main_window import MainWindow  # noqa: E402

SCENARIOS = tuple(key for key, _ in FakeSource().scenarios())
SIZES = ((1280, 720), (1366, 768), (1920, 1080), (2560, 1440))


@pytest.fixture(scope='module')
def app():
    return create_application(['test'])


def open_window(app, scenario, size):
    window = MainWindow(FakeSource(scenario))
    window.timer.stop()
    window.resize(*size)
    window.show()
    app.processEvents()
    window.refresh()
    app.processEvents()
    return window


def geometry_in_window(widget, window):
    return QRect(widget.mapTo(window, QPoint(0, 0)), widget.size())


def under_scroll_area(widget):
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QtWidgets.QAbstractScrollArea):
            return True
        parent = parent.parentWidget()
    return False


@pytest.mark.parametrize('size', SIZES)
@pytest.mark.parametrize('scenario', SCENARIOS)
def test_layout_at_every_size(app, scenario, size):
    window = open_window(app, scenario, size)
    assert (window.width(), window.height()) == size
    bounds = window.rect()

    sections = [window.status_bar, window.banner, window.camera_row, window.tables, window.event_log, window.control]
    for section in sections:
        assert section.isVisible()
        assert bounds.contains(geometry_in_window(section, window)), section

    assert window.control.stop.isVisible() and window.control.stop.isEnabled()
    assert bounds.contains(geometry_in_window(window.control.stop, window))

    for label in window.findChildren(QtWidgets.QLabel):
        if not label.isVisible() or under_scroll_area(label):
            continue
        assert bounds.contains(geometry_in_window(label, window)), label.text()
        assert label.height() >= label.fontMetrics().height() - 1, label.text()
        if not label.wordWrap() and label.text():
            assert label.fontMetrics().horizontalAdvance(label.text()) <= label.width(), label.text()

    for button in window.findChildren(QtWidgets.QPushButton):
        if button.isVisible() and button.objectName() != 'stop':
            assert button.fontMetrics().horizontalAdvance(button.text()) <= button.width(), button.text()
    window.close()


@pytest.mark.parametrize('size', SIZES)
def test_cameras_stay_4_by_3_and_equal(app, size):
    window = open_window(app, 'ready', size)
    targets = [fit_4_3(panel.view.rect()) for panel in window.cameras.values()]
    for target in targets:
        assert target.width() / target.height() == pytest.approx(4 / 3, abs=0.01)
    assert len({(target.width(), target.height()) for target in targets}) == 1
    window.close()


def test_base_resolution_uses_the_planned_camera_size(app):
    window = open_window(app, 'ready', (1920, 1080))
    assert window.control.width() == 320
    target = fit_4_3(window.cameras['env'].view.rect())
    assert target.width() >= 500
    window.close()


def test_compact_width_hides_the_radian_column(app):
    wide = open_window(app, 'ready', (1920, 1080))
    compact = open_window(app, 'ready', (1280, 720))
    label = '+0.100'
    visible = lambda window: any(cell.isVisible() and cell.text() == label for cell in window.findChildren(QtWidgets.QLabel))
    assert visible(wide) and not visible(compact)
    wide.close()
    compact.close()


def test_camera_focus_hides_the_rest_and_escape_returns(app):
    window = open_window(app, 'ready', (1920, 1080))
    window.cameras['arm1'].focus_toggled.emit('arm1')
    app.processEvents()
    assert window.cameras['arm1'].isVisible() and not window.cameras['env'].isVisible() and not window.tables.isVisible()
    assert window.control.stop.isVisible()
    window._leave_focus()
    app.processEvents()
    assert window.cameras['env'].isVisible() and window.tables.isVisible()
    window.close()


def test_short_window_log_collapses_and_expands(app):
    window = open_window(app, 'ready', (1366, 768))
    collapsed = window.event_log.height()
    window.event_log.expand.click()
    app.processEvents()
    assert not window.tables.isVisible() and window.event_log.height() > collapsed
    window.event_log.expand.click()
    app.processEvents()
    assert window.tables.isVisible()
    window.close()


def test_f12_stops_without_a_dialog(app):
    # Off screen there is no active window for a key press; the WSLg check sends a real one.
    window = open_window(app, 'working', (1920, 1080))
    sent = []
    window.source.invoke = sent.append
    shortcuts = [item for item in window.findChildren(QtWidgets.QShortcut) if item.key().toString() == 'F12']
    assert len(shortcuts) == 1 and shortcuts[0].context() == Qt.ApplicationShortcut
    shortcuts[0].activated.emit()
    assert sent == [Action.STOP]
    window.close()


def test_stop_button_sends_stop_without_a_dialog(app):
    window = open_window(app, 'working', (1920, 1080))
    sent = []
    window.source.invoke = sent.append
    QTest.mouseClick(window.control.stop, Qt.LeftButton)
    assert sent == [Action.STOP]
    window.close()


def test_start_button_cannot_take_keyboard_focus(app):
    window = open_window(app, 'ready', (1920, 1080))
    assert window.control.rows[Action.START_TASK].button.focusPolicy() == Qt.NoFocus
    window.close()


def test_confirmation_defaults_to_no(app, monkeypatch):
    window = open_window(app, 'ready', (1920, 1080))
    sent = []
    window.source.invoke = sent.append
    monkeypatch.setattr(QtWidgets.QMessageBox, 'exec_', lambda self: self.defaultButton() and QtWidgets.QMessageBox.No)
    window._on_action(Action.SHUTDOWN)
    assert sent == []
    window.close()


class MonitorSource(FakeSource):
    def snapshot(self):
        return replace(super().snapshot(), monitor_only=True)


@pytest.mark.parametrize('size', SIZES)
def test_monitor_mode_disables_every_control_and_says_so(app, size):
    window = MainWindow(MonitorSource('ready'))
    window.timer.stop()
    window.resize(*size)
    window.show()
    app.processEvents()
    window.refresh()
    app.processEvents()
    assert not window.control.stop.isEnabled() and window.control.stop.text() == '尚未接通'
    assert '尚未接通' in window.control.stop_note.text()
    assert not any(row.button.isEnabled() for row in window.control.rows.values())
    assert window.control.stop_note.isVisible()
    window.close()


def test_gazebo_view_opens_and_returns(app):
    window = open_window(app, 'ready', (1920, 1080))
    assert window.control.gazebo.isEnabled() and not window.gazebo_panel.isVisible()
    window.control.gazebo.click()
    app.processEvents()
    window.refresh()
    app.processEvents()
    assert window.gazebo_panel.isVisible() and window.gazebo_panel.view.image is not None
    assert not window.cameras['env'].isVisible() and window.control.stop.isVisible()
    assert '非實機' in window.gazebo_panel.notice.text() and window.control.gazebo.text() == '返回相機'
    window.control.gazebo.click()
    app.processEvents()
    assert not window.gazebo_panel.isVisible() and window.cameras['env'].isVisible()
    window.close()


def test_gazebo_button_is_disabled_with_a_reason_when_unavailable(app):
    window = open_window(app, 'hw_read_only', (1920, 1080))
    assert not window.control.gazebo.isEnabled() and window.control.gazebo_reason.text()
    window.close()


def test_missing_annotation_is_labelled(app):
    window = open_window(app, 'ready', (1920, 1080))
    panel = window.cameras['env']
    panel.set_status(CameraStatus(fps=15.0, age_s=0.05, calibration='PASS', has_annotation=False))
    assert panel.toggle.text() == '無標註'
    window.close()


def test_scenario_selector_changes_the_data(app):
    window = open_window(app, 'ready', (1920, 1080))
    combo = window.control.scenario
    combo.setCurrentIndex(combo.findData('latched'))
    combo.activated.emit(combo.currentIndex())
    app.processEvents()
    assert window.source.scenario() == 'latched'
    window.close()
