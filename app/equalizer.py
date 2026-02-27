# equalizer.py
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal, QPointF, QRectF
from PyQt6.QtGui import (QPainter, QColor, QPainterPath, QPen, QFont,
                         QLinearGradient, QBrush, QRadialGradient)

EQ_BANDS = ["60Hz", "250Hz", "1kHz", "4kHz", "16kHz"]
_RANGE = 12; _RADIUS = 20
_SWIPE_DOWN = 50   # px — свайп вниз за пилюль → закрыть


class BandBar(QWidget):
    value_changed = pyqtSignal(int, int)
    _TW = 4; _HR = 10; _LBL_H = 20; _VAL_H = 18

    def __init__(self, idx, label, parent=None):
        super().__init__(parent)
        self.idx = idx; self._val = 0; self._drag = False; self._label = label
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumWidth(28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def value(self): return self._val

    def setValue(self, v):
        v = max(-_RANGE, min(_RANGE, v))
        if v != self._val:
            self._val = v; self.value_changed.emit(self.idx, v); self.update()

    def reset(self): self.setValue(0)

    def _geo(self):
        cx = self.width() / 2
        top = self._VAL_H + self._HR + 4
        bot = self.height() - self._LBL_H - self._HR - 4
        return cx, top, bot, max(1.0, bot - top)

    def _v2y(self, v):
        cx, top, bot, th = self._geo()
        return top + (_RANGE - v) / (2 * _RANGE) * th

    def _y2v(self, y):
        cx, top, bot, th = self._geo()
        return round(_RANGE - max(0.0, min(1.0, (y - top) / th)) * 2 * _RANGE)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = True; self.setValue(self._y2v(e.position().y()))
        e.accept()

    def mouseMoveEvent(self, e):
        if self._drag: self.setValue(self._y2v(e.position().y()))
        e.accept()

    def mouseReleaseEvent(self, e): self._drag = False; e.accept()
    def wheelEvent(self, e): self.setValue(self._val + (1 if e.angleDelta().y() > 0 else -1)); e.accept()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, top, bot, th = self._geo(); tw = self._TW / 2
        hy = self._v2y(self._val); hr = self._HR
        tr = QPainterPath()
        tr.addRoundedRect(QRectF(cx - tw, top, self._TW, th), tw, tw)
        p.fillPath(tr, QColor(255, 255, 255, 30))
        zy = self._v2y(0); fh = abs(hy - zy)
        if fh > 0.5:
            fp = QPainterPath()
            fp.addRoundedRect(QRectF(cx - tw, min(hy, zy), self._TW, fh), tw, tw)
            fg = QLinearGradient(cx, min(hy, zy), cx, min(hy, zy) + fh)
            if self._val >= 0:
                fg.setColorAt(0, QColor(200, 170, 255, 255)); fg.setColorAt(1, QColor(120, 90, 220, 200))
            else:
                fg.setColorAt(0, QColor(80, 120, 220, 180));  fg.setColorAt(1, QColor(50, 80, 180, 240))
            p.fillPath(fp, QBrush(fg))
        pz = QPen(QColor(255, 255, 255, 45)); pz.setWidthF(1.0); p.setPen(pz)
        p.drawLine(QPointF(cx - 6, zy), QPointF(cx + 6, zy))
        gw = QRadialGradient(cx, hy, hr + 5)
        gw.setColorAt(0, QColor(200, 180, 255, 60)); gw.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(gw)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, hy), hr + 5, hr + 5)
        hp = QPainterPath(); hp.addEllipse(QPointF(cx, hy), hr, hr)
        hg = QRadialGradient(cx - hr * .25, hy - hr * .25, hr * 1.2)
        hg.setColorAt(0, QColor(255, 255, 255, 255))
        hg.setColorAt(.6, QColor(220, 210, 255, 240))
        hg.setColorAt(1, QColor(180, 160, 240, 220))
        p.fillPath(hp, QBrush(hg))
        ph = QPen(QColor(255, 255, 255, 90)); ph.setWidthF(1.0); p.setPen(ph); p.drawPath(hp)
        sign = "+" if self._val >= 0 else ""
        p.setOpacity(1.0)
        p.setPen(QColor(255, 255, 255, 160 if self._val == 0 else 220))
        p.setFont(QFont("Helvetica Neue", 9, QFont.Weight.Bold if self._val != 0 else QFont.Weight.Normal))
        p.drawText(QRectF(0, 0, self.width(), self._VAL_H),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, f"{sign}{self._val}")
        p.setPen(QColor(255, 255, 255, 155))
        p.setFont(QFont("Helvetica Neue", 9, QFont.Weight.Bold))
        p.drawText(QRectF(0, self.height() - self._LBL_H, self.width(), self._LBL_H),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, self._label)
        p.end()


