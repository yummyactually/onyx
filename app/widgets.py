# widgets.py
from PyQt6.QtWidgets import QWidget, QLabel, QLineEdit, QPushButton, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QPointF
from PyQt6.QtGui import (QPainter, QColor, QPainterPath, QPen, QFont,
                         QFontMetrics, QLinearGradient, QBrush, QRadialGradient)
from icons import icon_pm


class ElidingLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent); self._full = text
    def setText(self, t): self._full = t; super().setText(t)
    def resizeEvent(self, e):
        super().resizeEvent(e)
        fm = QFontMetrics(self.font())
        super().setText(fm.elidedText(self._full, Qt.TextElideMode.ElideRight, max(self.width(),1)))


class SmoothSlider(QWidget):
    valueChanged = pyqtSignal(int)
    sliderMoved  = pyqtSignal(int)
    _TH = 3; _HR = 9; _PAD = 14

    def __init__(self, parent=None):
        super().__init__(parent)
        self._min = 0; self._max = 1000; self._val = 0
        self._drag = False; self._hov = False
        self.setMinimumHeight(36)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

    def setRange(self, lo, hi): self._min = lo; self._max = hi; self.update()
    def minimum(self): return self._min
    def maximum(self): return self._max
    def value(self):   return self._val

    def setValue(self, v, emit=True):
        v = max(self._min, min(self._max, int(v)))
        changed = (v != self._val)
        self._val = v; self.update()
        if emit and changed: self.valueChanged.emit(v)

    def _x0(self): return self._PAD
    def _x1(self): return self.width() - self._PAD
    def _span(self): return max(1, self._x1() - self._x0())
    def _cy(self): return self.height() // 2

    def _v2x(self, v):
        rng = self._max - self._min
        if rng == 0: return float(self._x0())
        return self._x0() + (v - self._min) / rng * self._span()

    def _x2v(self, x):
        ratio = (x - self._x0()) / self._span()
        return round(self._min + max(0.0, min(1.0, ratio)) * (self._max - self._min))

    def enterEvent(self, e): self._hov = True;  self.update()
    def leaveEvent(self, e): self._hov = False; self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = True
            v = self._x2v(e.position().x())
            self._val = v; self.update()
            self.valueChanged.emit(v); self.sliderMoved.emit(v)
        e.accept()

    def mouseMoveEvent(self, e):
        if self._drag:
            v = self._x2v(e.position().x())
            self._val = v; self.update()
            self.valueChanged.emit(v); self.sliderMoved.emit(v)
        e.accept()

    def mouseReleaseEvent(self, e):
        self._drag = False; e.accept()

    def wheelEvent(self, e):
        step = max(1, (self._max - self._min) // 100)
        self.setValue(self._val + (step if e.angleDelta().y() > 0 else -step))
        e.accept()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cy = self._cy(); x0 = self._x0(); x1 = self._x1()
        hx = self._v2x(self._val); th = self._TH; hr = self._HR
        # Track bg
        bg = QPainterPath()
        bg.addRoundedRect(QRectF(x0, cy-th/2, x1-x0, th), th/2, th/2)
        p.fillPath(bg, QColor(255,255,255,35))
        # Filled portion
        if hx > x0 + 0.5:
            fl = QPainterPath()
            fl.addRoundedRect(QRectF(x0, cy-th/2, hx-x0, th), th/2, th/2)
            p.fillPath(fl, QColor(255,255,255,200))
        # Glow
        if self._hov or self._drag:
            gw = QRadialGradient(hx, cy, hr+7)
            gw.setColorAt(0.0, QColor(255,255,255,45))
            gw.setColorAt(1.0, QColor(0,0,0,0))
            p.setBrush(QBrush(gw)); p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(hx,cy), hr+7, hr+7)
        # Handle
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255,255,255,255))
        p.drawEllipse(QPointF(hx, cy), hr, hr)
        p.end()


# Alias
ThinSlider = SmoothSlider


