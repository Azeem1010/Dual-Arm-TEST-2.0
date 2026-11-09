"""Opens the real window on the WSLg display, presses F12 for real and records what happened."""
import json
import sys
import time

from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest

from dual_arm_hmi.app import create_application
from dual_arm_hmi.model.state import Action
from dual_arm_hmi.sources.fake_source import FakeSource
from dual_arm_hmi.ui import theme
from dual_arm_hmi.ui.main_window import MainWindow

out = sys.argv[1]
app = create_application(['check'])
source = FakeSource('working')
window = MainWindow(source)
window.resize(1920, 1000)
window.show()
exposed = QTest.qWaitForWindowExposed(window, 8000)
window.activateWindow()
active = QTest.qWaitForWindowActive(window, 5000)

sent = []
original = source.invoke
source.invoke = lambda action: (sent.append(action), original(action))

# Measure the real refresh loop while frames are drawn.
started, durations = time.monotonic(), []
while time.monotonic() - started < 5.0:
    tick = time.monotonic()
    window.refresh()
    durations.append(time.monotonic() - tick)
    app.processEvents()
    QTest.qWait(100)

QTest.keyClick(window, Qt.Key_F12)
app.processEvents()
window.grab().save(out + '/wslg_window.png')
screen = app.primaryScreen()
result = {
    'platform': app.platformName(), 'exposed': bool(exposed), 'active': bool(active),
    'window': [window.width(), window.height()], 'screen': [screen.size().width(), screen.size().height()],
    'device_pixel_ratio': screen.devicePixelRatio(), 'cjk_font': theme.font_available(),
    'f12_sent_stop': sent == [Action.STOP],
    'refresh_ms_mean': round(1000 * sum(durations) / len(durations), 1),
    'refresh_ms_max': round(1000 * max(durations), 1), 'refresh_samples': len(durations),
}
print(json.dumps(result, indent=2), flush=True)
with open(out + '/wslg_window.json', 'w', encoding='utf-8') as handle:
    json.dump(result, handle, indent=2)
window.timer.stop()
window.close()