class _EQCurve(QWidget):
    def __init__(self, n, parent=None):
        super().__init__(parent); self._gains = [0] * n
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedHeight(46)

    def set_gains(self, g): self._gains = list(g); self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height(); n = len(self._gains)
        if n < 2: return
        mid = h / 2; sc = mid / 12
        pts = [QPointF(i / (n - 1) * w, mid - g * sc) for i, g in enumerate(self._gains)]
        area = QPainterPath(); area.moveTo(QPointF(0, mid)); area.lineTo(pts[0])
        for i in range(1, len(pts)):
            mx = (pts[i-1].x() + pts[i].x()) / 2
            area.cubicTo(QPointF(mx, pts[i-1].y()), QPointF(mx, pts[i].y()), pts[i])
        area.lineTo(QPointF(w, mid)); area.closeSubpath()
        fl = QLinearGradient(0, 0, 0, h)
        fl.setColorAt(0, QColor(160, 130, 255, 55)); fl.setColorAt(1, QColor(80, 60, 220, 6))
        p.fillPath(area, QBrush(fl))
        ln = QPainterPath(); ln.moveTo(pts[0])
        for i in range(1, len(pts)):
            mx = (pts[i-1].x() + pts[i].x()) / 2
            ln.cubicTo(QPointF(mx, pts[i-1].y()), QPointF(mx, pts[i].y()), pts[i])
        pe = QPen(QColor(185, 155, 255, 210)); pe.setWidthF(1.8); p.setPen(pe); p.drawPath(ln)
        pe2 = QPen(QColor(255, 255, 255, 25)); pe2.setWidthF(1); pe2.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pe2); p.drawLine(QPointF(0, mid), QPointF(w, mid)); p.end()


class _PillHandle(QWidget):
    """
    Верхняя полоска эквалайзера.
    • Тап  → close_req
    • Свайп вниз (> _SWIPE_DOWN px) → close_req
    """
    close_req = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._press = False; self._py = None; self._hov = False

    def enterEvent(self, e): self._hov = True;  self.update()
    def leaveEvent(self, e): self._hov = False; self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._py = e.position().y(); self._press = True; self.update()
        e.accept()

    def mouseReleaseEvent(self, e):
        if self._press and self._py is not None:
            dy = e.position().y() - self._py
            if dy > _SWIPE_DOWN or abs(dy) < 18:   # свайп вниз ИЛИ тап
                self.close_req.emit()
            self._press = False; self._py = None; self.update()
        e.accept()

    def mouseMoveEvent(self, e):
        # Живой свайп — можно посмотреть прогресс (пока просто едим событие)
        e.accept()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        # Лёгкий hover-подсвет
        if self._hov or self._press:
            p.fillRect(0, 0, w, h, QColor(255, 255, 255, 8 if self._press else 5))
        # Маленький пилюль 40×4 px по центру
        pw, ph = 40, 4
        px2 = (w - pw) // 2; py2 = (h - ph) // 2 - 1
        path = QPainterPath(); path.addRoundedRect(px2, py2, pw, ph, 2, 2)
        opacity = 0.95 if self._press else (0.80 if self._hov else 0.55)
        p.setOpacity(opacity)
        p.fillPath(path, QColor(255, 255, 255, 255))
        p.end()


class EqualizerSheet(QWidget):
    """
    Bottom sheet EQ.
    Полоска сверху (_PillHandle) — тап или свайп вниз закрывает.
    Внешний EQOverlay тоже ловит свайп и тап по тёмной области.
    """
    gains_changed = pyqtSignal(list)   # list[float] dB
    close_req     = pyqtSignal()       # полоска просит закрыть

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._gains = [0] * len(EQ_BANDS)

        vl = QVBoxLayout(self); vl.setContentsMargins(0, 0, 0, 0); vl.setSpacing(0)

        # ── Полоска-ручка ─────────────────────────────────────────────────────
        self._pill = _PillHandle()
        self._pill.close_req.connect(self.close_req)
        vl.addWidget(self._pill)

        # ── Внутренний контент ────────────────────────────────────────────────
        inner = QWidget(); inner.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        ivl = QVBoxLayout(inner); ivl.setContentsMargins(20, 2, 20, 16); ivl.setSpacing(8)

        hdr = QHBoxLayout()
        t = QLabel("Эквалайзер")
        t.setFont(QFont("Helvetica Neue", 16, QFont.Weight.Bold))
        t.setStyleSheet("color:rgba(255,255,255,220);background:transparent;")
        r_btn = QLabel("Сброс")
        r_btn.setFont(QFont("Helvetica Neue", 11))
        r_btn.setStyleSheet("color:rgba(255,255,255,100);background:transparent;padding:2px 0;")
        r_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        r_btn.mousePressEvent = lambda _: self._reset()
        hdr.addWidget(t); hdr.addStretch(); hdr.addWidget(r_btn)
        ivl.addLayout(hdr)

        self._curve = _EQCurve(len(EQ_BANDS)); ivl.addWidget(self._curve)

        bands_row = QHBoxLayout(); bands_row.setSpacing(4)
        self._bands: list[BandBar] = []
        for i, label in enumerate(EQ_BANDS):
            bw = BandBar(i, label); bw.value_changed.connect(self._on_band)
            self._bands.append(bw); bands_row.addWidget(bw, 1)
        ivl.addLayout(bands_row, 1)
        vl.addWidget(inner, 1)

    def _on_band(self, idx, v):
        self._gains[idx] = v; self._curve.set_gains(self._gains)
        self.gains_changed.emit([float(g) for g in self._gains])

    def _reset(self):
        for bw in self._bands: bw.reset()

    def get_gains(self): return list(self._gains)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height(); r = _RADIUS
        path = QPainterPath()
        path.moveTo(0, h); path.lineTo(0, r)
        path.arcTo(0, 0, r * 2, r * 2, 180, -90)
        path.lineTo(w - r, 0); path.arcTo(w - r * 2, 0, r * 2, r * 2, 90, -90)
        path.lineTo(w, h); path.closeSubpath()
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0, QColor(22, 20, 38, 253)); grad.setColorAt(1, QColor(14, 12, 26, 255))
        p.fillPath(path, QBrush(grad))
        pen = QPen(QColor(255, 255, 255, 18)); pen.setWidthF(1.0); p.setPen(pen); p.drawPath(path)
        p.end()
