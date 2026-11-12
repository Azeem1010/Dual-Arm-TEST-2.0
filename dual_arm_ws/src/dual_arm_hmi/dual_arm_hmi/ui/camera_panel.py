"""One camera: the image kept at 4:3, with freshness and calibration beside the title."""
from PyQt5.QtCore import QRect, Qt, pyqtSignal
from PyQt5.QtGui import QImage, QPainter
from PyQt5.QtWidgets import QComboBox, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from ..model.state import GAZEBO_VIEWS, Level, calibration_label
from . import theme
from .widgets import Chip, HeaderBar, Panel, WhiteLabel

_ASPECT = 4.0 / 3.0


def to_qimage(frame):
    """Copy a BGR array so the image stays valid after the array changes."""
    height, width = frame.shape[:2]
    return QImage(frame.data, width, height, 3 * width, QImage.Format_BGR888).copy()


def fit_4_3(rect):
    """The largest 4:3 rectangle centred in rect, so detection boxes are never distorted."""
    width = min(rect.width(), int(rect.height() * _ASPECT))
    height = int(width / _ASPECT)
    return QRect(rect.x() + (rect.width() - width) // 2, rect.y() + (rect.height() - height) // 2, width, height)


class CameraView(QWidget):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.image = None
        self.placeholder = ('未啟動', Level.NEUTRAL)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.PointingHandCursor)

    def set_image(self, image, placeholder):
        self.image, self.placeholder = image, placeholder
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), theme.color(theme.TRACK))
        target = fit_4_3(self.rect())
        if self.image is not None:
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            painter.drawImage(target, self.image)
            return
        text, level = self.placeholder
        background, foreground = theme.LEVEL_COLORS[level]
        band = QRect(target.x(), target.center().y() - 26, target.width(), 52)
        painter.fillRect(band, theme.color(background))
        painter.setPen(theme.color(foreground))
        painter.setFont(theme.sans(theme.SIZE_STATUS, bold=True))
        painter.drawText(band, Qt.AlignCenter, text)


class CameraPanel(Panel):
    focus_toggled = pyqtSignal(str)

    def __init__(self, key, title, background, parent=None):
        super().__init__(parent)
        self.key = key
        self.annotated = True
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.header = HeaderBar(title, background, self)
        self.stats = WhiteLabel('', self.header)
        self.calibration = Chip(self.header)
        self.toggle = QPushButton('標註', self.header)
        self.toggle.setProperty('headerButton', True)
        self.toggle.setFixedSize(52, 22)
        self.toggle.setToolTip('切換 OpenCV 標註與原始影像')
        self.toggle.clicked.connect(self._toggle_annotated)
        for widget in (self.stats, self.calibration, self.toggle):
            self.header.add_right(widget)
        self.view = CameraView(self)
        self.view.clicked.connect(lambda: self.focus_toggled.emit(self.key))
        layout.addWidget(self.header)
        layout.addWidget(self.view, 1)

    def _toggle_annotated(self):
        self.annotated = not self.annotated
        self.toggle.setText('標註' if self.annotated else '原始')

    def set_status(self, status):
        """status is None when the mode has no such camera."""
        if status is None or not status.has_signal:
            self.stats.setText('')
        else:
            self.stats.setText(f'{status.fps:.0f} FPS {status.age_s:.2f}s')
        if self.annotated:
            # Say so when annotations are absent, rather than showing the raw image under an "annotated" label.
            self.toggle.setText('標註' if status is None or status.has_annotation or not status.has_signal else '無標註')
        calibration = 'NOT_RUN' if status is None or status.rotation else status.calibration
        color = {'PASS': theme.OK, 'FAIL': theme.DANGER}.get(calibration, theme.TEXT_MUTED)
        self.calibration.set_chip(calibration_label(status), '#FFFFFF', color)

    def set_frame(self, frame, placeholder):
        self.view.set_image(None if frame is None else to_qimage(frame), placeholder)


class GazeboPanel(Panel):
    """The simulated scene, kept visibly separate from the real cameras."""
    close_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.header = HeaderBar('Gazebo 視角', theme.NAVY, self)
        self.notice = WhiteLabel('Gazebo 模擬，非實機影像', self.header)
        self.notice.setFont(theme.sans(theme.SIZE_BODY, bold=True))
        self.selector = QComboBox(self.header)
        for key, label in GAZEBO_VIEWS:
            self.selector.addItem(label, key)
        self.selector.setFixedWidth(96)
        self.header.add_right(self.notice)
        self.header.add_right(self.selector)
        self.view = CameraView(self)
        self.view.clicked.connect(self.close_requested)
        layout.addWidget(self.header)
        layout.addWidget(self.view, 1)

    def current_view(self):
        return self.selector.currentData()

    def set_frame(self, frame, placeholder):
        self.view.set_image(None if frame is None else to_qimage(frame), placeholder)