class FlatIconBtn(QPushButton):
    def __init__(self, icon_name, size=40, icon_px=20, parent=None):
        super().__init__(parent)
        self._ipx = icon_px; self._hov = False; self._press = False
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pm = icon_pm(icon_name, icon_px*2)

    def swap(self, name): self._pm = icon_pm(name, self._ipx*2); self.update()
    def enterEvent(self, e): self._hov = True;  self.update()
    def leaveEvent(self, e): self._hov = False; self.update()
    def mousePressEvent(self, e):   self._press = True;  self.update(); super().mousePressEvent(e)
    def mouseReleaseEvent(self, e): self._press = False; self.update(); super().mouseReleaseEvent(e)
    def paintEvent(self, _):
        p = QPainter(self)
        p.setOpacity(0.35 if self._press else (0.95 if self._hov else 0.70))
        iw, ih = self._pm.width(), self._pm.height()
        p.drawPixmap((self.width()-iw)//2, (self.height()-ih)//2, self._pm)
        p.end()


class ToggleIconBtn(QPushButton):
    def __init__(self, icon_name, size=40, icon_px=20, parent=None):
        super().__init__(parent)
        self._ipx = icon_px; self._active = False; self._hov = False; self._press = False
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pm = icon_pm(icon_name, icon_px*2)

    def set_active(self, v): self._active = v; self.update()
    def is_active(self): return self._active
    def enterEvent(self, e): self._hov = True;  self.update()
    def leaveEvent(self, e): self._hov = False; self.update()
    def mousePressEvent(self, e):   self._press = True;  self.update(); super().mousePressEvent(e)
    def mouseReleaseEvent(self, e): self._press = False; self.update(); super().mouseReleaseEvent(e)
    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._active:
            path = QPainterPath()
            path.addRoundedRect(2, 2, self.width()-4, self.height()-4, 8, 8)
            p.fillPath(path, QColor(180,150,255,50))
        p.setOpacity(0.35 if self._press else (1.0 if self._active else (0.85 if self._hov else 0.50)))
        iw, ih = self._pm.width(), self._pm.height()
        p.drawPixmap((self.width()-iw)//2, (self.height()-ih)//2, self._pm)
        p.end()


class RoundIconBtn(QPushButton):
    def __init__(self, icon_name, btn_sz=56, icon_px=24, radius=None, parent=None):
        super().__init__(parent)
        self._ipx = icon_px; self._name = icon_name
        self._r = radius if radius is not None else btn_sz//2
        self._hov = False; self._press = False
        self.setFixedSize(btn_sz, btn_sz)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pm = icon_pm(icon_name, icon_px*2)

    def swap(self, name): self._name = name; self._pm = icon_pm(name, self._ipx*2); self.update()
    def enterEvent(self, e): self._hov = True;  self.update()
    def leaveEvent(self, e): self._hov = False; self.update()
    def mousePressEvent(self, e):   self._press = True;  self.update(); super().mousePressEvent(e)
    def mouseReleaseEvent(self, e): self._press = False; self.update(); super().mouseReleaseEvent(e)
    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), self._r, self._r)
        bg = QColor(60,60,78) if self._press else (QColor(46,46,62) if self._hov else QColor(32,32,48))
        p.fillPath(path, bg)
        pen = QPen(QColor(255,255,255,16)); pen.setWidthF(1.0); p.setPen(pen); p.drawPath(path)
        iw, ih = self._pm.width(), self._pm.height()
        x_off = 2 if self._name == "play" else 0
        p.setOpacity(0.55 if self._press else 0.95)
        p.drawPixmap((self.width()-iw)//2+x_off, (self.height()-ih)//2, self._pm)
        p.end()


class DarkEdit(QLineEdit):
    def __init__(self, placeholder="", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setFont(QFont("Helvetica Neue", 12))
        self.setStyleSheet("""
            QLineEdit {
                background: rgba(255,255,255,9);
                border: 1px solid rgba(255,255,255,20);
                border-radius: 12px;
                color: rgba(240,240,248,220);
                padding: 9px 14px;
            }
            QLineEdit:focus {
                border: 1px solid rgba(255,255,255,50);
                background: rgba(255,255,255,13);
            }
        """)
