# player_bar.py
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QSizePolicy
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPainterPath, QPen
from widgets import RoundIconBtn

_R = 20; _CAP_H = 44; _CTRL_H = 80
_SWIPE_UP = -45   # px — свайп вверх по островку → открыть страницу трека


class PlayerBar(QWidget):
    sig_prev  = pyqtSignal()
    sig_next  = pyqtSignal()
    sig_play  = pyqtSignal()
    sig_open  = pyqtSignal()   # двойной тап на кнопку play ИЛИ свайп вверх

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(_CAP_H + _CTRL_H)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._nclicks = 0
        self._ctimer = QTimer(); self._ctimer.setSingleShot(True)
        self._ctimer.timeout.connect(self._do_play)

        vl = QVBoxLayout(self); vl.setContentsMargins(0, 0, 0, 0); vl.setSpacing(0)

        # Полоска-шапка: маленький пилюль + зона свайпа
        self._cap = _CapZone()
        self._cap.setFixedHeight(_CAP_H)
        self._cap.tapped.connect(self.sig_open)
        self._cap.swiped_up.connect(self.sig_open)
        vl.addWidget(self._cap)

        ctrl = QWidget(); ctrl.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        ctrl.setFixedHeight(_CTRL_H)
        hl = QHBoxLayout(ctrl); hl.setContentsMargins(24, 6, 24, 14); hl.setSpacing(20)
        self.b_prev = RoundIconBtn("prev", 52, 20, 26)
        self.b_play = RoundIconBtn("play", 62, 26, 31)
        self.b_next = RoundIconBtn("next", 52, 20, 26)
        for btn in (self.b_prev, self.b_play, self.b_next):
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        hl.addStretch(1)
        hl.addWidget(self.b_prev); hl.addWidget(self.b_play); hl.addWidget(self.b_next)
        hl.addStretch(1)
        vl.addWidget(ctrl)

        self.b_prev.clicked.connect(self.sig_prev)
        self.b_next.clicked.connect(self.sig_next)
        self.b_play.clicked.connect(self._play_click)

        # Свайп по всему островку (кроме кнопок, которые едят события сами)
        self._sw_y = None

    # Обрабатываем свайп на самом PlayerBar (фон между кнопками)
    def mousePressEvent(self, e):
        self._sw_y = e.position().y(); super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if self._sw_y is not None:
            dy = e.position().y() - self._sw_y
            if dy < _SWIPE_UP:
                self.sig_open.emit()
        self._sw_y = None; super().mouseReleaseEvent(e)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        path = QPainterPath(); path.addRoundedRect(0, 0, w, h, _R, _R)
        p.fillPath(path, QColor(14, 14, 24, 252))
        ctrl = QPainterPath(); ctrl.addRect(0, _CAP_H, w, _CTRL_H)
        p.fillPath(path.intersected(ctrl), QColor(255, 255, 255, 9))
        pen = QPen(QColor(255, 255, 255, 18)); pen.setWidthF(1.0); p.setPen(pen)
        p.drawLine(0, _CAP_H, w, _CAP_H)
        p.end()

    def _play_click(self):
        self._nclicks += 1
        if self._nclicks == 1:
            self._ctimer.start(260)
        elif self._nclicks >= 2:
            self._ctimer.stop(); self._nclicks = 0; self.sig_open.emit()

    def _do_play(self): self._nclicks = 0; self.sig_play.emit()

    def set_playing(self, v): self.b_play.swap("pause" if v else "play")


class _CapZone(QWidget):
    """Полная ширина — тап/свайп-зона с маленьким центрированным пилюлем."""
    tapped    = pyqtSignal()
    swiped_up = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._press = False; self._py = None

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._py = e.position().y(); self._press = True; self.update()
        e.accept()

    def mouseReleaseEvent(self, e):
        if self._press and self._py is not None:
            dy = e.position().y() - self._py
            if dy < -30:                        # свайп вверх
                self.swiped_up.emit()
            elif abs(dy) < 18:                  # тап
                self.tapped.emit()
            self._press = False; self._py = None; self.update()
        e.accept()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if self._press:
            p.fillRect(0, 0, w, h, QColor(255, 255, 255, 6))
        # Маленький пилюль 36×4 px по центру
        pw, ph = 36, 4
        px2 = (w - pw) // 2; py2 = (h - ph) // 2 - 2
        path = QPainterPath(); path.addRoundedRect(px2, py2, pw, ph, 2, 2)
        p.fillPath(path, QColor(255, 255, 255, 80 if self._press else 55))
        p.end()
